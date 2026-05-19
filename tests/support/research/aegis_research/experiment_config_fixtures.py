from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.config import ResolvedLaneConfig
from research.aegis_research.configuration.builders import _build_train_lane_config
from research.aegis_research.configuration.secrets import to_builtin
from research.aegis_research.model_registry import FrozenModelRegistry

SYNTHETIC_ML_SCAFFOLD_CONFIG = (
    "tests/support/research/aegis_research/fixtures/experiments/synthetic_ml_scaffold_fixture.yaml"
)
SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG = (
    "tests/support/research/aegis_research/fixtures/experiments/"
    "synthetic_purged_fixlb_scaffold_fixture.yaml"
)


def load_train_fixture_config(
    path: str,
    *,
    model_registry: FrozenModelRegistry,
    output_dir: str | None = None,
    data: dict[str, Any] | None = None,
    split: dict[str, Any] | None = None,
    signals: dict[str, Any] | None = None,
) -> ResolvedLaneConfig:
    raw_text = Path(path).read_text()
    raw = yaml.safe_load(raw_text)
    if output_dir is not None:
        raw["output_dir"] = output_dir
    if data is not None:
        raw["data"] = {**raw.get("data", {}), **data}
    if split is not None:
        train = dict(raw.get("train", {}))
        train["split"] = {**train.get("split", {}), **split}
        raw["train"] = train
    if signals is not None:
        train = dict(raw.get("train", {}))
        train["signals"] = {**train.get("signals", {}), **signals}
        raw["train"] = train
    text_for_hash = yaml.safe_dump(raw, sort_keys=False)
    return ResolvedLaneConfig(
        config=_build_train_lane_config(raw),
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=path,
        model_registry=model_registry,
    )
