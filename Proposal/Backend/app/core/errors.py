"""Typed HTTP errors used across the API."""
from __future__ import annotations

from fastapi import HTTPException, status


class NotFound(HTTPException):
    def __init__(self, what: str = "Resource") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, f"{what} not found")


class Forbidden(HTTPException):
    def __init__(self, detail: str = "Not authorized") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class Unauthorized(HTTPException):
    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(
            status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
        )


class BadRequest(HTTPException):
    def __init__(self, detail: str = "Bad request") -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)


class Conflict(HTTPException):
    def __init__(self, detail: str = "Conflict") -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)
