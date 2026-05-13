class AppError(Exception):
    """Base application exception."""


class SecurityError(AppError):
    """Webhook security validation failed."""


class MaxApiError(AppError):
    """MAX API returned a non-retryable error."""


class MaxApiRetryableError(MaxApiError):
    """MAX API failed after retryable attempts."""


class RoutingError(AppError):
    """No route can be resolved for an alert group."""


class FormattingError(AppError):
    """Message formatting failed."""
