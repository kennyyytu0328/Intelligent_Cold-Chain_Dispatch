"""Exceptions for Smart Assignment recommendation service."""


class RecommendationException(Exception):
    """Base exception for recommendation service."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InsufficientDataException(RecommendationException):
    """No vehicles found or no data available for recommendation."""
    pass


class InvalidRouteSignatureException(RecommendationException):
    """Route has empty or null route_signature."""
    pass
