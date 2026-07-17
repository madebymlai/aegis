from datetime import date

from _prototyping.merger.shadow import FredDtb3RateSource

_CSV = b"""observation_date,DTB3
2026-07-14,4.10
2026-07-15,.
2026-07-16,4.20
"""


class _Available:
    def fetch(self, start: date, end: date) -> bytes:
        return _CSV


class _Unavailable:
    def fetch(self, start: date, end: date) -> bytes:
        raise OSError("offline")


def test_rate_source_replays_the_latest_causal_observation_offline(tmp_path) -> None:
    live = FredDtb3RateSource(tmp_path, transport=_Available())
    live.latest(as_of=date(2026, 7, 16))
    offline = FredDtb3RateSource(tmp_path, transport=_Unavailable())

    observation = offline.latest(as_of=date(2026, 7, 17))

    assert observation.observed_on == date(2026, 7, 16)
    assert observation.annual_rate == 0.042
