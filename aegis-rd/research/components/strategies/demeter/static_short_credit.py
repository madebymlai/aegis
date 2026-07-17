# %% component overview
# Fixed corporate-credit income allocations. The Run Config chooses a
# preregistered two- or four-fund comparator; this Strategy only emits its fully
# invested equal-weight target.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.static_short_credit",
    "version": "1.1.0",
    "input_names": ["Close"],
    "output_name": "target_weights",
    "owns_portfolio": False,
}

_HEDGED_PAIR = frozenset({"CBUS5E.XBRU", "STEA.LSEETF"})
_HEDGED_FALLBACK_PAIR = frozenset({"CBUS5E.XBRU", "STHE.LSEETF"})
_UNHEDGED_CONTROL_PAIR = frozenset({"SDIG.LSEETF", "SDHY.LSEETF"})
_HEDGED_DURATION_COMPARATOR = frozenset(
    {"CBUS5E.XBRU", "LQEE.LSEETF", "STEA.LSEETF", "IHYE.LSEETF"}
)
_SUPPORTED_PORTFOLIOS = frozenset(
    {
        _HEDGED_PAIR,
        _HEDGED_FALLBACK_PAIR,
        _UNHEDGED_CONTROL_PAIR,
        _HEDGED_DURATION_COMPARATOR,
    }
)


class UnsupportedStaticCreditPairError(ValueError):
    """The run config combined instruments outside a preregistered pair."""


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Emit one fully invested equal-weight target for a preregistered comparator."""

    close = inputs.data.array("Close")
    portfolio = frozenset(str(column) for column in close.columns)
    if portfolio not in _SUPPORTED_PORTFOLIOS or len(portfolio) != len(close.columns):
        raise UnsupportedStaticCreditPairError(
            f"demeter.static_short_credit: unsupported instrument pair {sorted(portfolio)!r}"
        )
    periods = len(close)
    target_weight = 1.0 / inputs.n_symbols
    return np.full((periods, n_candidates * inputs.n_symbols), target_weight, dtype=float)
