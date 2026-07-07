"""Golden-bytes oracle for ``resolved_config.v1``.

This pins the canonical bytes of the resolved Run Config document for a set of
representative configs. ``resolved_config.v1`` is hash-pinned in the Manifest, so
any change to dataclass fields, defaults, or serialization moves these hashes.

It is the regression guard for the pydantic validation migration (ADR-0012): a
pure structure/validation refactor must keep these bytes byte-identical. A
*deliberate* byte change (e.g. normalizing int→float numeric fields) shows up
here as a failing hash that must be updated in the same commit — never silently.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION, resolve_run_config
from tests.support.research.aegis_research.component_fixtures import write_indicator_component
from tests.support.research.aegis_research.market_data_fixtures import (
    native_data_config_payload,
)

_SPLIT = {"method": "from_rolling", "params": {"length": 20, "split": 0.5}, "max_splits": 10}


def _raw(name: str, portfolio: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": name,
        "data": native_data_config_payload(instruments=["SYN.XNAS"], end="2024-04-30"),
        "portfolio": portfolio,
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {"search": "grid", "split": _SPLIT},
    }


REPRESENTATIVE_CONFIGS: dict[str, dict[str, object]] = {
    "canonical_grid": _raw("canonical_run", {"gross_cap": 1.0, "direction": "longonly"}),
    # integer-literal caps — the case that diverges if numeric fields are coerced to float
    "int_valued_caps": _raw("int_caps", {"gross_cap": 1, "net_cap": 1, "direction": "both"}),
}

# Re-pinned when ``margin_interest_rate`` moved to the first-tier pin (0.0367,
# 2026-07-06 - live-account scale; previously the 1M-blend 0.0324) and again when
# ranking dropped ``min_weight`` for empirical-Bayes shrinkage (parameter-free):
# the resolved document no longer carries the retired knob. Both fields ride
# resolved_config.v1 deliberately, so schema_version stays put while hashes move.
GOLDEN_RESOLVED_CONFIG_HASHES: dict[str, str] = {
    "canonical_grid": "3c9e5d68cb728a20e99702a70aaf151c597434f1930ac7ad14cad1bd1799212e",
    "int_valued_caps": "023f0697e0b7bd47ee0dfb86ea86b299bb90b9ac510cca890c7c5478d4f508ea",
}


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    strategy = root / "strategies" / "strategy.py"
    strategy.parent.mkdir(parents=True, exist_ok=True)
    strategy.write_text(
        "# %% component overview\n# Strategy fixture for the resolved-config oracle.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'output_name': 'active', 'consumes_outputs': ['returns'], "
        "}\n"
        "\n# %% main compute\n"
        "def run(bundle):\n    \"\"\"Fixture strategy, never executed during config resolution.\"\"\"\n"
        "    raise RuntimeError('not executed during config tests')\n"
    )
    return discover_component_registry(root=root, repo_root=tmp_path)


@pytest.mark.parametrize("name", sorted(REPRESENTATIVE_CONFIGS))
def test_resolved_config_bytes_are_pinned(name: str, tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    resolved = resolve_run_config(REPRESENTATIVE_CONFIGS[name], component_registry=registry)
    digest = hashlib.sha256(canonical_json_bytes(resolved.resolved_config_document())).hexdigest()
    assert digest == GOLDEN_RESOLVED_CONFIG_HASHES[name], (
        f"resolved_config.v1 bytes moved for {name!r}; if this change is intended, "
        f"update GOLDEN_RESOLVED_CONFIG_HASHES (it is hash-pinned in the Manifest)."
    )
