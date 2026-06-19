from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

from aegis_runtime import FuturesRef, ListedRef

from research.aegis_research.cli_support.errors import (
    CliError,
    ConfigCliError,
    ExecutionFailureError,
)
from research.aegis_research.cli_support.output import CommandResult, write_success
from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentSelection,
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.component_registry.contracts import IndicatorManifest, StrategyManifest
from research.aegis_research.configuration import (
    LOCK_ROLES,
    ConfigValidationError,
    RunConfig,
    load_run_config,
)
from research.aegis_research.market_data.currency import required_fx_currencies
from research.aegis_research.market_data.figi import resolve_symbol_figis
from research.aegis_research.optimization.candidate_publishing import candidate_store_path
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.lock_run import ResolvedComponentParams, resolve_lock_run
from research.aegis_research.optimization.param_namespace import ComponentRef

STRATEGY_SLOT = "strategy"
ENTRY_POINT_GROUP = "aegis.execution_bundles"

ComponentSpecMap = dict[str, Any]
# Resolves the universe's provider tickers to their ListedRef FIGI payloads (ticker -> FIGI).
FigiResolver = Callable[[Sequence[Any]], Mapping[str, str]]


@dataclass(frozen=True)
class ExportedComponents:
    strategy: ComponentSpecMap
    indicators: tuple[ComponentSpecMap, ...]
    source_hashes: Mapping[str, str]
    lookback_bars: int = 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("export", help="Export a locked config as an execution bundle")
    parser.add_argument("--config", required=True, help="Path to locked run YAML")
    parser.add_argument("--out", help="Output directory for the wheel")
    parser.set_defaults(handler=handle_export, command_name="export")


def handle_export(args: argparse.Namespace, **streams: Any) -> int:
    try:
        out_dir = _default_bundle_dir() if args.out is None else Path(args.out)
        wheel_path = export_locked_bundle(Path(args.config), out_dir=out_dir)
    except ConfigValidationError as error:
        raise ConfigCliError(str(error)) from error
    except CliError:
        raise
    except Exception as error:
        raise ExecutionFailureError(str(error)) from error
    return write_success(
        CommandResult(
            command="export",
            payload={
                "wheel": str(wheel_path),
                "install": f"uv add {wheel_path}",
            },
        ),
        **streams,
    )


def export_locked_bundle(
    config_path: Path, *, out_dir: Path, figi_resolver: FigiResolver | None = None
) -> Path:
    component_registry = discover_component_registry()
    resolved = load_run_config(config_path, component_registry=component_registry)
    config = resolved.config
    if config.lock is None:
        raise ConfigCliError(
            "aerd export requires a Lock. This config has no `lock:`, so its "
            "parameters resolve to no single scored Candidate — an optimization "
            "sweep defines a search over many candidates, not one. Pin a "
            "published result with `lock: run_id[:role]` and re-run export."
        )
    with CandidateStore(candidate_store_path(config)) as store:
        lock_run = resolve_lock_run(config.lock, store=store)
    # Resolve the canonical cross-boundary identity once, before any artifact is
    # written: a fail-closed FIGI resolution must stop the export with no wheel.
    resolver = resolve_symbol_figis if figi_resolver is None else figi_resolver
    figi_by_ticker = resolver(config.data.symbols)
    refs = _instrument_refs(config.data, figi_by_ticker)
    strategy_definition = component_registry.get(
        ComponentSelection("strategies", config.strategy.id)
    )
    strategy_manifest = _strategy_manifest(strategy_definition)
    strategy_id = strategy_definition.id
    candidate_key = lock_run.candidate_key
    version = strategy_manifest.version
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate_prefix = _unique_candidate_prefix(
        strategy_id=strategy_id, candidate_key=candidate_key, out_dir=out_dir
    )
    dist_name = _distribution_name(strategy_id, candidate_prefix)
    package_name = _package_name(strategy_id, candidate_prefix)
    # The wheel advertises itself under its own filename: that is the
    # content-addressed handle a Book Config sleeve references, and the
    # aegis-trader registry resolves the bundle by an entry point of that name.
    wheel_filename = f"{_wheel_safe(dist_name)}-{version}-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="aegis-export-") as tmp:
        root = Path(tmp)
        package_dir = root / package_name
        package_dir.mkdir()
        components = _write_component_modules(
            package_dir=package_dir,
            package_name=package_name,
            config=config,
            component_registry=component_registry,
            component_params=lock_run.component_params,
        )
        manifest = {
            "run_id": lock_run.run_id,
            "role": _manifest_role(config.lock.candidate_id),
            "candidate_key": candidate_key,
            "component_source_hashes": components.source_hashes,
            "refs": refs,
        }
        contract = _bundle_contract(config, components, figi_by_ticker)
        plan = {
            "strategy": components.strategy,
            "indicators": components.indicators,
            "gross_cap": config.portfolio.gross_cap,
            "net_cap": config.portfolio.net_cap,
            "direction": config.portfolio.direction,
            "symbols": tuple(config.data.tickers),
            "currency_by_symbol": dict(config.data.currency_by_symbol),
        }
        _write_bundle_module(
            package_dir / "__init__.py",
            contract=contract,
            manifest=manifest,
            plan=plan,
        )
        (package_dir / "bundle_manifest.json").write_text(
            json.dumps(
                {
                    "contract": _jsonable(contract),
                    "manifest": _jsonable(manifest),
                    "plan": _jsonable(plan),
                },
                indent=2,
                sort_keys=True,
            )
        )
        dist_info = root / f"{_wheel_safe(dist_name)}-{version}.dist-info"
        dist_info.mkdir()
        _write_dist_info(
            dist_info,
            dist_name=dist_name,
            version=version,
            entry_point_name=wheel_filename,
            entry_point_value=f"{package_name}:get_bundle",
        )
        wheel_path = out_dir / wheel_filename
        _write_wheel(root, wheel_path)
    return wheel_path


