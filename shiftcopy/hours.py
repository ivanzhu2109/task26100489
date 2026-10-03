"""周工时计算：按实际经过分钟数，只累计落在该当地周内的部分。"""
from __future__ import annotations

from datetime import date

from .models import Shift, WeekHours
from .timeutil import check_week_start, get_timezone, week_bounds_utc


def weekly_hours(
    timezone: str,
    week_start: date,
    shifts: list[Shift],
    employee_ids: list[str] | None = None,
) -> list[WeekHours]:
    """计算指定当地周内各员工的工时（分钟）。

    只累计班次实际 UTC 区间落在该周内的部分；employee_ids 为 None 时
    覆盖 shifts 中出现的全部员工。"""
    tz = get_timezone(timezone)
    check_week_start(week_start)
    week_start_utc, week_end_utc = week_bounds_utc(tz, week_start)
    if employee_ids is None:
        employee_ids = sorted({s.employee_id for s in shifts})
    totals = {emp_id: 0 for emp_id in employee_ids}
    for shift in shifts:
        if shift.employee_id not in totals:
            continue
        overlap_start = max(shift.start_utc, week_start_utc)
        overlap_end = min(shift.end_utc, week_end_utc)
        if overlap_end > overlap_start:
            seconds = (overlap_end - overlap_start).total_seconds()
            totals[shift.employee_id] += int(seconds // 60)
    return [
        WeekHours(employee_id=emp_id, week_start=week_start, minutes=totals[emp_id])
        for emp_id in sorted(totals)
    ]
