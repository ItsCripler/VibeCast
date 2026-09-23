import pytest
from pydantic import ValidationError

from app.config import Settings


def valid_production_values() -> dict[str, str]:
    return {
        "environment": "production",
        "jwt_secret": "secure-random-value-with-at-least-32-characters",
        "database_url": "postgresql+psycopg://runtime:strong-db-password@localhost:5432/vibecast",
        "database_migration_url": "postgresql+psycopg://owner:strong-owner-password@localhost:5432/vibecast",
    }


def test_production_accepts_non_placeholder_credentials() -> None:
    assert Settings(**valid_production_values()).environment == "production"


@pytest.mark.parametrize("field,value", [
    ("jwt_secret", "replace-with-a-random-secret-at-least-32-characters"),
    ("database_url", "postgresql+psycopg://app:replace-this-runtime-password@db/vibecast"),
    ("database_migration_url", "postgresql+psycopg://owner:change-me@db/vibecast"),
])
def test_production_rejects_example_credentials(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{**valid_production_values(), field: value})
