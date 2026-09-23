import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit protection for cookie-authenticated state-changing requests."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get("vibecast_session"):
            cookie = request.cookies.get("vibecast_csrf", "")
            header = request.headers.get("x-csrf-token", "")
            if not cookie or not header or not secrets.compare_digest(cookie, header):
                return JSONResponse({"detail": "CSRF token missing or invalid"}, status_code=403)
        return await call_next(request)
