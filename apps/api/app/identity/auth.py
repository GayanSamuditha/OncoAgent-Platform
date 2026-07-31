"""FastAPI dependencies for local OIDC-compatible sessions."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.identity.service import AuthenticatedUser, authenticate_request, ensure_local_user


def current_user(request: Request, settings: Settings = Depends(get_settings)) -> AuthenticatedUser:
    with SessionLocal() as session:
        return authenticate_request(request, session, settings)


def development_actor(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_actor_id: str | None = Header(default=None),
) -> AuthenticatedUser:
    """Authenticate cookies/Bearer tokens; headers are a local migration bridge only.

    The legacy actor role header is intentionally ignored. The server-side local
    identity registry determines the role and permissions.
    """
    with SessionLocal() as session:
        try:
            return authenticate_request(request, session, settings)
        except HTTPException:
            has_token = bool(request.headers.get("authorization") or request.cookies.get(settings.identity_session_cookie))
            if settings.identity_legacy_headers_enabled and settings.environment == "local" and x_actor_id and not has_token:
                return ensure_local_user(session, settings, x_actor_id)
            raise


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]

PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/metrics",
    "/api/v1/platform/info",
    "/api/v1/auth/login",
    "/local-oidc/.well-known/openid-configuration",
    "/api/v1/mcp/status",
    "/api/v1/observability/status",
}


def identity_guard(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_actor_id: str | None = Header(default=None),
) -> AuthenticatedUser | None:
    if request.url.path in PUBLIC_PATHS:
        return None
    # Cookie-authenticated state changes must originate from a configured
    # local application origin.  SameSite=Lax is retained as a second layer;
    # this Origin check prevents cross-site form/fetch requests from using a
    # browser session.  Bearer clients are not subject to browser CSRF.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.cookies.get(settings.identity_session_cookie):
        origin = request.headers.get("origin")
        if origin not in settings.cors_origins:
            raise HTTPException(status_code=403, detail="CSRF origin validation failed")
    return development_actor(request, settings, x_actor_id)
