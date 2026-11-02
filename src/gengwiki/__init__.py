__version__ = "0.1.0"

from .client import GengWiki  # noqa: E402
from .errors import (  # noqa: E402
    AccountApiUnavailable,
    AuthError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    GengWikiError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    UnavailableError,
)

__all__ = [
    "AccountApiUnavailable",
    "AuthError",
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "GengWiki",
    "GengWikiError",
    "NetworkError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "UnavailableError",
]
