"""Acceptance tests for the weekly shift copy library."""

from datetime import date, datetime, timedelta, timezone

import pytest

from shiftcopy import (
    CopyPlanError,
    Employee,
    Leave,
    Shift,
    build_copy_plan,
    weekly_minutes,
)
from shiftcopy.tzutil import get_zone, local_to_utc

NY = "America/New_York"
LH = "Australia/Lord_Howe"


def make_shift(shift_id, emp, zone_name, start_local, end_local):
    """Build a Shift from naive local datetimes (test helper)."""
    zone = get_zone(zone_name)
    return Shift(
        shift_id=shift_id,
        employee_id=emp,
        start_utc=local_to_utc(zone, start_local),
        end_utc=local_to_utc(zone, end_local),
    )


def elapsed_minutes(shift):
    delta = shift.end_utc - shift.start_utc
    return (delta.days * 86400 + delta.seconds) // 60


class TestNewYorkSpringForward:
    def test_copy_across_spring_forward_counts_60_minutes(self):
        # Sun 2026-03-01 01:30-03:30 local; DST jump happens 2026-03-08 02:00.
        src = make_shift("s1", "e1", NY, datetime(2026, 3, 1, 1, 30), datetime(2026, 3, 1, 3, 30))
        plan = build_copy_plan([Employee("e1")], [src], [], NY, date(2026, 3, 2))
        assert len(plan.shifts) == 1
        copied = plan.shifts[0]
        assert copied.start_utc.astimezone(get_zone(NY)).replace(tzinfo=None) == datetime(2026, 3, 8, 1, 30)
        assert copied.end_utc.astimezone(get_zone(NY)).replace(tzinfo=None) == datetime(2026, 3, 8, 3, 30)
        assert elapsed_minutes(copied) == 60
        assert copied.employee_id == "e1"

    def test_nonexistent_target_endpoint_fails_whole_batch(self):
        good = make_shift("s1", "e1", NY, datetime(2026, 3, 1, 1, 30), datetime(2026, 3, 1, 2, 0))
        bad = make_shift("s2", "e2", NY, datetime(2026, 3, 1, 1, 30), datetime(2026, 3, 1, 2, 15))
        with pytest.raises(CopyPlanError):
            build_copy_plan([Employee("e1"), Employee("e2")], [good, bad], [], NY, date(2026, 3, 2))


class TestLordHoweHalfHourDst:
    def test_spring_forward_half_hour_utc_and_minutes(self):
        # 2026-10-04 02:00 -> 02:30 (+10:30 -> +11:00). 01:00-03:00 local
        # elapses 90 minutes: UTC 14:30 -> 16:00 on 2026-10-03/04.
        src = make_shift("s1", "e1", LH, datetime(2026, 9, 27, 1, 0), datetime(2026, 9, 27, 3, 0))
        plan = build_copy_plan([Employee("e1")], [src], [], LH, date(2026, 9, 28))
        assert len(plan.shifts) == 1
        copied = plan.shifts[0]
        assert copied.start_utc == datetime(2026, 10, 3, 14, 30, tzinfo=timezone.utc)
        assert copied.end_utc == datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
        assert elapsed_minutes(copied) == 90

    def test_fall_back_half_hour_utc_and_minutes(self):
        # 2026-04-05 02:00 -> 01:30 (+11:00 -> +10:30). 01:00-03:00 local
        # elapses 150 minutes: UTC 14:00 -> 16:30 on 2026-04-04.
        src = make_shift("s1", "e1", LH, datetime(2026, 3, 29, 1, 0), datetime(2026, 3, 29, 3, 0))
        plan = build_copy_plan([Employee("e1")], [src], [], LH, date(2026, 3, 30))
        assert len(plan.shifts) == 1
        copied = plan.shifts[0]
        assert copied.start_utc == datetime(2026, 4, 4, 14, 0, tzinfo=timezone.utc)
        assert copied.end_utc == datetime(2026, 4, 4, 16, 30, tzinfo=timezone.utc)
        assert elapsed_minutes(copied) == 150

    def test_lord_howe_gap_endpoint_fails_batch(self):
        # 2026-10-04 02:15 local does not exist (30-minute gap).
        src = make_shift("s1", "e1", LH, datetime(2026, 9, 27, 1, 45), datetime(2026, 9, 27, 2, 15))
        with pytest.raises(CopyPlanError):
            build_copy_plan([Employee("e1")], [src], [], LH, date(2026, 9, 28))


