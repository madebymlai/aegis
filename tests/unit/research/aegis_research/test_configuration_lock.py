"""Unit tests for the top-level ``lock:`` Run Config block.

A Run Config may carry a top-level ``lock: {run_id, candidate_id}`` block that
reproduces one prior Candidate. The builder produces a typed ``Lock`` value object;
a malformed/incomplete ``lock:`` fails at validation; and (interim rule) a config that
carries both a top-level ``lock:`` and any per-Component ``params:`` is rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    Lock,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
)


def _write_parameterized_strategy(path: Path) -> None:
    """A strategy whose manifest declares a single ``threshold`` param (values-only target)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized strategy fixture for lock+params tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['threshold'], "
        "'output_name': 'active', 'owns_portfolio': False, "
        "'defaults': {'threshold': 1.0}, 'param_space_callable': 'param_space', "
        "'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% param space\n"
        "def param_space():\n"
        '    """Return the searchable threshold param space."""\n'
        "    return {'threshold': vbt.Param([1.0, 2.0])}\n"
        "\n# %% main compute\n"
        "def run(inputs, *, threshold=1.0):\n"
        '    """Emit a deterministic active allocation frame for fixture runs."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    return close.gt(close.shift(1)).fillna(False).astype(object)\n"
        "\n# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide strategy output."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    return np.full((T, n_candidates * S), np.nan)\n"
    )


@pytest.fixture
def registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    _write_parameterized_strategy(root / "strategies" / "strategy.py")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _raw_config(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "locked_run",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"gross_cap": 1.0},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 40, "offset": 40, "split": 0.5},
                "max_splits": 2,
            },
        },
    }
    raw.update(overrides)
    return raw


def test_builder_produces_typed_lock(registry) -> None:
    resolved = resolve_run_config(
        _raw_config(lock={"run_id": "run-a", "candidate_id": "cand_123"}),
        component_registry=registry,
    )
    assert resolved.config.lock == Lock(run_id="run-a", candidate_id="cand_123")


def test_scalar_lock_defaults_role_to_best(registry) -> None:
    # aegis-rd-6ie: a bare string is the run_id; the role defaults to best, carried
    # in candidate_id as the role keyword (resolved to a candidate_key at run time).
    resolved = resolve_run_config(
        _raw_config(lock="20260527T000603791760Z_etf_momentum"),
        component_registry=registry,
    )
    assert resolved.config.lock == Lock(
        run_id="20260527T000603791760Z_etf_momentum", candidate_id="best"
    )


def test_scalar_lock_carries_explicit_role(registry) -> None:
    resolved = resolve_run_config(
        _raw_config(lock="run-a:median"),
        component_registry=registry,
    )
    assert resolved.config.lock == Lock(run_id="run-a", candidate_id="median")


def test_scalar_lock_unknown_role_fails_validation_with_clear_message(registry) -> None:
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(lock="run-a:bogus"),
            component_registry=registry,
        )
    lock_issues = [issue for issue in excinfo.value.issues if issue.path == "lock"]
    assert lock_issues, "expected a lock validation issue"
    message = lock_issues[0].message
    assert "best" in message and "median" in message and "worst" in message
    assert "bogus" in message


def test_scalar_lock_empty_run_id_fails_validation(registry) -> None:
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(lock=":best"),
            component_registry=registry,
        )
    assert any(
        issue.path == "lock" and "run_id" in issue.message for issue in excinfo.value.issues
    )


def test_config_without_lock_has_none_lock(registry) -> None:
    resolved = resolve_run_config(_raw_config(), component_registry=registry)
    assert resolved.config.lock is None


def test_incomplete_lock_missing_candidate_id_fails_validation(registry) -> None:
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(lock={"run_id": "run-a"}),
            component_registry=registry,
        )
    paths = {issue.path for issue in excinfo.value.issues}
    assert "lock.candidate_id" in paths


def test_malformed_lock_neither_string_nor_mapping_fails_validation(registry) -> None:
    # A scalar string and a mapping are both valid; anything else (here a list) is not.
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(lock=["run-a"]),
            component_registry=registry,
        )
    assert any(issue.path == "lock" for issue in excinfo.value.issues)


def test_lock_unknown_field_fails_validation(registry) -> None:
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(lock={"run_id": "run-a", "candidate_id": "c", "rank": 1}),
            component_registry=registry,
        )
    assert any(issue.path == "lock.rank" for issue in excinfo.value.issues)


def test_lock_with_component_params_is_accepted(registry) -> None:
    # Relaxed from the interim reject rule (slice 396.1): a top-level lock: may now
    # overlay a tuning config. The lock wins; the overridden params: are recorded in
    # Evidence (asserted in the locked-run behaviour tests).
    resolved = resolve_run_config(
        _raw_config(
            lock={"run_id": "run-a", "candidate_id": "cand_123"},
            strategy={"id": "demo.strategy", "params": {"threshold": 2.0}},
        ),
        component_registry=registry,
    )
    assert resolved.config.lock == Lock(run_id="run-a", candidate_id="cand_123")
    assert resolved.config.strategy.params == {"threshold": 2.0}


def test_lock_with_component_params_still_enforces_values_only(registry) -> None:
    # Lock-wins does not relax the values-only contract on params:: an undeclared
    # param name is still rejected even when a top-level lock: is present.
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(
                lock={"run_id": "run-a", "candidate_id": "c"},
                strategy={"id": "demo.strategy", "params": {"not_a_real_param": 1}},
            ),
            component_registry=registry,
        )
    assert any(issue.path == "strategy.params" for issue in excinfo.value.issues)
