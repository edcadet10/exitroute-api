"""FastAPI application factory."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from exitroute import __version__
from exitroute.api import admin, challenges, observations, public, system, webhooks
from exitroute.config import Settings, get_settings
from exitroute.database import create_database_engine, create_session_factory
from exitroute.errors import ApiProblemError
from exitroute.schemas import Problem

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
request_logger = logging.getLogger("uvicorn.error")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if _REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
        request.state.request_id = request_id
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            request_logger.info(
                json.dumps(
                    {
                        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                        "event": "http_request",
                        "method": request.method,
                        "request_id": request_id,
                        "route": route_template,
                        "status": status_code,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


def _problem_response(request: Request, error: ApiProblemError) -> JSONResponse:
    response_headers = {
        **error.headers,
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Request-ID": getattr(request.state, "request_id", str(uuid.uuid4())),
    }
    body = Problem(
        type=f"https://exitroute.dev/problems/{error.code}",
        title=error.title,
        status=error.status,
        detail=error.detail,
        code=error.code,
        instance=request.url.path,
        request_id=getattr(request.state, "request_id", None),
        errors=error.errors,
    )
    return JSONResponse(
        status_code=error.status,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
        headers=response_headers,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    engine = create_database_engine(resolved)
    factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    application = FastAPI(
        title="ExitRoute API",
        summary="Versioned, verified routes for leaving digital services",
        description=(
            "A self-hosted informational API. It never authenticates to, operates, or stores "
            "credentials for a consumer account."
        ),
        version=__version__,
        license_info={"name": "MIT", "identifier": "MIT"},
        contact={"name": "ExitRoute maintainers"},
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system"},
            {"name": "routes"},
            {"name": "observations"},
            {"name": "challenges"},
            {"name": "webhooks"},
            {"name": "admin"},
        ],
    )
    application.state.settings = resolved
    application.state.engine = engine
    application.state.session_factory = factory
    application.add_middleware(RequestContextMiddleware)
    if resolved.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=resolved.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "If-None-Match",
                "X-API-Key",
                "X-Request-ID",
            ],
        )

    @application.exception_handler(ApiProblemError)
    async def handle_problem(request: Request, error: ApiProblemError) -> JSONResponse:
        return _problem_response(request, error)

    @application.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, error: RequestValidationError) -> JSONResponse:
        details = []
        for item in error.errors():
            details.append(
                {
                    "location": ".".join(str(part) for part in item["loc"]),
                    "message": item["msg"],
                    "type": item["type"],
                }
            )
        problem = ApiProblemError(
            422,
            "request_validation_failed",
            "Unprocessable entity",
            "The request did not satisfy the API contract.",
            errors=details,
        )
        return _problem_response(request, problem)

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        if error.status_code == 404:
            code, title = "not_found", "Not found"
        elif error.status_code == 405:
            code, title = "method_not_allowed", "Method not allowed"
        else:
            code, title = "http_error", "HTTP error"
        problem = ApiProblemError(
            error.status_code,
            code,
            title,
            str(error.detail),
            headers=error.headers,
        )
        return _problem_response(request, problem)

    @application.exception_handler(Exception)
    async def handle_unexpected(request: Request, error: Exception) -> JSONResponse:
        request_logger.error(
            json.dumps(
                {
                    "error_type": type(error).__name__,
                    "event": "unhandled_request_exception",
                    "request_id": getattr(request.state, "request_id", None),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return _problem_response(
            request,
            ApiProblemError(
                500,
                "internal_error",
                "Internal server error",
                "The server could not complete the request.",
            ),
        )

    application.include_router(system.router)
    application.include_router(challenges.router)
    application.include_router(public.router)
    application.include_router(observations.router)
    application.include_router(webhooks.router)
    application.include_router(admin.router)

    def custom_openapi() -> dict[str, object]:
        if application.openapi_schema:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            summary=application.summary,
            description=application.description,
            routes=application.routes,
            tags=application.openapi_tags,
        )
        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        schemas["Problem"] = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
        responses = components.setdefault("responses", {})
        for status_code, name, description in (
            (400, "BadRequest", "The request is malformed."),
            (401, "Unauthorized", "Authentication failed."),
            (403, "Forbidden", "The credential lacks the required scope."),
            (404, "NotFound", "The requested resource does not exist."),
            (409, "Conflict", "The request conflicts with resource state."),
            (422, "Unprocessable", "The request violates a semantic or safety rule."),
            (429, "RateLimited", "The API-client quota was exceeded."),
            (500, "InternalError", "The server could not complete the request."),
            (503, "Unavailable", "A required service dependency is unavailable."),
        ):
            response: dict[str, object] = {
                "description": description,
                "content": {
                    "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
                },
            }
            if status_code == 429:
                response["headers"] = {
                    "Retry-After": {
                        "description": "Seconds until a new quota window.",
                        "schema": {"type": "integer", "minimum": 1},
                    }
                }
            responses[name] = response
        for path, path_item in schema["paths"].items():
            for method, operation in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                operation_responses = operation.setdefault("responses", {})
                operation_responses.setdefault(
                    "500", {"$ref": "#/components/responses/InternalError"}
                )
                if path == "/readyz":
                    operation_responses.setdefault(
                        "503", {"$ref": "#/components/responses/Unavailable"}
                    )
                if path not in {"/healthz", "/readyz", "/v1/challenges/daily"}:
                    operation_responses.setdefault(
                        "401", {"$ref": "#/components/responses/Unauthorized"}
                    )
                    operation_responses.setdefault(
                        "403", {"$ref": "#/components/responses/Forbidden"}
                    )
                    operation_responses.setdefault(
                        "429", {"$ref": "#/components/responses/RateLimited"}
                    )
                if "{" in path:
                    operation_responses.setdefault(
                        "404", {"$ref": "#/components/responses/NotFound"}
                    )
                if method in {"post", "put", "patch", "delete"}:
                    operation_responses.setdefault(
                        "409", {"$ref": "#/components/responses/Conflict"}
                    )
                if "422" in operation_responses:
                    operation_responses["422"] = {"$ref": "#/components/responses/Unprocessable"}
                if "304" in operation_responses:
                    operation_responses["304"]["headers"] = {
                        "ETag": {
                            "description": "Strong representation validator.",
                            "schema": {"type": "string"},
                        }
                    }
        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi  # type: ignore[method-assign]
    return application


app = create_app()
