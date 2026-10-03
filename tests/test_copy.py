"""复制方案验收：换时、跨周、休假、重叠、加班警告与整批失败。"""
from datetime import date, datetime, timedelta, timezone

import pytest

from shiftcopy import (
    CopyPlanError,
    Employee,
    Leave,
    Shift,
    generate_copy_plan,
)
from shiftcopy.timeutil import get_timezone, resolve_local

UTC = timezone.utc
NY = "America/New_York"
LH = "Australia/Lord_Howe"


def u(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


def test_spring_forward_copy_keeps_wall_clock_and_counts_60_minutes():
    # 当地 2026-03-01 01:30-03:30 (EST) -> 复制到 03-08 跨换时，实际 60 分钟
    src = Shift("s1", "e1", u("2026-03-01T06:30"), u("2026-03-01T08:30"))
    plan = generate_copy_plan(NY, date(2026, 3, 2), [Employee("e1")], [src], [])
    (cand,) = plan.shifts
    assert cand.start_utc == u("2026-03-08T06:30")
    assert cand.end_utc == u("2026-03-08T07:30")
    assert cand.end_utc - cand.start_utc == timedelta(minutes=60)
    hours = {(h.employee_id, h.week_start): h.minutes for h in plan.hours}
    assert hours[("e1", date(2026, 3, 2))] == 60


def test_spring_forward_gap_endpoint_fails_whole_batch():
    # 当地 02:15 在 2026-03-08 不存在；同批另一个正常班次也不得返回
    good = Shift("good", "e1", u("2026-03-01T06:30"), u("2026-03-01T08:30"))
    bad = Shift("bad", "e2", u("2026-03-01T07:15"), u("2026-03-01T08:15"))
    with pytest.raises(CopyPlanError) as exc:
        generate_copy_plan(NY, date(2026, 3, 2),
                           [Employee("e1"), Employee("e2")], [good, bad], [])
    assert any("bad" in r and "不存在时刻" in r for r in exc.value.reasons)


def test_lord_howe_half_hour_spring_forward_exact_interval():
    # 豪勋爵岛 2026-10-04 02:00->02:30 跳过半小时
    # 源：当地 2026-09-27 01:30-03:30 (+10:30) -> 目标 10-04 实际 90 分钟
    src = Shift("s1", "e1", u("2026-09-26T15:00"), u("2026-09-26T17:00"))
    plan = generate_copy_plan(LH, date(2026, 9, 28), [Employee("e1")], [src], [])
    (cand,) = plan.shifts
    assert cand.start_utc == u("2026-10-03T15:00")   # 01:30 +10:30
    assert cand.end_utc == u("2026-10-03T16:30")     # 03:30 +11:00
    assert cand.end_utc - cand.start_utc == timedelta(minutes=90)
    hours = {(h.employee_id, h.week_start): h.minutes for h in plan.hours}
    assert hours[("e1", date(2026, 9, 28))] == 90


def test_lord_howe_gap_endpoint_fails():
    # 源：当地 2026-09-27 02:15-03:15 -> 目标 10-04 02:15 不存在
    src = Shift("s1", "e1", u("2026-09-26T15:45"), u("2026-09-26T16:45"))
    with pytest.raises(CopyPlanError):
        generate_copy_plan(LH, date(2026, 9, 28), [Employee("e1")], [src], [])


def test_lord_howe_fallback_ambiguous_prefers_source_offset():
    # 源：当地 2026-03-29 01:45-02:45 (+11)；目标 04-05 01:45 有两个候选
    src = Shift("s1", "e1", u("2026-03-28T14:45"), u("2026-03-28T15:45"))
    plan = generate_copy_plan(LH, date(2026, 3, 30), [Employee("e1")], [src], [])
    (cand,) = plan.shifts
    assert cand.start_utc == u("2026-04-04T14:45")   # 第一次 01:45 (+11)
    assert cand.end_utc == u("2026-04-04T16:15")     # 02:45 +10:30
    assert cand.end_utc - cand.start_utc == timedelta(minutes=90)


def test_resolve_local_falls_back_to_earliest_utc_without_offset_match():
    tz = get_timezone(LH)
    wall = datetime(2026, 4, 5, 1, 45)
    picked = resolve_local(tz, wall, timedelta(hours=9))  # 不存在的偏移
    assert picked == u("2026-04-04T14:45")                # UTC 较早者 (+11)


def test_fallback_30_minute_source_shift_is_valid_but_copy_fails():
    # 2026-11-01 回拨日：第一次 01:45 (EDT) 到第二次 01:15 (EST)，实际 30 分钟
    src = Shift("s1", "e1", u("2026-11-01T05:45"), u("2026-11-01T06:15"))
    assert src.end_utc - src.start_utc == timedelta(minutes=30)
    # 复制到普通周：当地墙钟 01:45 -> 01:15 结束不晚于开始，整批失败
    with pytest.raises(CopyPlanError) as exc:
        generate_copy_plan(NY, date(2026, 11, 2), [Employee("e1")], [src], [])
    assert any("结束不晚于开始" in r for r in exc.value.reasons)


def test_fallback_ambiguous_target_prefers_source_offset():
    # 源：当地 2026-10-25 01:45-02:45 (EDT, -4)；目标 11-01 01:45 出现两次
    src = Shift("s1", "e1", u("2026-10-25T05:45"), u("2026-10-25T06:45"))
    plan = generate_copy_plan(NY, date(2026, 10, 26), [Employee("e1")], [src], [])
    (cand,) = plan.shifts
    assert cand.start_utc == u("2026-11-01T05:45")   # 第一次 01:45 (EDT)
    assert cand.end_utc == u("2026-11-01T07:45")     # 02:45 EST
    assert cand.end_utc - cand.start_utc == timedelta(hours=2)


def test_cross_week_shift_ending_at_leave_midnight_is_not_a_conflict():
    # 源：当地 2026-03-01(周日) 20:00 - 2026-03-02(周一) 00:00
    src = Shift("s1", "e1", u("2026-03-02T01:00"), u("2026-03-02T05:00"))
    leave = Leave("e1", date(2026, 3, 9), date(2026, 3, 10))
    plan = generate_copy_plan(NY, date(2026, 3, 2), [Employee("e1")], [src], [leave])
    (cand,) = plan.shifts
    assert cand.end_utc == u("2026-03-09T04:00")     # 恰在休假日当地零点结束
    # 周工时与逐 15 分钟人工归属一致：16 个刻度全部落在目标周
    hours = {(h.employee_id, h.week_start): h.minutes for h in plan.hours}
    assert hours[("e1", date(2026, 3, 2))] == 16 * 15
    assert ("e1", date(2026, 3, 9)) not in hours or hours[("e1", date(2026, 3, 9))] == 0


def test_leave_covers_shift_day_fails():
    src = Shift("s1", "e1", u("2026-03-02T01:00"), u("2026-03-02T05:00"))
    leave = Leave("e1", date(2026, 3, 8), date(2026, 3, 8))
    with pytest.raises(CopyPlanError) as exc:
        generate_copy_plan(NY, date(2026, 3, 2), [Employee("e1")], [src], [leave])
    assert any("休假" in r for r in exc.value.reasons)


def test_overlap_with_existing_and_with_candidate_fails():
    # 目标周存量：当地 2026-03-03 10:00-12:00
    existing_next = Shift("x1", "e1", u("2026-03-03T15:00"), u("2026-03-03T17:00"))
    # 源周两个班次复制后分别与存量、与同批候选重叠
    src_overlap_existing = Shift("s1", "e1", u("2026-02-24T15:30"), u("2026-02-24T17:30"))
    src_a = Shift("s2", "e2", u("2026-02-25T13:00"), u("2026-02-25T17:00"))
    src_b = Shift("s3", "e2", u("2026-02-25T16:00"), u("2026-02-25T20:00"))
    touching = Shift("s4", "e3", u("2026-02-25T13:00"), u("2026-02-25T17:00"))
    ok = generate_copy_plan(NY, date(2026, 3, 2), [Employee("e3")], [touching], [])
    assert len(ok.shifts) == 1  # 首尾相接不算重叠（与下一用例对照）
    with pytest.raises(CopyPlanError) as exc:
        generate_copy_plan(
            NY, date(2026, 3, 2),
            [Employee("e1"), Employee("e2")],
            [existing_next, src_overlap_existing, src_a, src_b],
            [],
        )
    assert any("重叠" in r for r in exc.value.reasons)


def test_touching_intervals_allowed():
    existing_next = Shift("x1", "e1", u("2026-03-03T17:00"), u("2026-03-03T19:00"))
    src = Shift("s1", "e1", u("2026-02-24T15:00"), u("2026-02-24T17:00"))
    plan = generate_copy_plan(NY, date(2026, 3, 2), [Employee("e1")],
                              [existing_next, src], [])
    assert len(plan.shifts) == 1


def test_over_limit_only_warns_and_real_conflict_fails_batch():
    # e1 上限 1 小时：源班次日复制后工时超限 -> 仅警告
    src = Shift("s1", "e1", u("2026-02-24T13:00"), u("2026-02-24T17:00"))
    plan = generate_copy_plan(NY, date(2026, 3, 2),
                              [Employee("e1", weekly_hour_limit=1.0)], [src], [])
    assert len(plan.shifts) == 1
    assert plan.warnings[0].employee_id == "e1"
    assert plan.warnings[0].minutes == 240
    assert plan.warnings[0].limit_minutes == 60
    # 同批加入一个真实冲突 -> 整批失败，不返回部分方案
    conflict = Shift("s2", "e1", u("2026-02-24T15:00"), u("2026-02-24T19:00"))
    existing_next = Shift("x1", "e1", u("2026-03-03T15:30"), u("2026-03-03T16:30"))
    with pytest.raises(CopyPlanError):
        generate_copy_plan(NY, date(2026, 3, 2),
                           [Employee("e1", weekly_hour_limit=1.0)],
                           [src, conflict, existing_next], [])


def test_copy_is_deterministic_and_inputs_unchanged():
    src = Shift("s1", "e1", u("2026-03-01T06:30"), u("2026-03-01T08:30"))
    employees = [Employee("e1")]
    existing = [src]
    first = generate_copy_plan(NY, date(2026, 3, 2), employees, existing, [])
    second = generate_copy_plan(NY, date(2026, 3, 2), employees, existing, [])
    assert first.shifts == second.shifts
    assert first.hours == second.hours
    assert first.warnings == second.warnings
    assert existing == [src]  # 现有输入不被修改


def test_only_source_week_shifts_are_copied_and_ids_are_new():
    in_week = Shift("s1", "e1", u("2026-02-24T13:00"), u("2026-02-24T17:00"))
    # 当地结束日期落在源周、但开始日期属于再上一周（02-22 23:00 - 02-23 01:00），
    # 不能只按结束日期筛选，不应被复制
    by_end_only = Shift("s2", "e1", u("2026-02-23T04:00"), u("2026-02-23T06:00"))
    plan = generate_copy_plan(NY, date(2026, 3, 2), [Employee("e1")],
                              [in_week, by_end_only], [])
    assert [c.id for c in plan.shifts] == ["s1:copy:2026-03-02"]
    assert plan.shifts[0].start_utc == u("2026-03-03T13:00")
