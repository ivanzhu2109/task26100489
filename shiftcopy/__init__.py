"""Weekly shift copy library (in-memory, caller-driven)."""

from .copy import build_copy_plan
from .hours import weekly_minutes
from .types import (
    CopyPlan,
    CopyPlanError,
    Employee,
    Leave,
    OvertimeWarning,
    Shift,
)

__all__ = [
    "build_copy_plan",
    "weekly_minutes",
    "CopyPlan",
    "CopyPlanError",
    "Employee",
    "Leave",
    "OvertimeWarning",
    "Shift",
]
