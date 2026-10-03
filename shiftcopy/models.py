"""数据模型：员工、班次、休假与复制结果。所有数据仅保存在内存中。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class Employee:
    id: str
    weekly_hour_limit: float = 40.0


@dataclass(frozen=True)
class Shift:
    """已分配员工的班次。start_utc/end_utc 为带 tzinfo 的 UTC 时刻，

    包含开始、不包含结束；边界落在 15 分钟刻度上。"""
    id: str
    employee_id: str
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class Leave:
    """已批准休假，起止日期（当地日期）均包含全天。"""
    employee_id: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class WeekHours:
    """某员工在某业务周内的工时（分钟）。"""
    employee_id: str
    week_start: date
    minutes: int


@dataclass(frozen=True)
class OverLimitWarning:
    """周工时超过员工上限的警告（不阻止复制）。"""
    employee_id: str
    week_start: date
    minutes: int
    limit_minutes: int


@dataclass
class CopyPlan:
    """整批通过后的完整复制方案。"""
    shifts: list[Shift] = field(default_factory=list)
    warnings: list[OverLimitWarning] = field(default_factory=list)
    hours: list[WeekHours] = field(default_factory=list)


class CopyPlanError(Exception):
    """整批失败。reasons 记录每个出问题班次的具体原因。"""

    def __init__(self, reasons: list[str]):
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons))
