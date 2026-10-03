"""Timezone helpers for store-local wall-clock handling.

Supported zones: America/New_York and Australia/Lord_Howe.
Business weeks run from local Monday 00:00 to the next Monday 00:00.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SUPPORTED_ZONES = ("America/New_York", "Australia/Lord_Howe")


def get_zone(name: str) -> ZoneInfo:
    """Return the ZoneInfo for a supported store timezone."""
    if name not in SUPPORTED_ZONES:
        raise ValueError(f"unsupported timezone: {name!r}")
    return ZoneInfo(name)


def week_start_local(d: date) -> date:
    """Return the Monday of the business week containing local date ``d``."""
    return d - timedelta(days=d.weekday())


def local_to_utc(zone: ZoneInfo, local_dt: datetime, prefer_utc_offset=None) -> datetime:
    """Convert a naive local datetime to an aware UTC datetime.

    Raises NonexistentLocalTimeError if the wall time is skipped by a DST
    transition.  If the wall time occurs twice (fall-back), prefer the
    candidate whose UTC offset equals ``prefer_utc_offset``; if neither
    matches, pick the earlier UTC instant.
    """
    if local_dt.tzinfo is not None:
        raise ValueError("local_dt must be naive")
    candidates = []
    for fold in (0, 1):
        aware = local_dt.replace(tzinfo=zone, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == local_dt:
            if utc not in candidates:
                candidates.append(utc)
    if not candidates:
        raise NonexistentLocalTimeError(
            f"local time {local_dt} does not exist in {zone.key}"
        )
    if len(candidates) == 1:
        return candidates[0]
    if prefer_utc_offset is not None:
        for utc in candidates:
            if utc.astimezone(zone).utcoffset() == prefer_utc_offset:
                return utc
    return min(candidates)


class NonexistentLocalTimeError(ValueError):
    """The requested local wall time does not exist (DST gap)."""
