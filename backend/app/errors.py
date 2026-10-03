"""Contract errors never include request bodies, cookies or database parameters."""

import logging
import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class APIError(Exception):
    def __init__(self, status, code, message, *, retryable=False):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable


def error_response(request, status, code, message, retryable=False, details=None):
    return JSONResponse(status_code=status, content={
        "code": code, "message": message,
        "request_id": str(request.state.request_id),
        "details": details or [], "retryable": retryable,
    })


def install_errors(app):
    @app.middleware("http")
    async def request_identity(request: Request, call_next):
        try:
            request.state.request_id = uuid.UUID(request.headers.get("X-Request-ID", ""))
        except ValueError:
            request.state.request_id = uuid.uuid4()
        try:
            response = await call_next(request)
        except Exception as error:
            # SQL/validation exception strings can include source bytes and credentials.
            logging.getLogger("proofpay.api").error("Unhandled %s; request_id=%s", type(error).__name__, request.state.request_id)
            response = error_response(request, 500, "INTERNAL_ERROR", "The request could not be completed.")
        response.headers["X-Request-ID"] = str(request.state.request_id)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(APIError)
    async def application_error(request, error):
        return error_response(request, error.status, error.code, error.message, error.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        details = [{"field": ".".join(str(p) for p in item["loc"])[:200],
                    "reason": item["msg"][:600]} for item in error.errors()[:30]]
        return error_response(request, 422, "INVALID_REQUEST", "Request validation failed.", details=details)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        codes = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        if isinstance(error.detail, dict):
            code = error.detail.get("code", "INVALID_REQUEST")
            message = error.detail.get("message", "Request failed.")
        else:
            code = codes.get(error.status_code, "INVALID_REQUEST")
            message = str(error.detail)
        return error_response(request, error.status_code, code, message)
