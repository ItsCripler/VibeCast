import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AuthSession, User

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str | None) -> bool:
    return bool(encoded_hash) and password_hash.verify(password, encoded_hash)


def issue_session(db: Session, user: User) -> str:
    now = datetime.now(UTC)
    expires = now + timedelta(hours=settings.session_hours)
    session_id = uuid.uuid4()
    db.add(AuthSession(id=session_id, user_id=user.id, expires_at=expires))
    db.flush()
    return jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "sid": str(session_id),
            "iat": now,
            "exp": expires,
            "iss": settings.jwt_issuer,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_session(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer=settings.jwt_issuer)
