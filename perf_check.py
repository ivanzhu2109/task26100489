"""可重复运行的耗时检查：150 名员工、500 个待复制班次、1500 个其他存量班次。"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from shiftcopy import Employee, Leave, Shift, generate_copy_plan, weekly_hours

TZ_NAME = "America/New_York"
TZ = ZoneInfo(TZ_NAME)
UTC = timezone.utc
TARGET_WEEK = date(2026, 6, 1)
SOURCE_WEEK = TARGET_WEEK - timedelta(days=7)
EMPLOYEE_COUNT = 150
SOURCE_SHIFT_COUNT = 500
OTHER_SHIFT_COUNT = 1500
LIMIT_MS = 200
RUNS = 5


def local_to_utc(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=TZ).astimezone(UTC)


def build_dataset():
    employees = [Employee(f"emp{i:03d}") for i in range(EMPLOYEE_COUNT)]
    shifts: list[Shift] = []
    # 500 个源周班次：每人 3~4 个，分散在不同工作日 08:00-10:00，互不重叠
    for i in range(EMPLOYEE_COUNT):
        count = 4 if i < SOURCE_SHIFT_COUNT % EMPLOYEE_COUNT else 3
        for j in range(count):
            day = SOURCE_WEEK + timedelta(days=(i + j * 2) % 7)
            start = local_to_utc(day, 8)
            shifts.append(Shift(f"src-{i}-{j}", employees[i].id, start,
                                start + timedelta(hours=2)))
    assert len(shifts) == SOURCE_SHIFT_COUNT
    # 1500 个其他存量班次：目标周及前后各周的 12:00-14:00，与候选不重叠
    for i in range(EMPLOYEE_COUNT):
        for j in range(OTHER_SHIFT_COUNT // EMPLOYEE_COUNT):
            week = TARGET_WEEK + timedelta(weeks=j - 4)
            day = week + timedelta(days=(i + j * 3 + 1) % 7)
            start = local_to_utc(day, 12)
            shifts.append(Shift(f"oth-{i}-{j}", employees[i].id, start,
                                start + timedelta(hours=2)))
    leaves = [Leave(employees[i].id, date(2026, 7, 1), date(2026, 7, 5))
              for i in range(0, EMPLOYEE_COUNT, 10)]
    return employees, shifts, leaves


def measure(fn, runs: int = RUNS) -> float:
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        best = min(best, (time.perf_counter() - start) * 1000)
    return best


def main() -> int:
    employees, shifts, leaves = build_dataset()
    plan_ms = measure(lambda: generate_copy_plan(
        TZ_NAME, TARGET_WEEK, employees, shifts, leaves))
    hours_ms = measure(lambda: weekly_hours(TZ_NAME, TARGET_WEEK, shifts))
    print(f"plan best-of-{RUNS}: {plan_ms:.1f} ms (limit {LIMIT_MS} ms)")
    print(f"hours best-of-{RUNS}: {hours_ms:.1f} ms (limit {LIMIT_MS} ms)")
    ok = plan_ms < LIMIT_MS and hours_ms < LIMIT_MS
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
