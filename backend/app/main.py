from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api import activity, admin, analytics, artists, auth, catalog, labels, playlists
from app.auth.csrf import CSRFMiddleware
from app.config import settings

app = FastAPI(
    title="VibeCast API",
    description="Jamendo-only music discovery, recommendations, playlists, and listening analytics.",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret,
                   max_age=300, same_site="lax",
                   https_only=settings.cookie_secure or settings.environment == "production")

for route_group in (auth.router, catalog.router, playlists.router, activity.router,
                    analytics.router, artists.router, labels.router, admin.router):
    app.include_router(route_group, prefix=settings.api_prefix)


@app.get("/health/live", tags=["health"])
def live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready():
    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready"}