def _write_component_modules(
    *,
    package_dir: Path,
    package_name: str,
    config: RunConfig,
    component_registry: FrozenComponentRegistry,
    component_params: ResolvedComponentParams,
) -> ExportedComponents:
    indicator_specs: list[ComponentSpecMap] = []
    hashes: dict[str, str] = {}
    lookback_bars: int = 0

    for position, ref in enumerate(config.indicators):
        module_name = f"indicator_{position}"
        definition = _copy_component_module(
            package_dir=package_dir,
            filename=f"{module_name}.py",
            component_registry=component_registry,
            selection=ComponentSelection("indicators", ref.id),
        )
        if not definition.has_lookback:
            raise ValueError(
                f"indicator {definition.id!r} lacks lookback() entrypoint; "
                f"every bundled component must declare its warmup bars"
            )
        indicator_manifest = _indicator_manifest(definition)
        component_ref = ComponentRef("indicators", definition.id, ref.id)
        params = dict(component_params[component_ref])
        lb = _call_lookback(definition, params)
        lookback_bars = max(lookback_bars, lb)
        indicator_specs.append(
            _component_spec(
                manifest=indicator_manifest,
                module=f"{package_name}.{module_name}",
                params=params,
            )
        )
        hashes[f"indicators/{definition.id}"] = definition.identity.source_hash

    definition = _copy_component_module(
        package_dir=package_dir,
        filename="strategy.py",
        component_registry=component_registry,
        selection=ComponentSelection("strategies", config.strategy.id),
    )
    if not definition.has_lookback:
        raise ValueError(
            f"strategy {definition.id!r} lacks lookback() entrypoint; "
            f"every bundled component must declare its warmup bars"
        )
    strategy_manifest = _strategy_manifest(definition)
    component_ref = ComponentRef("strategies", definition.id, STRATEGY_SLOT)
    params = dict(component_params[component_ref])
    lb = _call_lookback(definition, params)
    lookback_bars = max(lookback_bars, lb)
    strategy_spec = _component_spec(
        manifest=strategy_manifest,
        module=f"{package_name}.strategy",
        params=params,
    )
    hashes[f"strategies/{definition.id}"] = definition.identity.source_hash
    return ExportedComponents(
        strategy=strategy_spec,
        indicators=tuple(indicator_specs),
        source_hashes=hashes,
        lookback_bars=lookback_bars,
    )


