import secrets
import uuid
from datetime import UTC, datetime

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.security import hash_password, issue_session, verify_password
from app.config import settings
from app.db.models import AuthSession, User, UserRole
from app.db.session import get_db, set_rls_context
from app.schemas.auth import StaffLogin, UserSummary

router = APIRouter(prefix="/auth", tags=["authentication"])
oauth = OAuth()
if settings.google_client_id and settings.google_client_secret:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _set_login_cookies(response: Response, token: str) -> None:
    secure = settings.cookie_secure or settings.environment == "production"
    response.set_cookie("vibecast_session", token, httponly=True, secure=secure,
                        samesite="lax", max_age=settings.session_hours * 3600, path="/")
    response.set_cookie("vibecast_csrf", secrets.token_urlsafe(32), httponly=False,
                        secure=secure, samesite="lax", max_age=settings.session_hours * 3600, path="/")


def _clear_login_cookies(response: Response) -> None:
    response.delete_cookie("vibecast_session", path="/")
    response.delete_cookie("vibecast_csrf", path="/")


@router.get("/google/status")
def google_status():
    return {"configured": bool(settings.google_client_id and settings.google_client_secret)}


@router.post("/staff/login", response_model=UserSummary)
def staff_login(payload: StaffLogin, response: Response, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    # Deliberate, narrowly scoped pre-auth lookup. The transaction-local auth role is cleared on exit.
    set_rls_context(db, None, "platform_admin")
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_active.is_(True)))
    if user is None or user.role == UserRole.listener.value or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    set_rls_context(db, str(user.id), user.role)
    token = issue_session(db, user)
    db.commit()
    _set_login_cookies(response, token)
    return user


@router.get("/google")
async def google_login(request: Request):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    redirect_uri = settings.google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        token = await oauth.google.authorize_access_token(request)
        profile = token.get("userinfo")
    except Exception:
        raise HTTPException(status_code=401, detail="Google sign-in could not be completed") from None
    if not profile or not profile.get("email") or profile.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google did not provide a verified email")

    email = profile["email"].lower()
    # Only this verified email lookup runs with the narrowly scoped auth context.
    set_rls_context(db, None, "platform_admin")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    google_id = profile.get("sub")
    if user is not None and user.role != UserRole.listener.value:
        raise HTTPException(status_code=403, detail="Staff accounts use staff sign-in")
    if user is not None and user.google_id not in (None, google_id):
        raise HTTPException(status_code=409, detail="This email is linked to a different Google account")
    if user is None:
        user = User(id=uuid.uuid4(), name=profile.get("name") or email.split("@")[0], email=email,
                    google_id=google_id, role=UserRole.listener.value)
        set_rls_context(db, str(user.id), user.role)
        db.add(user)
        db.flush()
    elif user.google_id is None:
        user.google_id = google_id
    set_rls_context(db, str(user.id), user.role)
    session_token = issue_session(db, user)
    db.commit()
    response = RedirectResponse(settings.frontend_url, status_code=303)
    _set_login_cookies(response, session_token)
    return response


@router.get("/me", response_model=UserSummary)
def current_user(user: CurrentUser):
    return user


@router.post("/logout", status_code=204)
def logout(response: Response, user: CurrentUser, db: Session = Depends(get_db)):
    session_id = None
    # The dependency has already validated the cookie; decode only to locate this user's session row.
    from app.auth.security import decode_session

    token = db.info.get("session_token")
    if token is None:
        token = ""
    if token:
        session_id = decode_session(token).get("sid")
    if session_id:
        row = db.get(AuthSession, session_id)
        if row is not None and row.user_id == user.id:
            row.revoked_at = datetime.now(UTC)
    db.commit()
    _clear_login_cookies(response)
    return response


def create_staff_user(db: Session, *, name: str, email: str, password: str, role: str) -> User:
    if role not in {UserRole.artist.value, UserRole.label_admin.value, UserRole.platform_admin.value}:
        raise ValueError("Only staff roles may be created here")
    user = User(name=name, email=email.lower(), password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user
