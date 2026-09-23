from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VIBECAST_", extra="ignore")

    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://vibecast_app:change-me@localhost:5432/vibecast"
    database_migration_url: str = "postgresql+psycopg://vibecast_owner:change-me@localhost:5432/vibecast"
    jwt_secret: str = "development-only-change-this-secret-before-deploying"
    jwt_issuer: str = "vibecast"
    session_hours: int = 8
    cookie_secure: bool = False
    frontend_url: str = "http://localhost:5173"
    allowed_origins: str = "http://localhost:5173"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    jamendo_client_id: str | None = None
    jamendo_api_base: str = "https://api.jamendo.com/v3.0"
    jamendo_page_size: int = 100
    jamendo_max_tracks: int = 1000
    jamendo_search_queries: str = ""
    jamendo_min_request_interval: float = 0.25
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    recommendation_content_weight: float = 0.55
    vibe_semantic_weight: float = 0.65
    vibe_tag_weight: float = 0.20
    vibe_feature_weight: float = 0.15
    upload_directory: str = "./data/uploads"
    upload_max_bytes: int = 40 * 1024 * 1024
    worker_poll_seconds: float = 2.0
    worker_job_attempts: int = 4
    collaborative_retrain_after_plays: int = 100

    @model_validator(mode="after")
    def require_real_production_secret(self):
        if self.environment == "production":
            secret = self.jwt_secret.casefold()
            secret_placeholders = (
                "development-only-change-this-secret",
                "replace-with-a-random-secret",
                "change-me",
            )
            if len(self.jwt_secret) < 32 or any(marker in secret for marker in secret_placeholders):
                raise ValueError("VIBECAST_JWT_SECRET must be a real random secret of at least 32 characters")
            urls = (self.database_url.casefold(), self.database_migration_url.casefold())
            if any("change-me" in url or "replace-this" in url for url in urls):
                raise ValueError("Production database URLs must not contain the example credentials")
        return self

    @field_validator("jamendo_page_size")
    @classmethod
    def page_size_within_api_limit(cls, value: int) -> int:
        if not 1 <= value <= 200:
            raise ValueError("Jamendo page size must be between 1 and 200")
        return value

    @field_validator("session_hours")
    @classmethod
    def valid_session_lifetime(cls, value: int) -> int:
        if not 1 <= value <= 24:
            raise ValueError("Session lifetime must be between 1 and 24 hours")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
