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
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.aegis_research.cli_support.errors import ConfigCliError, ExecutionFailureError
from research.aegis_research.cli_support.output import CommandResult, write_success
from research.aegis_research.component_registry import (
    ComponentSelection,
    discover_component_registry,
)
from research.aegis_research.component_registry.contracts import IndicatorManifest, StrategyManifest
from research.aegis_research.configuration import LOCK_ROLES, ConfigValidationError, load_run_config
from research.aegis_research.optimization.candidate_publishing import candidate_store_path
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.lock_run import resolve_lock_run
from research.aegis_research.optimization.param_namespace import ComponentRef


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


def export_locked_bundle(config_path: Path, *, out_dir: Path) -> Path:
    component_registry = discover_component_registry()
    resolved = load_run_config(config_path, component_registry=component_registry)
    config = resolved.config
    if config.lock is None:
        raise ValueError("aerd export requires a locked config")
    with CandidateStore(candidate_store_path(config)) as store:
        lock_run = resolve_lock_run(config.lock, store=store)
    strategy_definition = component_registry.get(ComponentSelection("strategies", config.strategy.id))
    strategy_manifest = strategy_definition.manifest
    if not isinstance(strategy_manifest, StrategyManifest):
        raise TypeError(f"component {config.strategy.id!r} is not a strategy")
    strategy_id = strategy_definition.id
    candidate_key = lock_run.candidate_key
    dist_name = _distribution_name(strategy_id, candidate_key)
    package_name = _package_name(strategy_id, candidate_key)
    version = strategy_manifest.version
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aegis-export-") as tmp:
        root = Path(tmp)
        package_dir = root / package_name
        package_dir.mkdir()
        component_specs, component_hashes = _write_component_modules(
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
            "component_source_hashes": component_hashes,
        }
        contract = {
            "symbols": tuple(config.data.tickers),
            "required_arrays": tuple(_required_arrays(component_specs)),
            "base_currency": config.portfolio.base_currency,
            "timeframe": config.data.timeframe,
        }
        plan = {
            "strategy": component_specs["strategy"],
            "indicators": tuple(component_specs["indicators"]),
            "gross_cap": config.portfolio.gross_cap,
            "net_cap": config.portfolio.net_cap,
            "direction": config.portfolio.direction,
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
        _write_dist_info(dist_info, dist_name=dist_name, version=version)
        wheel_path = out_dir / f"{_wheel_safe(dist_name)}-{version}-py3-none-any.whl"
        _write_wheel(root, wheel_path)
    return wheel_path


def _write_component_modules(
    *,
    package_dir: Path,
    package_name: str,
    config: Any,
    component_registry: Any,
    component_params: Mapping[ComponentRef, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, str]]:
    specs: dict[str, Any] = {"indicators": []}
    hashes: dict[str, str] = {}
    for position, ref in enumerate(config.indicators):
        definition = component_registry.get(ComponentSelection("indicators", ref.id))
        manifest = definition.manifest
        if not isinstance(manifest, IndicatorManifest):
            raise TypeError(f"component {ref.id!r} is not an indicator")
        module_name = f"indicator_{position}"
        shutil.copyfile(definition.file_path, package_dir / f"{module_name}.py")
        component_ref = ComponentRef("indicators", definition.id, ref.id)
        spec = _component_spec(
            manifest=manifest,
            module=f"{package_name}.{module_name}",
            params=component_params[component_ref],
        )
        specs["indicators"].append(spec)
        hashes[f"indicators/{definition.id}"] = definition.identity.source_hash

    definition = component_registry.get(ComponentSelection("strategies", config.strategy.id))
    manifest = definition.manifest
    if not isinstance(manifest, StrategyManifest):
        raise TypeError(f"component {config.strategy.id!r} is not a strategy")
    shutil.copyfile(definition.file_path, package_dir / "strategy.py")
    component_ref = ComponentRef("strategies", definition.id, "strategy")
    specs["strategy"] = _component_spec(
        manifest=manifest,
        module=f"{package_name}.strategy",
        params=component_params[component_ref],
    )
    hashes[f"strategies/{definition.id}"] = definition.identity.source_hash
    return specs, hashes


def _component_spec(*, manifest: IndicatorManifest | StrategyManifest, module: str, params: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "family": manifest.family,
        "component_id": manifest.id,
        "module": module,
        "input_names": tuple(manifest.input_names),
        "output_names": tuple(manifest.output_names),
        "params": dict(params),
    }


def _write_bundle_module(
    path: Path,
    *,
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    path.write_text(
        "from aegis_runtime import (\n"
        "    BundleManifest, ComponentSpec, DataContract, ExecutionBundle, LockedExecutionPlan, MarketDataBundle\n"
        ")\n\n"
        f"CONTRACT = {contract!r}\n"
        f"MANIFEST = {manifest!r}\n"
        f"PLAN = {plan!r}\n\n"
        "def _component_spec(value):\n"
        "    return ComponentSpec(**value)\n\n"
        "def get_bundle():\n"
        "    plan = dict(PLAN)\n"
        "    plan['strategy'] = _component_spec(plan['strategy'])\n"
        "    plan['indicators'] = tuple(_component_spec(item) for item in plan['indicators'])\n"
        "    return ExecutionBundle(\n"
        "        contract=DataContract(**CONTRACT),\n"
        "        manifest=BundleManifest(**MANIFEST),\n"
        "        plan=LockedExecutionPlan(**plan),\n"
        "    )\n\n"
        "bundle = get_bundle()\n"
        "__all__ = ['ExecutionBundle', 'MarketDataBundle', 'bundle', 'get_bundle']\n"
    )


def _write_dist_info(dist_info: Path, *, dist_name: str, version: str) -> None:
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\n"
        f"Name: {dist_name}\n"
        f"Version: {version}\n"
        "Summary: Aegis locked execution bundle\n"
        "Requires-Dist: aegis-runtime\n"
    )
    (dist_info / "WHEEL").write_text(
        "Wheel-Version: 1.0\n"
        "Generator: aegis-rd-export\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )


def _write_wheel(root: Path, wheel_path: Path) -> None:
    rows: list[tuple[str, str, str]] = []
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "RECORD")
    record_path = next(path for path in root.rglob("*.dist-info") if path.is_dir()) / "RECORD"
    for file_path in files:
        relative = file_path.relative_to(root).as_posix()
        data = file_path.read_bytes()
        rows.append((relative, f"sha256={_urlsafe_b64(hashlib.sha256(data).digest())}", str(len(data))))
    rows.append((record_path.relative_to(root).as_posix(), "", ""))
    with record_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
            zf.write(file_path, file_path.relative_to(root).as_posix())


def _required_arrays(component_specs: Mapping[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for spec in (*component_specs["indicators"], component_specs["strategy"]):
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


def _distribution_name(strategy_id: str, candidate_key: str) -> str:
    return f"aegis-exec-{_slug(strategy_id)}-{candidate_key[:8]}"


def _package_name(strategy_id: str, candidate_key: str) -> str:
    return f"aegis_exec_{_module_slug(strategy_id)}_{candidate_key[:8]}"


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
