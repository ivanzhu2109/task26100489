"""Generate a copy plan that replicates last week's shifts into a target week.

The whole batch succeeds or fails together; inputs are never mutated.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .hours import weekly_minutes
from .types import CopyPlan, CopyPlanError, OvertimeWarning, Shift
from .tzutil import (
    NonexistentLocalTimeError,
    get_zone,
    local_to_utc,
    week_start_local,
)

MIN_YEAR = 2020
MAX_YEAR = 2035
DEFAULT_CAP_MINUTES = 40 * 60


def _validate_shift(zone, shift: Shift) -> None:
    if shift.start_utc.tzinfo is None or shift.end_utc.tzinfo is None:
        raise ValueError(f"shift {shift.shift_id}: times must be timezone-aware")
    if not shift.start_utc < shift.end_utc:
        raise ValueError(f"shift {shift.shift_id}: start must be before end")
    for ts in (shift.start_utc, shift.end_utc):
        if ts.second or ts.microsecond or ts.minute % 15:
            raise ValueError(f"shift {shift.shift_id}: endpoints must align to 15-minute ticks")
    start_local = shift.start_utc.astimezone(zone).date()
    end_local = shift.end_utc.astimezone(zone).date()
    if end_local != start_local and end_local != start_local + timedelta(days=1):
        raise ValueError(f"shift {shift.shift_id}: local start/end dates must be equal or adjacent")
    for d in (start_local, end_local):
        if not MIN_YEAR <= d.year <= MAX_YEAR:
            raise ValueError(f"shift {shift.shift_id}: local date {d} outside {MIN_YEAR}-{MAX_YEAR}")


def _leave_intervals_utc(zone, leaves):
    """Per-employee sorted list of half-open UTC leave intervals."""
    by_emp = {}
    for leave in leaves:
        if leave.end_date < leave.start_date:
            raise ValueError("leave end_date before start_date")
        day = leave.start_date
        while day <= leave.end_date:
            if not MIN_YEAR <= day.year <= MAX_YEAR:
                raise ValueError(f"leave date {day} outside {MIN_YEAR}-{MAX_YEAR}")
            lo = local_to_utc(zone, datetime(day.year, day.month, day.day))
            nxt = day + timedelta(days=1)
            hi = local_to_utc(zone, datetime(nxt.year, nxt.month, nxt.day))
            by_emp.setdefault(leave.employee_id, []).append((lo, hi))
            day = nxt
    for emp in by_emp:
        by_emp[emp].sort()
    return by_emp


def _check_conflicts(shifts, leave_by_emp) -> None:
    by_emp = {}
    for shift in shifts:
        by_emp.setdefault(shift.employee_id, []).append(shift)
    for emp, emp_shifts in by_emp.items():
        emp_shifts.sort(key=lambda s: (s.start_utc, s.end_utc))
        for prev, nxt in zip(emp_shifts, emp_shifts[1:]):
            if nxt.start_utc < prev.end_utc:
                raise CopyPlanError(
                    f"employee {emp}: shifts {prev.shift_id} and {nxt.shift_id} overlap"
                )
        leaves = leave_by_emp.get(emp, [])
        if not leaves:
            continue
        for shift in emp_shifts:
            for lo, hi in leaves:
                if lo >= shift.end_utc:
                    break
                if hi > shift.start_utc:
                    raise CopyPlanError(
                        f"employee {emp}: shift {shift.shift_id} falls on approved leave"
                    )


def build_copy_plan(
    employees,
    existing_shifts,
    leaves,
    zone_name: str,
    target_week_start: date,
) -> CopyPlan:
    """Copy all shifts whose local start date belongs to the week before
    ``target_week_start`` into the target week.

    Raises CopyPlanError on any DST, overlap, or leave conflict.
    Overtime only produces warnings.
    """
    zone = get_zone(zone_name)
    target_week_start = week_start_local(target_week_start)
    if not MIN_YEAR <= target_week_start.year <= MAX_YEAR:
        raise ValueError(f"target week {target_week_start} outside {MIN_YEAR}-{MAX_YEAR}")
    source_week_start = target_week_start - timedelta(days=7)

    existing_shifts = list(existing_shifts)
    for shift in existing_shifts:
        _validate_shift(zone, shift)
    leave_by_emp = _leave_intervals_utc(zone, leaves)

    source_shifts = [
        s for s in existing_shifts
        if source_week_start <= s.start_utc.astimezone(zone).date() < target_week_start
    ]

    candidates = []
    for src in source_shifts:
        src_start_local = src.start_utc.astimezone(zone)
        src_end_local = src.end_utc.astimezone(zone)
        new_start_naive = src_start_local.replace(tzinfo=None) + timedelta(days=7)
        new_end_naive = src_end_local.replace(tzinfo=None) + timedelta(days=7)
        try:
            new_start = local_to_utc(
                zone, new_start_naive, prefer_utc_offset=src_start_local.utcoffset()
            )
            new_end = local_to_utc(
                zone, new_end_naive, prefer_utc_offset=src_end_local.utcoffset()
            )
        except NonexistentLocalTimeError as exc:
            raise CopyPlanError(
                f"shift {src.shift_id}: copied endpoint falls in a DST gap ({exc})"
            ) from exc
        if new_end <= new_start:
            raise CopyPlanError(
                f"shift {src.shift_id}: copied end is not after its start"
            )
        candidates.append(
            Shift(
                shift_id=f"{src.shift_id}__w{target_week_start.isoformat()}",
                employee_id=src.employee_id,
                start_utc=new_start,
                end_utc=new_end,
            )
        )

    _check_conflicts(existing_shifts + candidates, leave_by_emp)

    caps = {e.employee_id: int(round(e.weekly_hours_cap * 60)) for e in employees}
    weeks = set()
    for cand in candidates:
        first = cand.start_utc.astimezone(zone).date()
        last = (cand.end_utc - timedelta(microseconds=1)).astimezone(zone).date()
        day = week_start_local(first)
        while day <= last:
            weeks.add(day)
            day += timedelta(days=7)

    warnings = []
    all_shifts = existing_shifts + candidates
    for week in sorted(weeks):
        totals = weekly_minutes(all_shifts, zone_name, week)
        for emp, minutes in sorted(totals.items()):
            cap = caps.get(emp, DEFAULT_CAP_MINUTES)
            if minutes > cap:
                warnings.append(
                    OvertimeWarning(
                        employee_id=emp,
                        week_start=week,
                        minutes=minutes,
                        cap_minutes=cap,
                    )
                )

    return CopyPlan(shifts=candidates, warnings=warnings)
