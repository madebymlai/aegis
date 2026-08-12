import pandas as pd

from aegis_data.provider import ProviderAnswer


def test_verified_empty_answer_keeps_the_verified_frontier() -> None:
    frontier = pd.Timestamp("2024-01-01", tz="UTC")

    answer = ProviderAnswer.verified((), oldest_verified=frontier)

    assert answer.records == ()
    assert answer.oldest_verified == frontier
    assert answer.is_responsible is True


def test_not_responsible_answer_has_no_records_or_verified_frontier() -> None:
    answer = ProviderAnswer.not_responsible()

    assert answer.records == ()
    assert answer.oldest_verified is None
    assert answer.is_responsible is False
