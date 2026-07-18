"""Shared UTC datetime helpers used across ingest and services."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import overload

from dateutil import parser as date_parser


@overload
def ensure_utc(dt: None) -> None: ...


@overload
def ensure_utc(dt: datetime) -> datetime: ...


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Return *dt* as timezone-aware UTC, or None if *dt* is None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_timestamp_utc(value: datetime | str) -> datetime:
    """Parse a datetime or ISO-ish string and return timezone-aware UTC."""
    if isinstance(value, datetime):
        return ensure_utc(value)
    return ensure_utc(date_parser.isoparse(value))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
