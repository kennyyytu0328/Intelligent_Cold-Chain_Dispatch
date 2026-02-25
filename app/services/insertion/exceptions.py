"""Exceptions for Dynamic Insertion service."""
from uuid import UUID


class StaleRouteException(Exception):
    """Raised when a CAS (Compare-And-Swap) version check fails.

    This indicates another user modified the route between the time
    the client read it and attempted to apply changes.
    """

    def __init__(
        self,
        route_id: UUID,
        expected_version: int,
        current_version: int | None = None,
        message: str = "Route was modified by another user. Please refresh and retry.",
    ):
        self.route_id = route_id
        self.expected_version = expected_version
        self.current_version = current_version
        self.message = message
        super().__init__(message)


class InsertionRejectedException(Exception):
    """Raised when no feasible insertion position exists.

    All candidate positions have temperature risk above the threshold.
    """

    def __init__(
        self,
        reason: str,
        temp_risk_score: float | None = None,
    ):
        self.reason = reason
        self.temp_risk_score = temp_risk_score
        super().__init__(reason)
