"""One exception per error code the gengwiki services return."""


class GengWikiError(Exception):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class BadRequestError(GengWikiError):
    pass


class AuthError(GengWikiError):
    """Missing or invalid API key, or an expired login."""


class ForbiddenError(GengWikiError):
    """The key lacks a scope, or a quota is used up."""


class NotFoundError(GengWikiError):
    """The resource does not exist or is outside this key's scope."""


class ConflictError(GengWikiError):
    pass


class UnavailableError(GengWikiError):
    """The service cannot answer right now. Cached data is served instead when there is any."""


class RateLimitError(UnavailableError):
    def __init__(self, message: str, status: int | None = 429, code: str | None = "rate_limited", retry_after: float = 0):
        super().__init__(message, status, code)
        self.retry_after = retry_after


class ServerError(UnavailableError):
    pass


class NetworkError(UnavailableError):
    pass


class AccountApiUnavailable(GengWikiError):
    """The site does not expose the account routes, so keys cannot be managed from here."""
