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


class DulayniAuthenticationError(DulayniClientError):
    """Raised when authentication fails or is required."""

    pass


class DulayniPaymentRequiredError(DulayniClientError):
    """Raised when payment is required to complete the request."""
    
    def __init__(self, message, payment_info=None):
        super().__init__(message)
        self.payment_info = payment_info
