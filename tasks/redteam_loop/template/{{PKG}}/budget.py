"""A model-call budget shared by every role (and every episode) of a run."""
from __future__ import annotations


class BudgetExceeded(Exception):
    """Raised by CallBudget.charge when no calls are left."""


class CallBudget:
    """Caps the model calls of a run, summed over all roles; each call is charged once, however many retries."""

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.used = 0
        self.by_role: dict[str, int] = {}

    def charge(self, role: str) -> None:
        """Record one call by `role`. Raises BudgetExceeded (recording nothing) once the budget is spent."""
        if self.used >= self.max_calls:
            raise BudgetExceeded(f"call budget of {self.max_calls} exhausted")
        self.used += 1
        self.by_role[role] = self.by_role.get(role, 0) + 1

    def remaining(self) -> int:
        """Calls still available: max_calls - used, never below 0."""
        raise NotImplementedError
