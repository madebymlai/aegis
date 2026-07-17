import json
from datetime import date

from _prototyping.merger.shadow import SecApiSource

_FILING = {
    "accessionNo": "0000000001-26-000001",
    "cik": "1",
    "companyName": "Deal One, Inc.",
    "ticker": "D01",
    "filedAt": "2026-01-03T12:00:00+00:00",
    "formType": "8-K",
    "linkToFilingDetails": "https://example.test/d01",
    "items": ["1.01"],
    "documentFormatFiles": [{"type": "EX-2.1"}],
}
_SUBMISSION = b"""<SEC-DOCUMENT>
<DOCUMENT><TYPE>8-K<TEXT>
Deal One entered into a definitive merger agreement. Each share will receive
$10.20 per share in cash, without interest.
</TEXT></DOCUMENT>
<DOCUMENT><TYPE>EX-2.1<TEXT>
AGREEMENT AND PLAN OF MERGER dated as of January 2, 2026.
Each share shall be converted into the right to receive $10.20 per share in cash.
</TEXT></DOCUMENT>
</SEC-DOCUMENT>"""


class _AvailableTransport:
    def query(self, request: bytes) -> bytes:
        return json.dumps({"filings": [_FILING], "total": {"value": 1}}).encode()

    def submission(self, cik: str, accession: str) -> bytes:
        return _SUBMISSION


class _UnavailableTransport:
    def query(self, request: bytes) -> bytes:
        raise RuntimeError("network unavailable")

    def submission(self, cik: str, accession: str) -> bytes:
        raise RuntimeError("network unavailable")


class _UnrelatedTerminationTransport:
    def query(self, request: bytes) -> bytes:
        query = json.loads(request)["query"]
        filings = (
            []
            if "documentFormatFiles.type" in query
            else [
                {
                    "accessionNo": "0000000001-26-000002",
                    "cik": "1",
                    "companyName": "Deal One, Inc.",
                    "ticker": "D01",
                    "filedAt": "2026-02-03T12:00:00+00:00",
                    "formType": "8-K",
                    "linkToFilingDetails": "https://example.test/unrelated",
                    "items": ["1.02"],
                    "documentFormatFiles": [],
                }
            ]
        )
        return json.dumps({"filings": filings, "total": {"value": len(filings)}}).encode()

    def submission(self, cik: str, accession: str) -> bytes:
        return b"""<SEC-DOCUMENT><DOCUMENT><TYPE>8-K<TEXT>
        Item 1.02. The company terminated an unrelated parking purchase agreement.
        </TEXT></DOCUMENT></SEC-DOCUMENT>"""


class _ReplacementTransport:
    def query(self, request: bytes) -> bytes:
        filing = {
            "accessionNo": "0000000001-26-000003",
            "cik": "1",
            "companyName": "Deal One, Inc.",
            "ticker": "D01",
            "filedAt": "2026-02-18T12:00:00+00:00",
            "formType": "8-K",
            "linkToFilingDetails": "https://example.test/replacement",
            "items": ["1.01", "1.02"],
            "documentFormatFiles": [{"type": "EX-2.1"}],
        }
        return json.dumps({"filings": [filing], "total": {"value": 1}}).encode()

    def submission(self, cik: str, accession: str) -> bytes:
        return b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The Agreement and Plan of Merger dated as of January 2, 2026 was terminated.
        Deal One entered into a different merger agreement under which each share
        will receive $11.00 per share in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of February 17, 2026.
        Each share shall be converted into the right to receive $11.00 per share in cash.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>"""


class _AmendmentTransport:
    def query(self, request: bytes) -> bytes:
        filing = {
            **_FILING,
            "accessionNo": "0000000001-26-000004",
            "filedAt": "2026-02-20T12:00:00+00:00",
            "linkToFilingDetails": "https://example.test/amendment",
        }
        return json.dumps({"filings": [filing], "total": {"value": 1}}).encode()

    def submission(self, cik: str, accession: str) -> bytes:
        return b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        Deal One amended its merger agreement. Each share will receive
        $10.40 per share in cash, without interest.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AMENDMENT TO AGREEMENT AND PLAN OF MERGER dated as of January 2, 2026.
        Each share shall be converted into the right to receive $10.40 per share in cash.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>"""


class _PaginatedTransport:
    def __init__(self) -> None:
        self.requests = 0

    def query(self, request: bytes) -> bytes:
        payload = json.loads(request)
        if "documentFormatFiles.type" not in payload["query"]:
            return json.dumps({"filings": [], "total": {"value": 0}}).encode()
        self.requests += 1
        offset = int(payload["from"])
        filings = []
        if offset == 0:
            filings = [
                {
                    **_FILING,
                    "accessionNo": f"0000000001-26-{number:06d}",
                    "ticker": f"D{number:02d}",
                }
                for number in range(1, 51)
            ]
        elif offset == 50:
            filings = [
                {
                    **_FILING,
                    "accessionNo": "0000000001-26-000051",
                    "ticker": "D51",
                }
            ]
        return json.dumps({"filings": filings, "total": {"value": 51}}).encode()

    def submission(self, cik: str, accession: str) -> bytes:
        return _SUBMISSION


