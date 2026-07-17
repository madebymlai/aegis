"""Conservative point-in-time closing guidance and outside-date observations.

This is prototype code.  It intentionally accepts only unambiguous date language
from target 8-K text already returned by Massive.  A missed observation falls
back to the empirical timing prior; an ambiguous observation must never acquire
false precision.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Literal

import pandas as pd

from cash_merger.census import CashMergerDeal

TimingPrecision = Literal["day", "quarter", "half", "year", "coarse"]
GuidanceState = Literal["unguided", "before_guidance", "in_guidance", "stale_guidance"]

_MONTH = (
    r"January|February|March|April|May|June|July|August|September|October|"
    r"November|December"
)
_DATE = re.compile(
    rf"\b(?P<month>{_MONTH})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+"
    r"(?P<year>20\d{2})\b",
    re.I,
)
_GUIDANCE_VERB = re.compile(
    r"\b(?:currently\s+)?(?:expect(?:s|ed)?|anticipat(?:e|es|ed)|target(?:s|ed)?)\b"
    r".{0,90}?\b(?:close|closing|complete|completed|completion|consummate|consummated)\b",
    re.I,
)
_DEAL_NOUN = re.compile(r"\b(?:merger|transaction|acquisition|offer)\b", re.I)
_IRRELEVANT = re.compile(
    r"\b(?:PIPE financing|equity award|restricted stock|stock option|compensation|"
    r"financial results|earnings|dividend)\b",
    re.I,
)
_QUARTER = re.compile(
    r"\b(?:the\s+)?(?P<quarter>first|second|third|fourth|1st|2nd|3rd|4th|Q[1-4])"
    r"\s+(?:calendar\s+)?quarter(?:\s+of)?\s+(?P<year>20\d{2})\b",
    re.I,
)
_HALF = re.compile(
    r"\b(?:the\s+)?(?P<half>first|second|1st|2nd|H[12])\s+half(?:\s+of)?\s+"
    r"(?P<year>20\d{2})\b",
    re.I,
)
_YEAR = re.compile(
    r"\b(?:in|during)\s+(?P<year>20\d{2})\b|"
    r"\b(?:by|before)\s+(?:the\s+)?(?:end|year[- ]end)\s+of\s+(?P<end_year>20\d{2})\b|"
    r"\b(?:by|before)\s+(?:the\s+)?end\s+of\s+(?:the\s+)?year\b",
    re.I,
)
_COARSE = re.compile(
    r"\b(?P<part>early|mid(?:dle)?|late)\s+(?P<year>20\d{2})\b|"
    r"\b(?P<season>spring|summer|fall|autumn|winter)(?:\s+of)?\s+(?P<season_year>20\d{2})\b",
    re.I,
)
_OUTSIDE_ALIAS_TEXT = r"(?:Outside|Termination|End) Date"
_OUTSIDE_DIRECT = (
    re.compile(
        rf"(?P<date>{_DATE.pattern})\s*\(\s*(?:the\s+)?[\"“']?"
        rf"{_OUTSIDE_ALIAS_TEXT}[\"”']?\s*\)",
        re.I,
    ),
    re.compile(
        rf"\b{_OUTSIDE_ALIAS_TEXT}\b.{{0,80}}?"
        rf"(?:means|shall\s+mean|is|will\s+be)\s+(?P<date>{_DATE.pattern})",
        re.I,
    ),
    re.compile(
        rf"\bextend(?:ed|s|ing)?\s+(?:the\s+)?{_OUTSIDE_ALIAS_TEXT}\b"
        rf".{{0,50}}?\b(?:to|until|through)\s+(?P<date>{_DATE.pattern})",
        re.I,
    ),
)
_EXTENDABLE = re.compile(
    r"\b(?:extend|extension|automatically extended|elect to extend|may extend)\b",
    re.I,
)


@dataclass(frozen=True)
class DateInterval:
    start: date
    end: date
    precision: TimingPrecision

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("timing interval ends before it starts")


@dataclass(frozen=True)
class GuidanceObservation:
    deal_id: str
    observed_at: date
    interval: DateInterval
    accession: str
    raw_text: str


@dataclass(frozen=True)
class OutsideDateObservation:
    deal_id: str
    observed_at: date
    outside_date: date
    extendable: bool
    accession: str
    raw_text: str


@dataclass(frozen=True)
class DealTimingState:
    guidance: GuidanceObservation | None
    outside: OutsideDateObservation | None
    guidance_state: GuidanceState


@dataclass(frozen=True)
class DealTimingTape:
    guidance: dict[str, tuple[GuidanceObservation, ...]]
    outside_dates: dict[str, tuple[OutsideDateObservation, ...]]

    def at(self, deal_id: str, today: pd.Timestamp) -> DealTimingState:
        as_of = today.date()
        guidance = _latest_available(self.guidance.get(deal_id, ()), as_of)
        outside = _latest_available(self.outside_dates.get(deal_id, ()), as_of)
        if guidance is None:
            state: GuidanceState = "unguided"
        elif as_of < guidance.interval.start:
            state = "before_guidance"
        elif as_of <= guidance.interval.end:
            state = "in_guidance"
        else:
            state = "stale_guidance"
        return DealTimingState(guidance, outside, state)


def build_timing_tape(
    deals: Iterable[CashMergerDeal],
    filing_rows: Iterable[dict[str, Any]],
) -> DealTimingTape:
    """Extract immutable observations only within each deal's causal lifecycle."""

    rows_by_cik: dict[str, list[dict[str, Any]]] = {}
    for row in filing_rows:
        cik = str(row.get("cik") or "").lstrip("0")
        if cik and row.get("items_text") and row.get("filing_date"):
            rows_by_cik.setdefault(cik, []).append(row)

    guidance: dict[str, tuple[GuidanceObservation, ...]] = {}
    outside_dates: dict[str, tuple[OutsideDateObservation, ...]] = {}
    for deal in deals:
        announced = date.fromisoformat(deal.announced_at[:10])
        resolved = (
            date.fromisoformat(deal.resolved_at[:10])
            if deal.resolved_at is not None
            else date.max
        )
        deal_guidance: list[GuidanceObservation] = []
        deal_outside: list[OutsideDateObservation] = []
        for row in rows_by_cik.get(deal.target_cik, ()):
            observed = date.fromisoformat(str(row["filing_date"]))
            if not announced <= observed <= resolved:
                continue
            accession = str(row.get("accession_number") or "")
            text = _normalize(str(row["items_text"]))
            deal_guidance.extend(
                GuidanceObservation(deal.deal_id, observed, interval, accession, raw)
                for interval, raw in _guidance_candidates(text, observed)
            )
            deal_outside.extend(
                OutsideDateObservation(
                    deal.deal_id, observed, boundary, extendable, accession, raw
                )
                for boundary, extendable, raw in _outside_candidates(text)
            )
        guidance[deal.deal_id] = _deduplicate_guidance(deal_guidance)
        outside_dates[deal.deal_id] = _deduplicate_outside(deal_outside)
    return DealTimingTape(guidance, outside_dates)


