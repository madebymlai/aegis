from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class MetricTargetAdapter(Protocol):
    def stats(self, metrics: list[str], **kwargs: Any) -> Any:
        pass

    def metric_inputs(self) -> Mapping[str, Any]:
        pass
