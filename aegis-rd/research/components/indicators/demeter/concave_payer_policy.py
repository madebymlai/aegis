# %% component overview
# Classify the three approved Demeter instruments by the distinct loss event
# that pays their calm-state income. Prices deliberately do not affect this
# strategic policy classification.

# %% imports
import numpy as np
from nautilus_trader.model.identifiers import InstrumentId

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter.concave_payer_policy",
    "version": "1.0.0",
    "input_names": ["Close"],
    "output_names": ["credit_payer", "insurance_payer"],
}

_CREDIT_PAYERS = frozenset(
    {
        InstrumentId.from_str("CBUS5E.XBRU"),
        InstrumentId.from_str("STEA.LSEETF"),
    }
)
_INSURANCE_PAYERS = frozenset({InstrumentId.from_str("CATB.LSEETF")})
_SUPPORTED_UNIVERSE = _CREDIT_PAYERS | _INSURANCE_PAYERS


class UnsupportedConcavePayerUniverseError(ValueError):
    """The run config does not contain the approved independent payer set."""


# %% helpers
def lookback(**params):
    """The strategic payer classification has no price-history warmup."""

    return 0


def _payer_masks(columns):
    instruments = tuple(columns)
    if len(set(instruments)) != len(instruments) or set(instruments) != _SUPPORTED_UNIVERSE:
        raise UnsupportedConcavePayerUniverseError(
            "demeter.concave_payer_policy: unsupported payer universe "
            f"{sorted(map(str, instruments))!r}"
        )
    credit = np.fromiter(
        (instrument in _CREDIT_PAYERS for instrument in instruments),
        dtype=float,
        count=len(instruments),
    )
    insurance = np.fromiter(
        (instrument in _INSURANCE_PAYERS for instrument in instruments),
        dtype=float,
        count=len(instruments),
    )
    return credit, insurance


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Return candidate-major credit and catastrophe-insurance role masks."""

    close = data.array("Close")
    credit, insurance = _payer_masks(close.columns)
    return {
        "credit_payer": np.tile(credit, (len(close), n_candidates)),
        "insurance_payer": np.tile(insurance, (len(close), n_candidates)),
    }