class TestNewYorkFallBack:
    def test_first_0145_to_second_0115_is_valid_30_minutes(self):
        # 2026-11-01 fall-back: first 01:45 is EDT (UTC-4), second 01:15 EST (UTC-5).
        zone = get_zone(NY)
        edt = timedelta(hours=-4)
        est = timedelta(hours=-5)
        src = Shift(
            shift_id="s1",
            employee_id="e1",
            start_utc=local_to_utc(zone, datetime(2026, 11, 1, 1, 45), prefer_utc_offset=edt),
            end_utc=local_to_utc(zone, datetime(2026, 11, 1, 1, 15), prefer_utc_offset=est),
        )
        assert elapsed_minutes(src) == 30
        assert src.start_utc == datetime(2026, 11, 1, 5, 45, tzinfo=timezone.utc)
        assert src.end_utc == datetime(2026, 11, 1, 6, 15, tzinfo=timezone.utc)

    def test_copying_ambiguous_source_to_normal_week_fails_batch(self):
        # The 30-minute source above copies to 2026-11-08 where 01:45 EST
        # and 01:15 EST give end <= start: the whole batch must fail.
        zone = get_zone(NY)
        edt = timedelta(hours=-4)
        est = timedelta(hours=-5)
        src = Shift(
            shift_id="s1",
            employee_id="e1",
            start_utc=local_to_utc(zone, datetime(2026, 11, 1, 1, 45), prefer_utc_offset=edt),
            end_utc=local_to_utc(zone, datetime(2026, 11, 1, 1, 15), prefer_utc_offset=est),
        )
        with pytest.raises(CopyPlanError):
            build_copy_plan([Employee("e1")], [src], [], NY, date(2026, 11, 2))

    def test_repeated_target_time_prefers_source_offset(self):
        # Source 2026-10-25 00:45-01:45 EDT; target 2026-11-01 01:45 is
        # ambiguous and must resolve to the EDT occurrence (05:45 UTC).
        src = make_shift("s1", "e1", NY, datetime(2026, 10, 25, 0, 45), datetime(2026, 10, 25, 1, 45))
        assert src.start_utc.astimezone(get_zone(NY)).utcoffset() == timedelta(hours=-4)
        plan = build_copy_plan([Employee("e1")], [src], [], NY, date(2026, 10, 26))
        copied = plan.shifts[0]
        assert copied.end_utc == datetime(2026, 11, 1, 5, 45, tzinfo=timezone.utc)
        assert elapsed_minutes(copied) == 60

    def test_repeated_target_time_without_matching_offset_picks_earlier_utc(self):
        # A source endpoint in EST (e.g. created before a hypothetical rule
        # change) has no matching offset among the ambiguous candidates;
        # the earlier UTC instant (EDT occurrence) must be chosen.
        zone = get_zone(NY)
        est = timedelta(hours=-5)
        utc = local_to_utc(zone, datetime(2026, 11, 1, 1, 45), prefer_utc_offset=est)
        assert utc == datetime(2026, 11, 1, 6, 45, tzinfo=timezone.utc)
        no_match = local_to_utc(zone, datetime(2026, 11, 1, 1, 45), prefer_utc_offset=timedelta(hours=2))
        assert no_match == datetime(2026, 11, 1, 5, 45, tzinfo=timezone.utc)


