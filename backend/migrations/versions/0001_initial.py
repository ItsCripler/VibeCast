"""Initial normalized catalog, activity, recommendation, and security schema."""

from alembic import op
from sqlalchemy import text

from app.db.base import Base
from app.db import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

RLS_TABLES = (
    "users", "labels", "label_members", "artist_profiles", "catalog_artists", "albums",
    "songs", "song_features", "song_embeddings", "playlists", "playlist_songs",
    "play_events", "user_song_stats", "user_daily_stats", "artist_daily_stats", "item_similarities", "jobs",
    "catalog_sync_runs", "auth_sessions", "demo_counters",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')

    op.execute("""
    CREATE FUNCTION vibecast_app_user_id() RETURNS uuid
    LANGUAGE sql STABLE AS $$
      SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
    $$;
    CREATE FUNCTION vibecast_app_role() RETURNS text
    LANGUAGE sql STABLE AS $$ SELECT COALESCE(current_setting('app.role', true), '') $$;
    CREATE FUNCTION vibecast_is_worker() RETURNS boolean
    LANGUAGE sql STABLE AS $$ SELECT COALESCE(current_setting('app.worker', true), 'false') = 'true' $$;
    """)

    admin_or_worker = "vibecast_app_role() = 'platform_admin' OR vibecast_is_worker()"
    own_or_admin = "user_id = vibecast_app_user_id() OR vibecast_app_role() = 'platform_admin'"
    policies = {
        "users": ("id = vibecast_app_user_id() OR vibecast_app_role() = 'platform_admin' OR vibecast_is_worker() OR EXISTS (SELECT 1 FROM artist_profiles ap JOIN label_members lm ON lm.label_id = ap.label_id WHERE ap.user_id = users.id AND lm.user_id = vibecast_app_user_id() AND lm.membership_role = 'admin')", "(id = vibecast_app_user_id() AND role = 'listener') OR vibecast_app_role() = 'platform_admin' OR vibecast_is_worker()"),
        "labels": ("vibecast_app_role() = 'platform_admin' OR EXISTS (SELECT 1 FROM label_members lm WHERE lm.label_id = labels.id AND lm.user_id = vibecast_app_user_id())", admin_or_worker),
        "label_members": ("user_id = vibecast_app_user_id() OR vibecast_app_role() = 'platform_admin'", admin_or_worker),
        "artist_profiles": ("user_id = vibecast_app_user_id() OR vibecast_app_role() = 'platform_admin' OR (vibecast_app_role() = 'label_admin' AND EXISTS (SELECT 1 FROM label_members lm WHERE lm.label_id = artist_profiles.label_id AND lm.user_id = vibecast_app_user_id()))", "user_id = vibecast_app_user_id() OR vibecast_app_role() = 'platform_admin' OR (vibecast_app_role() = 'label_admin' AND EXISTS (SELECT 1 FROM label_members lm WHERE lm.label_id = artist_profiles.label_id AND lm.user_id = vibecast_app_user_id()))"),
        "playlists": ("owner_id = vibecast_app_user_id() OR is_public OR vibecast_app_role() = 'platform_admin' OR vibecast_is_worker()", "owner_id = vibecast_app_user_id() OR vibecast_app_role() = 'platform_admin' OR vibecast_is_worker()"),
        "play_events": (own_or_admin + " OR vibecast_is_worker()", own_or_admin + " OR vibecast_is_worker()"),
        "user_song_stats": (own_or_admin + " OR vibecast_is_worker()", own_or_admin + " OR vibecast_is_worker()"),
        "user_daily_stats": (own_or_admin + " OR vibecast_is_worker()", own_or_admin + " OR vibecast_is_worker()"),
        "artist_daily_stats": ("vibecast_app_role() = 'platform_admin' OR vibecast_is_worker() OR EXISTS (SELECT 1 FROM artist_profiles ap WHERE ap.id = artist_daily_stats.artist_profile_id AND (ap.user_id = vibecast_app_user_id() OR EXISTS (SELECT 1 FROM label_members lm WHERE lm.label_id = ap.label_id AND lm.user_id = vibecast_app_user_id() AND lm.membership_role = 'admin'))) ", admin_or_worker),
        "jobs": (admin_or_worker, admin_or_worker),
        "catalog_sync_runs": (admin_or_worker, admin_or_worker),
        "auth_sessions": (own_or_admin, own_or_admin),
        "demo_counters": (admin_or_worker, admin_or_worker),
    }
    for table, (using_expression, check_expression) in policies.items():
        op.execute(f'CREATE POLICY {table}_scope ON "{table}" USING ({using_expression}) WITH CHECK ({check_expression})')

    # Public read access is separated from mutation rights so a listener cannot
    # insert a row that merely claims to have come from Jamendo.
    op.execute("CREATE POLICY catalog_artists_read ON catalog_artists FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY catalog_artists_write ON catalog_artists FOR ALL USING ({admin_or_worker}) WITH CHECK ({admin_or_worker})")
    op.execute("CREATE POLICY albums_read ON albums FOR SELECT USING (source = 'jamendo' OR EXISTS (SELECT 1 FROM songs s WHERE s.album_id = albums.id AND s.is_public) OR EXISTS (SELECT 1 FROM artist_profiles ap WHERE ap.id = albums.artist_profile_id AND ap.user_id = vibecast_app_user_id()))")
    op.execute(f"CREATE POLICY albums_write ON albums FOR ALL USING ({admin_or_worker} OR EXISTS (SELECT 1 FROM artist_profiles ap WHERE ap.id = albums.artist_profile_id AND ap.user_id = vibecast_app_user_id())) WITH CHECK ({admin_or_worker} OR EXISTS (SELECT 1 FROM artist_profiles ap WHERE ap.id = albums.artist_profile_id AND ap.user_id = vibecast_app_user_id()))")
    song_read = "(is_public AND source IN ('jamendo','artist_upload')) OR EXISTS (SELECT 1 FROM artist_profiles ap WHERE ap.id = songs.artist_profile_id AND ap.user_id = vibecast_app_user_id()) OR vibecast_app_role() = 'platform_admin' OR vibecast_is_worker()"
    song_write = "vibecast_app_role() = 'platform_admin' OR vibecast_is_worker() OR (source = 'artist_upload' AND EXISTS (SELECT 1 FROM artist_profiles ap WHERE ap.id = songs.artist_profile_id AND ap.user_id = vibecast_app_user_id()))"
    op.execute(f"CREATE POLICY songs_read ON songs FOR SELECT USING ({song_read})")
    op.execute(f"CREATE POLICY songs_write ON songs FOR ALL USING ({song_write}) WITH CHECK ({song_write})")
    for table in ("song_features", "song_embeddings"):
        read = f"EXISTS (SELECT 1 FROM songs s WHERE s.id = {table}.song_id AND ((s.is_public) OR EXISTS (SELECT 1 FROM artist_profiles ap WHERE ap.id = s.artist_profile_id AND ap.user_id = vibecast_app_user_id()))) OR {admin_or_worker}"
        write = f"{admin_or_worker} OR EXISTS (SELECT 1 FROM songs s JOIN artist_profiles ap ON ap.id = s.artist_profile_id WHERE s.id = {table}.song_id AND ap.user_id = vibecast_app_user_id() AND s.source = 'artist_upload')"
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({read})")
        op.execute(f"CREATE POLICY {table}_write ON {table} FOR ALL USING ({write}) WITH CHECK ({write})")
    playlist_song_scope = "EXISTS (SELECT 1 FROM playlists p WHERE p.id = playlist_songs.playlist_id AND (p.owner_id = vibecast_app_user_id() OR p.is_public)) OR vibecast_app_role() = 'platform_admin' OR vibecast_is_worker()"
    playlist_song_write = "EXISTS (SELECT 1 FROM playlists p WHERE p.id = playlist_songs.playlist_id AND p.owner_id = vibecast_app_user_id()) OR vibecast_app_role() = 'platform_admin' OR vibecast_is_worker()"
    op.execute(f"CREATE POLICY playlist_songs_read ON playlist_songs FOR SELECT USING ({playlist_song_scope})")
    op.execute(f"CREATE POLICY playlist_songs_write ON playlist_songs FOR ALL USING ({playlist_song_write}) WITH CHECK ({playlist_song_write})")
    op.execute("CREATE POLICY item_similarities_read ON item_similarities FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY item_similarities_write ON item_similarities FOR ALL USING ({admin_or_worker}) WITH CHECK ({admin_or_worker})")
    op.execute("CREATE POLICY jobs_artist_processing ON jobs FOR INSERT WITH CHECK (kind IN ('embed_song','analyze_song') AND EXISTS (SELECT 1 FROM songs s JOIN artist_profiles ap ON ap.id = s.artist_profile_id WHERE s.id = (jobs.payload ->> 'song_id')::uuid AND ap.user_id = vibecast_app_user_id() AND s.source = 'artist_upload'))")

    op.execute("REVOKE UPDATE ON users FROM vibecast_app")
    op.execute("GRANT UPDATE (name, preferences, password_hash, google_id) ON users TO vibecast_app")
    op.execute("""
    CREATE FUNCTION vibecast_admin_set_user_role(target_id uuid, new_role text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    BEGIN
      IF COALESCE(current_setting('app.role', true), '') <> 'platform_admin' THEN
        RAISE EXCEPTION 'platform administrator role required' USING ERRCODE = '42501';
      END IF;
      IF new_role NOT IN ('listener','artist','label_admin','platform_admin') THEN
        RAISE EXCEPTION 'invalid role' USING ERRCODE = '22023';
      END IF;
      UPDATE users SET role = new_role, updated_at = now() WHERE id = target_id;
      IF NOT FOUND THEN RAISE EXCEPTION 'user not found' USING ERRCODE = 'P0002'; END IF;
    END
    $$;
    REVOKE ALL ON FUNCTION vibecast_admin_set_user_role(uuid, text) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION vibecast_admin_set_user_role(uuid, text) TO vibecast_app;
    """)

    op.execute("""
    CREATE FUNCTION vibecast_rollup_play() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    BEGIN
      IF NEW.qualified THEN
        INSERT INTO user_song_stats (id, user_id, song_id, qualified_plays, listening_seconds, last_played_at)
        VALUES (gen_random_uuid(), NEW.user_id, NEW.song_id, 1, NEW.duration_played_seconds, NEW.played_at)
        ON CONFLICT (user_id, song_id) DO UPDATE SET
          qualified_plays = user_song_stats.qualified_plays + 1,
          listening_seconds = user_song_stats.listening_seconds + EXCLUDED.listening_seconds,
          last_played_at = GREATEST(user_song_stats.last_played_at, EXCLUDED.last_played_at);

        INSERT INTO user_daily_stats (id, user_id, day, qualified_plays, listening_seconds)
        VALUES (gen_random_uuid(), NEW.user_id, (NEW.played_at AT TIME ZONE 'UTC')::date, 1, NEW.duration_played_seconds)
        ON CONFLICT (user_id, day) DO UPDATE SET
          qualified_plays = user_daily_stats.qualified_plays + 1,
          listening_seconds = user_daily_stats.listening_seconds + EXCLUDED.listening_seconds;

        INSERT INTO artist_daily_stats (id, artist_profile_id, song_id, day, qualified_plays, listening_seconds)
        SELECT gen_random_uuid(), s.artist_profile_id, s.id, (NEW.played_at AT TIME ZONE 'UTC')::date,
               1, NEW.duration_played_seconds
        FROM songs s WHERE s.id = NEW.song_id AND s.artist_profile_id IS NOT NULL
        ON CONFLICT (artist_profile_id, song_id, day) DO UPDATE SET
          qualified_plays = artist_daily_stats.qualified_plays + 1,
          listening_seconds = artist_daily_stats.listening_seconds + EXCLUDED.listening_seconds;
      END IF;
      RETURN NEW;
    END
    $$;
    CREATE TRIGGER play_event_rollup AFTER INSERT ON play_events
      FOR EACH ROW EXECUTE FUNCTION vibecast_rollup_play();

    CREATE OR REPLACE VIEW artist_song_performance WITH (security_invoker = true) AS
      SELECT s.artist_profile_id, s.id AS song_id, s.title,
             COALESCE(SUM(ads.qualified_plays), 0) AS qualified_plays,
             COALESCE(SUM(ads.listening_seconds), 0) AS listening_seconds,
             MAX(ads.day) AS last_played_at
      FROM songs s LEFT JOIN artist_daily_stats ads ON ads.song_id = s.id
      WHERE s.source = 'artist_upload' GROUP BY s.artist_profile_id, s.id, s.title;
    """)

    # The migration owner creates a separate runtime role in the deployment bootstrap.
    op.execute("GRANT USAGE ON SCHEMA public TO vibecast_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO vibecast_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO vibecast_app")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS artist_song_performance")
    op.execute("DROP FUNCTION IF EXISTS vibecast_rollup_play() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS vibecast_app_user_id() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS vibecast_app_role() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS vibecast_is_worker() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS vibecast_admin_set_user_role(uuid, text) CASCADE")
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
