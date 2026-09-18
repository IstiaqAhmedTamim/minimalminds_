import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _is_malformed_json_error(exc: RequestValidationError) -> bool:
    for error in exc.errors():
        if error.get("type") in {"json_invalid", "value_error.jsondecode"}:
            return True
        if error.get("loc") == ("body",) and "JSON" in str(error.get("msg", "")):
            return True
    return False


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for error in errors:
        sanitized.append(
            {
                "loc": error.get("loc", []),
                "msg": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
        )
    return sanitized


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        if _is_malformed_json_error(exc):
            return JSONResponse(status_code=400, content={"error": "Malformed JSON"})

        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation errors",
                "details": _sanitize_validation_errors(exc.errors()),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            body = detail
        elif isinstance(detail, list):
            body = {"error": "Validation errors", "details": detail}
        else:
            body = {"error": str(detail)}

        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error")
        return JSONResponse(
            status_code=500,
            content={"error": "Controlled internal error"},
        )
