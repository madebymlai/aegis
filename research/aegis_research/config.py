from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DataConfig:
    source: str = "synthetic"
    symbols: list[str] = field(default_factory=lambda: ["SYN"])
    start: str | None = None
    end: str | None = None
    timeframe: str = "1D"
    path: str | None = None
    seed: int = 42
    rows: int = 750


@dataclass(frozen=True)
class IndicatorConfig:
    returns: list[int] = field(default_factory=lambda: [1, 5, 20])
    moving_average_windows: list[int] = field(default_factory=lambda: [10, 30])
    volatility_windows: list[int] = field(default_factory=lambda: [20])
    rsi_windows: list[int] = field(default_factory=lambda: [14])


@dataclass(frozen=True)
class LabelConfig:
    horizon: int = 5
    threshold: float = 0.0


@dataclass(frozen=True)
class SplitConfig:
    kind: str = "holdout"
    train_size: float = 0.7
    embargo_bars: int = 0
    n: int = 5
    length: str | int | None = "optimize"


@dataclass(frozen=True)
class ModelConfig:
    kind: str = "logistic_regression"
    min_train_samples: int = 100


@dataclass(frozen=True)
class SignalConfig:
    long_threshold: float = 0.55
    exit_threshold: float = 0.50


@dataclass(frozen=True)
class PortfolioConfig:
    init_cash: float = 10_000.0
    fees: float = 0.001
    slippage: float = 0.0005
    size: float = 1.0
    size_type: str = "valuepercent"
    direction: str = "longonly"


@dataclass(frozen=True)
class ReportConfig:
    min_oos_sharpe: float = 0.5
    max_oos_drawdown: float = 0.35
    min_oos_trades: int = 5


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    data: DataConfig = field(default_factory=DataConfig)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    labels: LabelConfig = field(default_factory=LabelConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    output_dir: str = "runs"


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Experiment config must be a mapping: {path}")

    return ExperimentConfig(
        name=raw["name"],
        data=DataConfig(**raw.get("data", {})),
        indicators=IndicatorConfig(**raw.get("indicators", {})),
        labels=LabelConfig(**raw.get("labels", {})),
        split=SplitConfig(**raw.get("split", {})),
        model=ModelConfig(**raw.get("model", {})),
        signals=SignalConfig(**raw.get("signals", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        output_dir=raw.get("output_dir", "runs"),
    )


def to_builtin(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {str(k): to_builtin(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_builtin(v) for v in value]
    return value
