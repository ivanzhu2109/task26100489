"""时区与业务周工具。仅支持纽约与豪勋爵岛，日期范围 2020-2035。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SUPPORTED_TIMEZONES = {
    "America/New_York": ZoneInfo("America/New_York"),
    "Australia/Lord_Howe": ZoneInfo("Australia/Lord_Howe"),
}

UTC = timezone.utc

MIN_DATE = date(2020, 1, 1)
MAX_DATE = date(2035, 12, 31)


def get_timezone(name: str) -> ZoneInfo:
    try:
        return SUPPORTED_TIMEZONES[name]
    except KeyError:
        raise ValueError(f"不支持的时区: {name!r}") from None


def check_week_start(week_start: date) -> None:
    if week_start.weekday() != 0:
        raise ValueError(f"业务周必须从周一开始: {week_start}")
    if not (MIN_DATE <= week_start <= MAX_DATE):
        raise ValueError(f"周起始日期超出支持范围: {week_start}")


def week_bounds_utc(tz: ZoneInfo, week_start: date) -> tuple[datetime, datetime]:
    """返回当地周 [周一零点, 下周一零点) 对应的 UTC 区间。"""
    start_local = datetime(week_start.year, week_start.month, week_start.day, tzinfo=tz)
    end_date = week_start + timedelta(days=7)
    end_local = datetime(end_date.year, end_date.month, end_date.day, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def local_wall(tz: ZoneInfo, utc_dt: datetime) -> datetime:
    """UTC 时刻转当地墙上时间（naive）。"""
    return utc_dt.astimezone(tz).replace(tzinfo=None)


def resolve_local(tz: ZoneInfo, wall: datetime, prefer_offset) -> datetime:
    """把当地墙上时间解析为 UTC 时刻。

    不存在（换时跳过）返回 None；两个候选时优先与 prefer_offset 相同者，
    否则取 UTC 较早者。"""
    candidates: list[datetime] = []
    for fold in (0, 1):
        aware = wall.replace(tzinfo=tz, fold=fold)
        utc_dt = aware.astimezone(UTC)
        if utc_dt.astimezone(tz).replace(tzinfo=None) == wall:
            candidates.append(utc_dt)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    for cand in candidates:
        if cand.astimezone(tz).utcoffset() == prefer_offset:
            return cand
    return min(candidates)
