"""RFC 9457-compatible application errors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ApiProblemError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str,
        *,
        headers: Mapping[str, str] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.headers = dict(headers or {})
        self.errors = errors


def bad_request(code: str, detail: str) -> ApiProblemError:
    return ApiProblemError(400, code, "Bad request", detail)


def unauthorized(code: str, detail: str) -> ApiProblemError:
    return ApiProblemError(
        401,
        code,
        "Unauthorized",
        detail,
        headers={"WWW-Authenticate": 'ApiKey realm="exitroute"'},
    )


def forbidden(code: str, detail: str) -> ApiProblemError:
    return ApiProblemError(403, code, "Forbidden", detail)


def not_found(code: str, detail: str) -> ApiProblemError:
    return ApiProblemError(404, code, "Not found", detail)


def conflict(code: str, detail: str) -> ApiProblemError:
    return ApiProblemError(409, code, "Conflict", detail)


def unprocessable(code: str, detail: str) -> ApiProblemError:
    return ApiProblemError(422, code, "Unprocessable entity", detail)
