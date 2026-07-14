# %% component overview
# Allocate one strategic Demeter sleeve across two independent loss payers:
# corporate credit receives 80% and catastrophe insurance receives 20%.
# The policy is static; portfolio drift bands, not a market-timing signal,
# decide when a target difference is large enough to trade.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.insurance_credit_income",
    "version": "1.0.0",
    "input_names": ["Close"],
    "output_name": "target_weights",
    "consumes_outputs": ["credit_payer", "insurance_payer"],
    "owns_portfolio": False,
}

_CREDIT_BUDGET = 0.80
_INSURANCE_BUDGET = 0.20
_CREDIT_LEG_COUNT = 2
_INSURANCE_LEG_COUNT = 1


class InvalidConcavePayerLayoutError(ValueError):
    """The consumed payer masks do not match the candidate-major layout."""


class InvalidConcavePayerMembershipError(ValueError):
    """The consumed masks do not describe the required payer membership."""


# %% helpers
def lookback(**params):
    """The static allocation adds no warmup beyond its payer Indicator."""

    return 0


def _validated_masks(inputs, periods, n_candidates):
    expected_shape = (periods, n_candidates * inputs.n_symbols)
    credit = np.asarray(inputs.indicators["credit_payer"], dtype=float)
    insurance = np.asarray(inputs.indicators["insurance_payer"], dtype=float)
    if credit.shape != expected_shape or insurance.shape != expected_shape:
        raise InvalidConcavePayerLayoutError(
            "demeter.insurance_credit_income: payer masks do not match the candidate layout"
        )
    credit = credit.reshape(periods, n_candidates, inputs.n_symbols)
    insurance = insurance.reshape(periods, n_candidates, inputs.n_symbols)
    classified = credit + insurance
    if not (
        np.isin(credit, (0.0, 1.0)).all()
        and np.isin(insurance, (0.0, 1.0)).all()
        and (classified == 1.0).all()
        and (credit.sum(axis=2) == _CREDIT_LEG_COUNT).all()
        and (insurance.sum(axis=2) == _INSURANCE_LEG_COUNT).all()
    ):
        raise InvalidConcavePayerMembershipError(
            "demeter.insurance_credit_income: expected two credit payers and one insurance payer"
        )
    return credit, insurance


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Emit the fixed 80/20 payer policy in candidate-major symbol order."""

    periods = len(inputs.data.array("Close"))
    credit, insurance = _validated_masks(inputs, periods, n_candidates)
    weights = (
        credit * (_CREDIT_BUDGET / _CREDIT_LEG_COUNT)
        + insurance * (_INSURANCE_BUDGET / _INSURANCE_LEG_COUNT)
    )
    return weights.reshape(periods, n_candidates * inputs.n_symbols)
