from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _apply_transaction_rls_context(session: Session, _transaction, connection) -> None:
    context = session.info.get("rls_context", {})
    connection.execute(
        text("SELECT set_config('app.user_id', :uid, true), "
             "set_config('app.role', :role, true), set_config('app.worker', :worker, true)"),
        {"uid": context.get("user_id", ""), "role": context.get("role", ""),
         "worker": "true" if context.get("worker", False) else "false"},
    )


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            if session.in_transaction():
                session.rollback()


def set_rls_context(session: Session, user_id: str | None, role: str | None, worker: bool = False) -> None:
    """Set transaction-local RLS identity; values cannot leak across pooled connections."""
    session.info["rls_context"] = {"user_id": user_id or "", "role": role or "", "worker": worker}
    session.execute(
        text("SELECT set_config('app.user_id', :uid, true), "
             "set_config('app.role', :role, true), set_config('app.worker', :worker, true)"),
        {"uid": user_id or "", "role": role or "", "worker": "true" if worker else "false"},
    )