class _AnnouncedAndCompletedTransport:
    def query(self, request: bytes) -> bytes:
        query = json.loads(request)["query"]
        if "documentFormatFiles.type" in query:
            filings = [_FILING]
        else:
            filings = [
                _FILING,
                {
                    **_FILING,
                    "accessionNo": "0000000001-26-000005",
                    "filedAt": "2026-01-09T12:00:00+00:00",
                    "linkToFilingDetails": "https://example.test/completion",
                    "items": ["2.01"],
                    "documentFormatFiles": [],
                },
            ]
        return json.dumps({"filings": filings, "total": {"value": len(filings)}}).encode()

    def submission(self, cik: str, accession: str) -> bytes:
        if accession == _FILING["accessionNo"]:
            return _SUBMISSION
        return b"""<SEC-DOCUMENT><DOCUMENT><TYPE>8-K<TEXT>
        On January 9, 2026, the company completed the merger contemplated by the
        Agreement and Plan of Merger dated as of January 2, 2026.
        </TEXT></DOCUMENT></SEC-DOCUMENT>"""


def test_warm_source_replay_does_not_require_the_network(tmp_path) -> None:
    first_source = SecApiSource(tmp_path, transport=_AvailableTransport())
    first = first_source.refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 3),
        active_events=(),
    )
    warm_source = SecApiSource(tmp_path, transport=_UnavailableTransport())

    replay = warm_source.refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 3),
        active_events=(),
    )

    assert first.observations == replay.observations
    assert replay.observations[0].event_id == "1:0000000001-26-000001"
    assert replay.observations[0].offer_price == 10.20
    assert replay.reviews == ()


def test_unrelated_item_102_cannot_terminate_an_active_merger(tmp_path) -> None:
    active = (
        SecApiSource(tmp_path / "seed", transport=_AvailableTransport())
        .refresh(
            start=date(2026, 1, 3),
            end=date(2026, 1, 3),
            active_events=(),
        )
        .observations[0]
    )
    source = SecApiSource(tmp_path / "audit", transport=_UnrelatedTerminationTransport())

    refresh = source.refresh(
        start=date(2026, 2, 3),
        end=date(2026, 2, 3),
        active_events=(active,),
    )

    assert refresh.observations == ()
    assert refresh.reviews[0].reason == "filing does not identify the active agreement"


def test_replacement_filing_closes_old_event_and_opens_new_event(tmp_path) -> None:
    active = (
        SecApiSource(tmp_path / "seed", transport=_AvailableTransport())
        .refresh(
            start=date(2026, 1, 3),
            end=date(2026, 1, 3),
            active_events=(),
        )
        .observations[0]
    )
    source = SecApiSource(tmp_path / "replacement", transport=_ReplacementTransport())

    refresh = source.refresh(
        start=date(2026, 2, 18),
        end=date(2026, 2, 18),
        active_events=(active,),
    )

    assert refresh.observations[0].event_id == "1:0000000001-26-000001"
    assert refresh.observations[0].status.value == "replaced"
    assert refresh.observations[1].event_id == "1:0000000001-26-000003"
    assert refresh.observations[1].status.value == "announced"


def test_amendment_preserves_the_original_event_identity(tmp_path) -> None:
    active = (
        SecApiSource(tmp_path / "seed", transport=_AvailableTransport())
        .refresh(
            start=date(2026, 1, 3),
            end=date(2026, 1, 3),
            active_events=(),
        )
        .observations[0]
    )
    source = SecApiSource(tmp_path / "amendment", transport=_AmendmentTransport())

    refresh = source.refresh(
        start=date(2026, 2, 20),
        end=date(2026, 2, 20),
        active_events=(active,),
    )

    amended = refresh.observations[0]
    assert amended.event_id == active.event_id
    assert amended.agreement_accession == active.agreement_accession
    assert amended.offer_price == 10.40
    assert amended.status.value == "amended"


def test_source_fetches_every_reported_query_page(tmp_path) -> None:
    transport = _PaginatedTransport()
    source = SecApiSource(tmp_path, transport=transport)

    refresh = source.refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 3),
        active_events=(),
    )

    assert len(refresh.observations) == 51
    assert transport.requests == 2


def test_cold_catchup_observes_a_completion_after_an_announcement_in_the_same_window(
    tmp_path,
) -> None:
    source = SecApiSource(tmp_path, transport=_AnnouncedAndCompletedTransport())

    refresh = source.refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 9),
        active_events=(),
    )

    assert tuple(observation.status.value for observation in refresh.observations) == (
        "announced",
        "completed",
    )
