"""RFC 7807 `application/problem+json` for every error path.

`ProblemException` is what routes raise for an expected 4xx. First-party domain
errors (`TortoiseError`, which carries its own `http_status`/`http_title`) and
FastAPI's own validation / HTTP errors are caught by the handlers installed here
and reshaped into the same body, so a client only ever parses one error format.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import TortoiseError
from app.core.logging import get_logger

log = get_logger("api.errors")

_PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemException(Exception):
    def __init__(
        self,
        *,
        status: int,
        title: str,
        detail: str | None = None,
        type: str = "about:blank",
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type


def problem(
    *, status: int, title: str, detail: str | None = None, type: str = "about:blank"
) -> JSONResponse:
    body: dict[str, Any] = {"type": type, "title": title, "status": status}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type=_PROBLEM_MEDIA_TYPE)


def _validation_detail(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        parts.append(f"{loc}: {err['msg']}" if loc else str(err["msg"]))
    return "; ".join(parts)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemException)
    async def _on_problem(_: Request, exc: ProblemException) -> JSONResponse:
        return problem(status=exc.status, title=exc.title, detail=exc.detail, type=exc.type)

    @app.exception_handler(RequestValidationError)
    async def _on_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(status=422, title="Unprocessable Entity", detail=_validation_detail(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _on_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = exc.detail if isinstance(exc.detail, str) else "Error"
        return problem(status=exc.status_code, title=title)

    @app.exception_handler(TortoiseError)
    async def _on_domain(_: Request, exc: TortoiseError) -> JSONResponse:
        return problem(status=exc.http_status, title=exc.http_title, detail=str(exc))

    @app.exception_handler(Exception)
    async def _on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("api.unhandled", path=request.url.path, error=type(exc).__name__)
        return problem(status=500, title="Internal Server Error")
