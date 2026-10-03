import hmac

from fastapi import Request

from backend.app.config import settings
from backend.app.errors import APIError


async def require_runner(request: Request):
    token = settings.RUNNER_SERVICE_TOKEN.get_secret_value()
    if len(token.encode()) < 32 or token == settings.SESSION_CSRF_KEY.get_secret_value():
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "A distinct runner service credential must be configured.")
    supplied = request.headers.get("Authorization", "")
    if len(supplied) > 256 or not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
        raise APIError(401, "UNAUTHORIZED", "A runner service credential is required.")
    return settings.DEFAULT_AGENCY_ID
