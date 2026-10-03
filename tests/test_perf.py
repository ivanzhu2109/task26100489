"""Repeatable timing check for the non-functional requirements.

150 employees, 500 shifts to copy, 1500 other existing shifts:
plan generation and a single-week hours query must each finish
within 200 ms.  Run directly (``python3 tests/perf_check.py``) or
via pytest.
"""

import time
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shiftcopy import Employee, Shift, build_copy_plan, weekly_minutes
from shiftcopy.tzutil import get_zone, local_to_utc

ZONE = "America/New_York"
EMPLOYEES = 150
SOURCE_SHIFTS = 500
OTHER_SHIFTS = 1500
ROUNDS = 5
BUDGET_MS = 200.0

SOURCE_WEEK = date(2026, 1, 5)  # Monday
TARGET_WEEK = date(2026, 1, 12)


def _slot(counter):
    """Deterministic non-overlapping (day, start_hour) per employee."""
    return counter % 7, (counter // 7) * 3


def _make_shifts(prefix, count, week_monday, counters):
    zone = get_zone(ZONE)
    shifts = []
    for i in range(count):
        emp = f"emp{i % EMPLOYEES:03d}"
        day_offset, hour = _slot(counters[emp])
        counters[emp] += 1
        day = week_monday + timedelta(days=day_offset)
        start_local = datetime(day.year, day.month, day.day, hour)
        shifts.append(
            Shift(
                shift_id=f"{prefix}{i}",
                employee_id=emp,
                start_utc=local_to_utc(zone, start_local),
                end_utc=local_to_utc(zone, start_local + timedelta(hours=2)),
            )
        )
    return shifts


def build_dataset():
    employees = [Employee(f"emp{i:03d}") for i in range(EMPLOYEES)]
    counters = {e.employee_id: 0 for e in employees}
    source = _make_shifts("src", SOURCE_SHIFTS, SOURCE_WEEK, counters)
    counters = {e.employee_id: 0 for e in employees}
    other = _make_shifts("oth", OTHER_SHIFTS, date(2026, 2, 2), counters)
    return employees, source + other


def _time_call(fn, rounds=ROUNDS):
    samples = []
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return samples


def run_check():
    employees, shifts = build_dataset()
    gen = _time_call(lambda: build_copy_plan(employees, shifts, [], ZONE, TARGET_WEEK))
    query = _time_call(lambda: weekly_minutes(shifts, ZONE, TARGET_WEEK))
    print(f"plan generation  ms: {[round(s, 2) for s in gen]}")
    print(f"weekly hours     ms: {[round(s, 2) for s in query]}")
    assert max(gen) < BUDGET_MS, f"plan generation too slow: {max(gen):.1f} ms"
    assert max(query) < BUDGET_MS, f"weekly hours query too slow: {max(query):.1f} ms"
    print(f"OK: both under {BUDGET_MS:.0f} ms over {ROUNDS} rounds")


def test_performance_budget():
    run_check()


if __name__ == "__main__":
    run_check()
