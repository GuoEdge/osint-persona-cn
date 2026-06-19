"""Web 中间件 / Web middleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from osint_toolkit.web.web_token import TOKEN_COOKIE, TOKEN_HEADER, get_or_create_token, is_auth_enabled, token_matches


class WebTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path == "/api/health":
            response = await call_next(request)
            if is_auth_enabled():
                token = get_or_create_token()
                response.set_cookie(
                    TOKEN_COOKIE,
                    token,
                    httponly=True,
                    samesite="strict",
                    secure=False,
                    max_age=60 * 60 * 24 * 365,
                )
            return response
        if not is_auth_enabled() or not path.startswith("/api/"):
            response = await call_next(request)
            if not path.startswith("/api/") and path != "/favicon.ico":
                token = get_or_create_token()
                response.set_cookie(
                    TOKEN_COOKIE,
                    token,
                    httponly=True,
                    samesite="strict",
                    secure=False,
                    max_age=60 * 60 * 24 * 365,
                )
            return response

        header_token = request.headers.get(TOKEN_HEADER) or request.headers.get("X-Osint-Token")
        cookie_token = request.cookies.get(TOKEN_COOKIE)
        if not token_matches(header_token, cookie_token):
            return JSONResponse({"detail": "invalid or missing web token"}, status_code=403)

        return await call_next(request)
