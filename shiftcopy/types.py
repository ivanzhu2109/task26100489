"""Data types for the weekly shift copy library.

All data is provided by the caller and kept in memory only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class Employee:
    """An employee with a weekly working-hours cap (default 40h)."""

    employee_id: str
    weekly_hours_cap: float = 40.0


@dataclass(frozen=True)
class Shift:
    """An assigned shift.

    ``start_utc`` / ``end_utc`` are timezone-aware UTC datetimes.
    The shift contains its start instant but not its end instant.
    """

    shift_id: str
    employee_id: str
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class Leave:
    """Approved leave for an employee; both dates are inclusive full days
    in the store's local timezone."""

    employee_id: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class OvertimeWarning:
    """Weekly hours exceed an employee's cap; never blocks copying."""

    employee_id: str
    week_start: date
    minutes: int
    cap_minutes: int


@dataclass
class CopyPlan:
    """Result of a successful copy: candidate shifts plus warnings."""

    shifts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class CopyPlanError(Exception):
    """Raised when the whole batch fails; no partial plan is returned."""
