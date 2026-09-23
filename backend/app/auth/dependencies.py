import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_session
from app.db.models import AuthSession, User
from app.db.session import get_db, set_rls_context


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    token = request.cookies.get("vibecast_session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    db.info["session_token"] = token
    try:
        claims = decode_session(token)
        user_id = uuid.UUID(claims["sub"])
        session_id = uuid.UUID(claims["sid"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired") from None

    set_rls_context(db, str(user_id), str(claims.get("role", "")))
    auth_session = db.scalar(select(AuthSession).where(AuthSession.id == session_id))
    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    now = datetime.now(UTC)
    if (auth_session is None or auth_session.revoked_at is not None or auth_session.expires_at <= now
            or user is None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    # Refresh the RLS role from the database so revoked staff privileges in a live token do not linger.
    set_rls_context(db, str(user.id), user.role)
    return user


def require_roles(*roles: str):
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


def get_optional_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User | None:
    if not request.cookies.get("vibecast_session"):
        return None
    return get_current_user(request, db)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