def _copy_component_module(
    *,
    package_dir: Path,
    filename: str,
    component_registry: FrozenComponentRegistry,
    selection: ComponentSelection,
) -> ComponentDefinition:
    definition = component_registry.get(selection)
    shutil.copyfile(definition.file_path, package_dir / filename)
    return definition


def _indicator_manifest(definition: ComponentDefinition) -> IndicatorManifest:
    manifest = definition.manifest
    if not isinstance(manifest, IndicatorManifest):
        raise TypeError(f"component {definition.id!r} is not an indicator")
    return manifest


def _strategy_manifest(definition: ComponentDefinition) -> StrategyManifest:
    manifest = definition.manifest
    if not isinstance(manifest, StrategyManifest):
        raise TypeError(f"component {definition.id!r} is not a strategy")
    return manifest


def _component_spec(
    *,
    manifest: IndicatorManifest | StrategyManifest,
    module: str,
    params: Mapping[str, Any],
) -> ComponentSpecMap:
    return {
        "family": manifest.family,
        "component_id": manifest.id,
        "module": module,
        "input_names": tuple(manifest.input_names),
        "output_names": tuple(manifest.output_names),
        "params": dict(params),
    }


def _bundle_contract(
    config: RunConfig, components: ExportedComponents, figi_by_ticker: Mapping[str, str]
) -> dict[str, Any]:
    currency_by_symbol = config.data.currency_by_symbol
    base_currency = config.portfolio.base_currency
    return {
        "refs": _instrument_refs(config.data, figi_by_ticker),
        "required_arrays": tuple(_required_arrays(components)),
        "base_currency": base_currency,
        "required_fx_currencies": tuple(
            sorted(required_fx_currencies(currency_by_symbol, base_currency))
        ),
        "timeframe": config.data.timeframe,
        "lookback_bars": components.lookback_bars,
    }


def _instrument_refs(data_config: Any, figi_by_ticker: Mapping[str, str]) -> tuple[ListedRef | FuturesRef, ...]:
    refs: list[ListedRef | FuturesRef] = []
    for symbol in data_config.symbols:
        if getattr(symbol, "is_future", False):
            dataset = symbol.dataset or data_config.dataset
            if dataset is None:
                raise ValueError(f"dataset is required for futures symbol {symbol.root!r}")
            refs.append(
                FuturesRef(
                    root=symbol.root,
                    dataset=dataset,
                    roll_rule=symbol.roll_rule,
                    adjustment=symbol.adjustment,
                )
            )
            continue
        refs.append(ListedRef(figi_by_ticker[symbol.symbol_name]))
    return tuple(refs)


def _call_lookback(definition: ComponentDefinition, params: Mapping[str, Any]) -> int:
    lookback_fn = definition.load_lookback()
    result = lookback_fn(**params)
    if not isinstance(result, int) or result < 0:
        raise ValueError(
            f"component {definition.id!r} lookback() must return a non-negative int; "
            f"got {result!r}"
        )
    return result


def _write_bundle_module(
    path: Path,
    *,
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    path.write_text(
        dedent(
            f"""
            from aegis_runtime import (
                BundleManifest,
                ComponentSpec,
                DataContract,
                ExecutionBundle,
                FuturesRef,
                ListedRef,
                LockedExecutionPlan,
                MarketDataBundle,
            )

            CONTRACT = {contract!r}
            MANIFEST = {manifest!r}
            PLAN = {plan!r}

            def _component_spec(value):
                return ComponentSpec(**value)

            def get_bundle():
                plan = dict(PLAN)
                plan['strategy'] = _component_spec(plan['strategy'])
                plan['indicators'] = tuple(_component_spec(item) for item in plan['indicators'])
                return ExecutionBundle(
                    contract=DataContract(**CONTRACT),
                    manifest=BundleManifest(**MANIFEST),
                    plan=LockedExecutionPlan(**plan),
                )

            bundle = get_bundle()
            __all__ = ['ExecutionBundle', 'MarketDataBundle', 'bundle', 'get_bundle']
            """
        ).lstrip()
    )


def _write_dist_info(
    dist_info: Path,
    *,
    dist_name: str,
    version: str,
    entry_point_name: str,
    entry_point_value: str,
) -> None:
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\n"
        f"Name: {dist_name}\n"
        f"Version: {version}\n"
        "Summary: Aegis locked execution bundle\n"
        "Requires-Dist: aegis-runtime\n"
    )
    wheel_metadata = "\n".join(
        [
            "Wheel-Version: 1.0",
            "Generator: aegis-rd-export",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
        ]
    )
    (dist_info / "WHEEL").write_text(f"{wheel_metadata}\n")
    (dist_info / "entry_points.txt").write_text(
        f"[{ENTRY_POINT_GROUP}]\n{entry_point_name} = {entry_point_value}\n"
    )


