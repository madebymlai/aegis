# %% component overview
# Fixed short-duration corporate-credit income allocation. The Run Config chooses
# either the EUR-hedged pair or its matched unhedged control; this Strategy only
# emits their preregistered, fully invested 50/50 target.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.static_short_credit",
    "version": "1.0.0",
    "input_names": ["Close"],
    "output_name": "target_weights",
    "owns_portfolio": False,
}

_HEDGED_PAIR = frozenset({"CBUS5E.XBRU", "STEA.LSEETF"})
_HEDGED_FALLBACK_PAIR = frozenset({"CBUS5E.XBRU", "STHE.LSEETF"})
_UNHEDGED_CONTROL_PAIR = frozenset({"SDIG.LSEETF", "SDHY.LSEETF"})
_SUPPORTED_PAIRS = frozenset({_HEDGED_PAIR, _HEDGED_FALLBACK_PAIR, _UNHEDGED_CONTROL_PAIR})


class UnsupportedStaticCreditPairError(ValueError):
    """The run config combined instruments outside a preregistered pair."""


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Emit one fully invested equal-weight target for the two credit roles."""

    close = inputs.data.array("Close")
    pair = frozenset(str(column) for column in close.columns)
    if pair not in _SUPPORTED_PAIRS or len(close.columns) != 2:
        raise UnsupportedStaticCreditPairError(
            f"demeter.static_short_credit: unsupported instrument pair {sorted(pair)!r}"
        )
    periods = len(close)
    return np.full((periods, n_candidates * inputs.n_symbols), 0.5, dtype=float)