def _guidance_candidates(
    text: str, observed: date
) -> tuple[tuple[DateInterval, str], ...]:
    found: list[tuple[DateInterval, str]] = []
    for match in _GUIDANCE_VERB.finditer(text):
        sentence = _sentence_around(text, match.start(), match.end())
        if (
            _DEAL_NOUN.search(sentence) is None
            or _IRRELEVANT.search(sentence) is not None
            or re.search(r"\bnot\s+(?:currently\s+)?expected\b", sentence, re.I)
        ):
            continue
        if (interval := _parse_interval(sentence, observed)) and interval.end >= observed:
            found.append((interval, sentence))
    unique = {(item.start, item.end, item.precision): (item, raw) for item, raw in found}
    # Multiple distinct forecasts in one filing are usually quoted old and new guidance.
    # Refuse to guess which one controls.
    return tuple(unique.values()) if len(unique) == 1 else ()


def _outside_candidates(text: str) -> tuple[tuple[date, bool, str], ...]:
    found: dict[date, tuple[date, bool, str]] = {}
    for pattern in _OUTSIDE_DIRECT:
        for match in pattern.finditer(text):
            date_match = _DATE.search(match.group("date"))
            if date_match is None:
                continue
            boundary = _date_value(date_match)
            window = text[max(0, match.start() - 220) : min(len(text), match.end() + 300)]
            found[boundary] = (boundary, _EXTENDABLE.search(window) is not None, window)
    # An amendment often quotes both old and new dates.  Ambiguity is safer than
    # selecting the latest calendar date and possibly inventing an extension.
    return tuple(found.values()) if len(found) == 1 else ()


