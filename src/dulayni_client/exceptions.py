"""Custom exceptions for the dulayni client."""


class DulayniClientError(Exception):
    """Base exception for dulayni client errors."""

    pass


class DulayniConnectionError(DulayniClientError):
    """Raised when unable to connect to the dulayni server."""

    pass


class DulayniTimeoutError(DulayniClientError):
    """Raised when a request to the dulayni server times out."""

    pass