class TestLeaveAndWeeklyHours:
    def test_shift_ending_at_leave_midnight_is_not_a_conflict(self):
        # Cross-week shift Sun 2026-01-04 22:00 -> Mon 2026-01-05 00:00 local.
        # Leave on Monday 01-05 starts exactly when the shift ends: no conflict.
        src = make_shift("s1", "e1", NY, datetime(2026, 1, 4, 22, 0), datetime(2026, 1, 5, 0, 0))
        leave = Leave("e1", date(2026, 1, 5), date(2026, 1, 6))
        plan = build_copy_plan([Employee("e1")], [src], [leave], NY, date(2026, 1, 5))
        assert len(plan.shifts) == 1

    def test_weekly_hours_match_manual_15_minute_attribution(self):
        # Shift Sun 2026-01-04 20:00 -> Mon 2026-01-05 02:00 local (6h).
        # Manual per-15-minute attribution: 16 slots (240 min) in the week
        # starting 2025-12-29, 8 slots (120 min) in the week starting 01-05.
        shift = make_shift("s1", "e1", NY, datetime(2026, 1, 4, 20, 0), datetime(2026, 1, 5, 2, 0))
        before = weekly_minutes([shift], NY, date(2025, 12, 29))
        after = weekly_minutes([shift], NY, date(2026, 1, 5))
        outside = weekly_minutes([shift], NY, date(2026, 1, 12))
        assert before == {"e1": 240}
        assert after == {"e1": 120}
        assert outside == {}

    def test_leave_midnight_boundary_shift_hours_not_lost(self):
        src = make_shift("s1", "e1", NY, datetime(2026, 1, 4, 22, 0), datetime(2026, 1, 5, 0, 0))
        assert weekly_minutes([src], NY, date(2025, 12, 29)) == {"e1": 120}
        assert weekly_minutes([src], NY, date(2026, 1, 5)) == {}

    def test_real_leave_conflict_fails_whole_batch(self):
        good = make_shift("s1", "e1", NY, datetime(2026, 1, 4, 9, 0), datetime(2026, 1, 4, 12, 0))
        bad = make_shift("s2", "e2", NY, datetime(2026, 1, 4, 13, 0), datetime(2026, 1, 4, 16, 0))
        leave = Leave("e2", date(2026, 1, 11), date(2026, 1, 11))
        with pytest.raises(CopyPlanError):
            build_copy_plan([Employee("e1"), Employee("e2")], [good, bad], [leave], NY, date(2026, 1, 5))

    def test_overlap_with_existing_shift_fails_batch(self):
        src = make_shift("s1", "e1", NY, datetime(2026, 1, 4, 9, 0), datetime(2026, 1, 4, 12, 0))
        blocker = make_shift("s2", "e1", NY, datetime(2026, 1, 11, 11, 0), datetime(2026, 1, 11, 13, 0))
        with pytest.raises(CopyPlanError):
            build_copy_plan([Employee("e1")], [src, blocker], [], NY, date(2026, 1, 5))

    def test_touching_shifts_are_allowed(self):
        first = make_shift("s1", "e1", NY, datetime(2026, 1, 4, 9, 0), datetime(2026, 1, 4, 12, 0))
        second = make_shift("s2", "e1", NY, datetime(2026, 1, 4, 12, 0), datetime(2026, 1, 4, 15, 0))
        plan = build_copy_plan([Employee("e1")], [first, second], [], NY, date(2026, 1, 5))
        assert len(plan.shifts) == 2

    def test_overtime_warns_but_does_not_block(self):
        # 5 existing 9h shifts (Mon-Fri, 45h) copy into the target week;
        # the target week total exceeds the 40h cap: warning only.
        employees = [Employee("e1", weekly_hours_cap=40.0)]
        shifts = [
            make_shift(
                f"s{i}", "e1", NY,
                datetime(2025, 12, 29, 9, 0) + timedelta(days=i),
                datetime(2025, 12, 29, 18, 0) + timedelta(days=i),
            )
            for i in range(5)
        ]
        plan = build_copy_plan(employees, shifts, [], NY, date(2026, 1, 5))
        assert len(plan.shifts) == 5
        assert len(plan.warnings) == 1
        warning = plan.warnings[0]
        assert warning.employee_id == "e1"
        assert warning.week_start == date(2026, 1, 5)
        assert warning.minutes == 45 * 60
        assert warning.cap_minutes == 40 * 60

    def test_inputs_are_not_mutated(self):
        src = make_shift("s1", "e1", NY, datetime(2026, 1, 4, 9, 0), datetime(2026, 1, 4, 12, 0))
        shifts = [src]
        build_copy_plan([Employee("e1")], shifts, [], NY, date(2025, 12, 29))
        assert shifts == [src]

    def test_repeatable_results(self):
        src = make_shift("s1", "e1", NY, datetime(2026, 3, 1, 1, 30), datetime(2026, 3, 1, 3, 30))
        first = build_copy_plan([Employee("e1")], [src], [], NY, date(2026, 3, 2))
        second = build_copy_plan([Employee("e1")], [src], [], NY, date(2026, 3, 2))
        assert first.shifts == second.shifts
        assert first.warnings == second.warnings
