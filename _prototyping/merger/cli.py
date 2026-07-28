"""Shared command-line values for merger prototype runners."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, date, datetime
from pathlib import Path


class PrototypeCliError(ValueError):
    """A merger prototype command-line value is malformed."""


def default_state_dir(name: str) -> Path:
    """Return one prototype runtime directory below the configured cache root."""

    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_root / "aegis" / name


def iso_date(value: str) -> date:
    """Parse one command-line ISO date."""

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected an ISO date (YYYY-MM-DD)") from error


def utc_timestamp(value: str | None) -> datetime:
    """Parse an aware timestamp or return the current UTC time."""

    if value is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PrototypeCliError("--as-of must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise PrototypeCliError("--as-of must include a timezone")
    return parsed.astimezone(UTC)
