"""周工时口径：实际经过分钟数，只累计落在当地周内的部分。"""
from datetime import date, datetime, timezone

import pytest

from shiftcopy import Shift, weekly_hours

UTC = timezone.utc


def u(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


def test_cross_midnight_shift_split_across_local_weeks():
    # 纽约当地 2026-03-08(周日) 22:00 - 2026-03-09(周一) 02:00 (EDT)
    shift = Shift("s1", "e1", u("2026-03-09T02:00"), u("2026-03-09T06:00"))
    prev = weekly_hours("America/New_York", date(2026, 3, 2), [shift])
    curr = weekly_hours("America/New_York", date(2026, 3, 9), [shift])
    assert prev[0].minutes == 120
    assert curr[0].minutes == 120
    assert prev[0].minutes + curr[0].minutes == 240


def test_spring_forward_week_has_no_lost_minutes():
    # 换时周：当地 2026-03-08(周日) 00:00 - 04:00，实际经过 3 小时（跳过 02:00）
    shift = Shift("s1", "e1", u("2026-03-08T05:00"), u("2026-03-08T08:00"))
    (result,) = weekly_hours("America/New_York", date(2026, 3, 2), [shift])
    assert result.minutes == 180


def test_lord_howe_half_hour_fallback_minutes():
    # 豪勋爵岛 2026-04-05 回拨半小时：当地 01:00 - 03:00 实际经过 150 分钟
    shift = Shift("s1", "e1", u("2026-04-04T14:30"), u("2026-04-04T17:00"))
    (result,) = weekly_hours("Australia/Lord_Howe", date(2026, 3, 30), [shift])
    assert result.minutes == 150


def test_shift_outside_week_contributes_zero():
    shift = Shift("s1", "e1", u("2026-03-10T12:00"), u("2026-03-10T14:00"))
    (result,) = weekly_hours("America/New_York", date(2026, 3, 16), [shift])
    assert result.minutes == 0


def test_deterministic_and_employee_filter():
    shifts = [
        Shift("s1", "e1", u("2026-03-10T12:00"), u("2026-03-10T14:00")),
        Shift("s2", "e2", u("2026-03-10T12:00"), u("2026-03-10T13:00")),
    ]
    first = weekly_hours("America/New_York", date(2026, 3, 9), shifts)
    second = weekly_hours("America/New_York", date(2026, 3, 9), shifts)
    assert first == second
    only_e2 = weekly_hours("America/New_York", date(2026, 3, 9), shifts, ["e2"])
    assert [(w.employee_id, w.minutes) for w in only_e2] == [("e2", 60)]


def test_invalid_timezone_and_non_monday_rejected():
    with pytest.raises(ValueError):
        weekly_hours("Asia/Shanghai", date(2026, 3, 9), [])
    with pytest.raises(ValueError):
        weekly_hours("America/New_York", date(2026, 3, 10), [])
