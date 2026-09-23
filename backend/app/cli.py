import sys
from getpass import getpass

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import settings
from app.db import models  # noqa: F401
from app.db.models import User


def create_first_admin() -> None:
    name = input("Platform admin name: ").strip()
    email = input("Platform admin email: ").strip().lower()
    password = getpass("Password (12+ characters): ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters")
    engine = create_engine(settings.database_migration_url, pool_pre_ping=True)
    with Session(engine) as db:
        if db.scalar(select(User.id).where(func.lower(User.email) == email)):
            raise SystemExit("An account already uses that email")
        if db.scalar(select(User.id).where(User.role == "platform_admin")):
            raise SystemExit("A platform administrator already exists; use the admin API to add another")
        user = User(name=name, email=email, password_hash=hash_password(password), role="platform_admin")
        db.add(user)
        db.commit()
    engine.dispose()
    print("Platform administrator created. Sign in at the staff login screen.")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] != "create-admin":
        raise SystemExit("Usage: python -m app.cli create-admin")
    create_first_admin()


if __name__ == "__main__":
    main()
