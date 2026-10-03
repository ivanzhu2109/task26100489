"""生成下周复制方案：整批校验，全部通过才返回完整候选排班。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .hours import weekly_hours
from .models import CopyPlan, CopyPlanError, Employee, Leave, OverLimitWarning, Shift, WeekHours
from .timeutil import UTC, check_week_start, get_timezone, local_wall, resolve_local, week_bounds_utc


def _validate_shift(tz, shift: Shift) -> None:
    for label, dt in (("start_utc", shift.start_utc), ("end_utc", shift.end_utc)):
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
            raise ValueError(f"班次 {shift.id} 的 {label} 必须是带时区的 UTC 时刻")
        if dt.second or dt.microsecond or dt.minute % 15:
            raise ValueError(f"班次 {shift.id} 的 {label} 必须落在 15 分钟刻度上")
    if not shift.start_utc < shift.end_utc:
        raise ValueError(f"班次 {shift.id} 的开始必须早于结束")
    start_date = local_wall(tz, shift.start_utc).date()
    end_date = local_wall(tz, shift.end_utc).date()
    if (end_date - start_date).days not in (0, 1):
        raise ValueError(f"班次 {shift.id} 的当地开始与结束日期必须相同或相邻")


def _occupied_local_dates(tz, shift: Shift) -> tuple[date, date]:
    """班次实际占用到的当地日期闭区间（结束恰在零点不算占用次日）。"""
    first = shift.start_utc.astimezone(tz).date()
    last = (shift.end_utc - timedelta(microseconds=1)).astimezone(tz).date()
    return first, last


def generate_copy_plan(
    timezone: str,
    target_week_start: date,
    employees: list[Employee],
    existing_shifts: list[Shift],
    leaves: list[Leave],
) -> CopyPlan:
    """把当地开始日期属于上一周的全部班次复制到目标周。"""
    tz = get_timezone(timezone)
    check_week_start(target_week_start)
    source_week_start = target_week_start - timedelta(days=7)
    source_end = source_week_start + timedelta(days=7)

    for shift in existing_shifts:
        _validate_shift(tz, shift)

    emp_limits = {e.id: int(round(e.weekly_hour_limit * 60)) for e in employees}
    leaves_by_emp: dict[str, list[Leave]] = {}
    for leave in leaves:
        leaves_by_emp.setdefault(leave.employee_id, []).append(leave)

    # 1. 选出当地开始日期属于上一周的班次，生成候选。
    reasons: list[str] = []
    candidates: list[Shift] = []
    for src in existing_shifts:
        start_wall = local_wall(tz, src.start_utc)
        if not (source_week_start <= start_wall.date() < source_end):
            continue
        end_wall = local_wall(tz, src.end_utc)
        new_start_wall = start_wall + timedelta(days=7)
        new_end_wall = end_wall + timedelta(days=7)
        start_offset = src.start_utc.astimezone(tz).utcoffset()
        end_offset = src.end_utc.astimezone(tz).utcoffset()
        new_start = resolve_local(tz, new_start_wall, start_offset)
        new_end = resolve_local(tz, new_end_wall, end_offset)
        if new_start is None or new_end is None:
            bad = new_start_wall if new_start is None else new_end_wall
            reasons.append(f"班次 {src.id} 的目标端点 {bad} 落在换时跳过的不存在时刻")
            continue
        if new_end <= new_start:
            reasons.append(f"班次 {src.id} 复制后结束不晚于开始")
            continue
        candidates.append(Shift(
            id=f"{src.id}:copy:{target_week_start.isoformat()}",
            employee_id=src.employee_id,
            start_utc=new_start,
            end_utc=new_end,
        ))

    # 2. 重叠检查：候选 vs 全部存量 + 同批候选（按员工扫描区间）。
    if not reasons:
        intervals_by_emp: dict[str, list[tuple[datetime, datetime, str, bool]]] = {}
        for shift in existing_shifts:
            intervals_by_emp.setdefault(shift.employee_id, []).append(
                (shift.start_utc, shift.end_utc, shift.id, False))
        for cand in candidates:
            intervals_by_emp.setdefault(cand.employee_id, []).append(
                (cand.start_utc, cand.end_utc, cand.id, True))
        for emp_id, intervals in intervals_by_emp.items():
            intervals.sort(key=lambda iv: (iv[0], iv[1]))
            max_end: datetime | None = None
            max_end_id = ""
            for start, end, shift_id, is_candidate in intervals:
                if is_candidate and max_end is not None and max_end > start:
                    reasons.append(f"班次 {shift_id} 与 {max_end_id} 的实际 UTC 区间重叠")
                if max_end is None or end > max_end:
                    max_end, max_end_id = end, shift_id

    # 3. 休假检查：候选实际占用的当地日期不得落在已批准休假内。
    if not reasons:
        for cand in candidates:
            first, last = _occupied_local_dates(tz, cand)
            for leave in leaves_by_emp.get(cand.employee_id, ()):
                if leave.start_date <= last and leave.end_date >= first:
                    reasons.append(
                        f"班次 {cand.id} 占用 {first}~{last}，"
                        f"与休假 {leave.start_date}~{leave.end_date} 冲突")
                    break

    if reasons:
        raise CopyPlanError(reasons)

    # 4. 工时与警告：覆盖候选涉及的每个业务周（存量 + 候选）。
    weeks = {target_week_start}
    next_week = target_week_start + timedelta(days=7)
    next_week_start_utc, _ = week_bounds_utc(tz, next_week)
    for cand in candidates:
        if cand.end_utc > next_week_start_utc:
            weeks.add(next_week)
    all_shifts = list(existing_shifts) + candidates
    emp_ids = sorted(emp_limits)
    hours: list[WeekHours] = []
    warnings: list[OverLimitWarning] = []
    for week in sorted(weeks):
        for wh in weekly_hours(timezone, week, all_shifts, emp_ids):
            hours.append(wh)
            limit = emp_limits.get(wh.employee_id)
            if limit is not None and wh.minutes > limit:
                warnings.append(OverLimitWarning(
                    employee_id=wh.employee_id,
                    week_start=week,
                    minutes=wh.minutes,
                    limit_minutes=limit,
                ))

    candidates.sort(key=lambda s: (s.start_utc, s.id))
    return CopyPlan(shifts=candidates, warnings=warnings, hours=hours)
