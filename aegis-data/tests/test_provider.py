import pandas as pd

from aegis_data.provider import ProviderAnswer


def test_verified_empty_answer_keeps_the_verified_frontier() -> None:
    frontier = pd.Timestamp("2024-01-01", tz="UTC")

    answer = ProviderAnswer.verified((), oldest_verified=frontier)

    assert answer.records == ()
    assert answer.oldest_verified == frontier
