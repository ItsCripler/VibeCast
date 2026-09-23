from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import PlayEvent, Playlist, Song, User, UserSongStat
from app.db.session import set_rls_context

pytestmark = pytest.mark.skipif(
    os.getenv("VIBECAST_RUN_DATABASE_TESTS") != "1",
    reason="set VIBECAST_RUN_DATABASE_TESTS=1 after applying the PostgreSQL migration",
)


def test_private_playlist_rls_role_guard_and_concurrent_play_rollup() -> None:
    owner_engine = create_engine(settings.database_migration_url, pool_pre_ping=True)
    owner_factory = sessionmaker(bind=owner_engine, expire_on_commit=False)
    app_engine = create_engine(settings.database_url, pool_pre_ping=True)
    app_factory = sessionmaker(bind=app_engine, expire_on_commit=False)
    own_user_id, other_user_id, song_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    own_playlist_id, other_playlist_id = uuid.uuid4(), uuid.uuid4()
    song_external_id = f"rls-test-{song_id}"
    try:
        with owner_factory() as owner:
            owner.add_all([
                User(id=own_user_id, name="RLS test one", email=f"{own_user_id}@example.invalid", role="listener"),
                User(id=other_user_id, name="RLS test two", email=f"{other_user_id}@example.invalid", role="listener"),
                Song(id=song_id, source="jamendo", jamendo_track_id=song_external_id,
                     title="RLS fixture", artist_name="Test fixture", duration_seconds=90,
                     tags=[], jamendo_musicinfo={}, is_public=True),
                Playlist(id=own_playlist_id, owner_id=own_user_id, name="Private one"),
                Playlist(id=other_playlist_id, owner_id=other_user_id, name="Private two"),
            ])
            owner.commit()

        with app_factory() as app:
            set_rls_context(app, str(own_user_id), "listener")
            visible = set(app.scalars(select(Playlist.id)))
            assert visible == {own_playlist_id}
            app.add(Playlist(owner_id=other_user_id, name="RLS violation"))
            with pytest.raises(DBAPIError):
                app.flush()
            app.rollback()

        def attempt_role_escalation() -> None:
            with app_factory() as app:
                set_rls_context(app, str(own_user_id), "listener")
                with pytest.raises(DBAPIError):
                    app.execute(update(User).where(User.id == own_user_id).values(role="platform_admin"))
                app.rollback()

        attempt_role_escalation()

        barrier = Barrier(2)

        def record(event_id: uuid.UUID) -> None:
            with app_factory() as app:
                set_rls_context(app, str(own_user_id), "listener")
                barrier.wait(timeout=10)
                app.add(PlayEvent(id=event_id, client_event_id=event_id, user_id=own_user_id,
                                  song_id=song_id, duration_played_seconds=45, qualified=True))
                app.commit()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(record, uuid.uuid4()) for _ in range(2)]
            for future in futures:
                future.result()

        with app_factory() as app:
            set_rls_context(app, str(own_user_id), "listener")
            stats = app.scalar(select(UserSongStat).where(
                UserSongStat.user_id == own_user_id, UserSongStat.song_id == song_id))
            assert stats is not None
            assert stats.qualified_plays == 2
            assert stats.listening_seconds == 90
    finally:
        with owner_factory() as owner:
            owner.execute(delete(User).where(User.id.in_([own_user_id, other_user_id])))
            owner.execute(delete(Song).where(Song.id == song_id))
            owner.commit()
        app_engine.dispose()
        owner_engine.dispose()