def _parse_interval(sentence: str, observed: date) -> DateInterval | None:
    if re.search(r"\bfiscal\b", sentence, re.I):
        return None
    exact = tuple(_DATE.finditer(sentence))
    if len(exact) == 1:
        day = _date_value(exact[0])
        return DateInterval(day, day, "day")
    if match := _QUARTER.search(sentence):
        quarter_name = match.group("quarter").casefold()
        quarter = {"first": 1, "1st": 1, "q1": 1, "second": 2, "2nd": 2,
                   "q2": 2, "third": 3, "3rd": 3, "q3": 3, "fourth": 4,
                   "4th": 4, "q4": 4}[quarter_name]
        year = int(match.group("year"))
        start_month = 3 * (quarter - 1) + 1
        end_month = start_month + 2
        return DateInterval(
            date(year, start_month, 1),
            date(year, end_month, calendar.monthrange(year, end_month)[1]),
            "quarter",
        )
    if match := _HALF.search(sentence):
        half = match.group("half").casefold()
        year = int(match.group("year"))
        return (
            DateInterval(date(year, 1, 1), date(year, 6, 30), "half")
            if half in {"first", "1st", "h1"}
            else DateInterval(date(year, 7, 1), date(year, 12, 31), "half")
        )
    if match := _COARSE.search(sentence):
        year = int(match.group("year") or match.group("season_year"))
        label = (match.group("part") or match.group("season")).casefold()
        bounds = {
            "early": (1, 4), "mid": (5, 8), "middle": (5, 8), "late": (9, 12),
            "spring": (3, 5), "summer": (6, 8), "fall": (9, 11),
            "autumn": (9, 11), "winter": (12, 12),
        }[label]
        end_day = calendar.monthrange(year, bounds[1])[1]
        return DateInterval(date(year, bounds[0], 1), date(year, bounds[1], end_day), "coarse")
    if match := _YEAR.search(sentence):
        year_text = match.group("year") or match.group("end_year")
        year = int(year_text) if year_text else observed.year
        start = max(observed, date(year, 1, 1))
        if start > date(year, 12, 31):
            return None
        return DateInterval(start, date(year, 12, 31), "year")
    return None


def _date_value(match: re.Match[str]) -> date:
    month = datetime.strptime(match.group("month")[:3], "%b").month
    return date(int(match.group("year")), month, int(match.group("day")))


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind(";", 0, start), start - 220)
    right_candidates = [position for mark in (".", ";") if (position := text.find(mark, end)) >= 0]
    right = min(right_candidates, default=min(len(text), end + 260))
    return text[max(0, left + 1) : min(len(text), right + 1)].strip()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _latest_available(observations: Iterable[Any], as_of: date) -> Any | None:
    available = [item for item in observations if item.observed_at < as_of]
    return available[-1] if available else None


def _deduplicate_guidance(
    observations: Iterable[GuidanceObservation],
) -> tuple[GuidanceObservation, ...]:
    unique = {
        (item.observed_at, item.interval.start, item.interval.end): item
        for item in observations
    }
    return tuple(sorted(unique.values(), key=lambda item: (item.observed_at, item.accession)))


def _deduplicate_outside(
    observations: Iterable[OutsideDateObservation],
) -> tuple[OutsideDateObservation, ...]:
    unique = {(item.observed_at, item.outside_date): item for item in observations}
    return tuple(sorted(unique.values(), key=lambda item: (item.observed_at, item.accession)))
