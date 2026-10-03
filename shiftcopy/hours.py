"""Weekly working-hours computation.

Hours are counted in actually elapsed minutes, attributed to the local
business week (Monday 00:00 to next Monday 00:00) in which they fall.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .types import Shift
from .tzutil import get_zone, local_to_utc


def _minutes_between(start, end) -> int:
    """Whole minutes between two instants, computed without floats."""
    delta = end - start
    return (delta.days * 86400 + delta.seconds) // 60


def week_bounds_utc(zone_name: str, week_start: date):
    """UTC instants for [local Monday 00:00, next local Monday 00:00)."""
    zone = get_zone(zone_name)
    start = local_to_utc(zone, datetime(week_start.year, week_start.month, week_start.day))
    next_monday = week_start + timedelta(days=7)
    end = local_to_utc(zone, datetime(next_monday.year, next_monday.month, next_monday.day))
    return start, end


def weekly_minutes(shifts, zone_name: str, week_start: date) -> dict:
    """Return {employee_id: minutes} for the given local business week.

    Only the portion of each shift falling inside the week is counted.
    """
    week_start_utc, week_end_utc = week_bounds_utc(zone_name, week_start)
    totals = {}
    for shift in shifts:
        lo = max(shift.start_utc, week_start_utc)
        hi = min(shift.end_utc, week_end_utc)
        if hi > lo:
            totals[shift.employee_id] = totals.get(shift.employee_id, 0) + _minutes_between(lo, hi)
    return totals