def _write_wheel(root: Path, wheel_path: Path) -> None:
    rows: list[tuple[str, str, str]] = []
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "RECORD")
    record_path = next(path for path in root.rglob("*.dist-info") if path.is_dir()) / "RECORD"
    for file_path in files:
        relative = file_path.relative_to(root).as_posix()
        data = file_path.read_bytes()
        rows.append(
            (relative, f"sha256={_urlsafe_b64(hashlib.sha256(data).digest())}", str(len(data)))
        )
    rows.append((record_path.relative_to(root).as_posix(), "", ""))
    with record_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
            zf.write(file_path, file_path.relative_to(root).as_posix())


def _required_arrays(components: ExportedComponents) -> tuple[str, ...]:
    names: list[str] = []
    for spec in (*components.indicators, components.strategy):
        for name in spec["input_names"]:
            if name not in names:
                names.append(name)
    if "Close" not in names:
        names.append("Close")
    return tuple(names)


def _default_bundle_dir() -> Path:
    cwd = Path.cwd().resolve(strict=False)
    for parent in (cwd, *cwd.parents):
        if (parent / "CONTEXT-MAP.md").exists() and (parent / "aegis-rd").exists():
            return parent / "bundles"
    return cwd / "bundles"


def _distribution_name(strategy_id: str, candidate_prefix: str) -> str:
    return f"aegis-exec-{_slug(strategy_id)}-{candidate_prefix}"


def _package_name(strategy_id: str, candidate_prefix: str) -> str:
    return f"aegis_exec_{_module_slug(strategy_id)}_{candidate_prefix}"


def _unique_candidate_prefix(*, strategy_id: str, candidate_key: str, out_dir: Path) -> str:
    existing_owners = _existing_bundle_owners(strategy_id=strategy_id, out_dir=out_dir)
    minimum_length = min(8, len(candidate_key))
    for length in range(minimum_length, len(candidate_key) + 1):
        prefix = candidate_key[:length]
        package_name = _package_name(strategy_id, prefix)
        existing_owner = existing_owners.get(package_name)
        if existing_owner is None or existing_owner == candidate_key:
            return prefix
    raise ValueError(f"candidate key {candidate_key!r} cannot be uniquely abbreviated")


def _existing_bundle_owners(*, strategy_id: str, out_dir: Path) -> dict[str, str]:
    owners: dict[str, str] = {}
    wheel_name_prefix = _wheel_safe(_distribution_name(strategy_id, ""))
    for wheel_path in sorted(out_dir.glob(f"{wheel_name_prefix}*.whl")):
        owner = _bundle_owner(wheel_path)
        if owner is not None:
            package_name, candidate_key = owner
            owners[package_name] = candidate_key
    return owners


def _bundle_owner(wheel_path: Path) -> tuple[str, str] | None:
    with zipfile.ZipFile(wheel_path) as zf:
        names = zf.namelist()
        packages = sorted(name.split("/")[0] for name in names if name.endswith("__init__.py"))
        manifest_paths = [name for name in names if name.endswith("bundle_manifest.json")]
        if not packages or not manifest_paths:
            return None
        manifest = json.loads(zf.read(manifest_paths[0]))
    candidate_key = manifest.get("manifest", {}).get("candidate_key")
    if not isinstance(candidate_key, str):
        return None
    return packages[0], candidate_key


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _module_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()


def _wheel_safe(value: str) -> str:
    return value.replace("-", "_")


def _manifest_role(candidate_id: str) -> str:
    return candidate_id if candidate_id in LOCK_ROLES else "candidate_key"


def _urlsafe_b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "public"):
        return value.public()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value
