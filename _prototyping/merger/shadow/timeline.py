"""Causal expected-close ranges for pending cash mergers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Protocol


class TimelineMilestoneKind(StrEnum):
    """A dated condition that prevents a merger from closing earlier."""

    SHAREHOLDER_VOTE = "shareholder_vote"
    TENDER_EXPIRATION = "tender_expiration"
    REGULATORY_DECISION = "regulatory_decision"


@dataclass(frozen=True)
class CloseGuidance:
    """The issuer's causally published expected closing window."""

    earliest: str
    latest: str


@dataclass(frozen=True)
class TimelineMilestone:
    """One dated condition known from a public filing."""

    kind: TimelineMilestoneKind
    scheduled_for: str


@dataclass(frozen=True)
class DealTimelineEvidence:
    """Raw dated terms extracted from one causal filing observation."""

    guidance: CloseGuidance | None = None
    outside_date: str | None = None
    milestones: tuple[TimelineMilestone, ...] = ()


@dataclass(frozen=True)
class DealCloseEstimate:
    """The currently knowable close range for one active agreement."""

    announced_at: str
    earliest_close: str
    expected_close: str
    latest_close: str


class TimelineObservation(Protocol):
    @property
    def observed_at(self) -> str: ...

    @property
    def timeline(self) -> DealTimelineEvidence | None: ...


class DealTimeline:
    """Reduce causal filing terms into one expected-close range."""

    def estimate(
        self,
        observations: Iterable[TimelineObservation],
        *,
        as_of: datetime,
    ) -> DealCloseEstimate | None:
        available = tuple(
            observation
            for observation in observations
            if datetime.fromisoformat(observation.observed_at) <= as_of
        )
        if not available:
            return None
        ordered = tuple(sorted(available, key=lambda item: item.observed_at))
        announced_at = ordered[0].observed_at
        guidance = _latest_guidance(ordered)
        outside_date = _latest_outside_date(ordered)
        milestones = tuple(
            date.fromisoformat(milestone.scheduled_for)
            for observation in ordered
            if observation.timeline is not None
            for milestone in observation.timeline.milestones
        )
        today = as_of.date()
        earliest = max((today, *milestones))
        latest: date | None = outside_date
        if guidance is not None:
            earliest = max(earliest, date.fromisoformat(guidance.earliest))
            guided_latest = date.fromisoformat(guidance.latest)
            latest = guided_latest if latest is None else min(latest, guided_latest)
        if latest is None or latest < earliest:
            return None
        expected = earliest + timedelta(days=(latest - earliest).days // 2)
        return DealCloseEstimate(
            announced_at=announced_at,
            earliest_close=earliest.isoformat(),
            expected_close=expected.isoformat(),
            latest_close=latest.isoformat(),
        )


def _latest_guidance(
    observations: tuple[TimelineObservation, ...],
) -> CloseGuidance | None:
    guidance = None
    for observation in observations:
        if observation.timeline is not None and observation.timeline.guidance is not None:
            guidance = observation.timeline.guidance
    return guidance


def _latest_outside_date(
    observations: tuple[TimelineObservation, ...],
) -> date | None:
    outside_date = None
    for observation in observations:
        if observation.timeline is not None and observation.timeline.outside_date is not None:
            outside_date = date.fromisoformat(observation.timeline.outside_date)
    return outside_date
