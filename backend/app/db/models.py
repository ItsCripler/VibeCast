from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db.base import Base


class UserRole(StrEnum):
    listener = "listener"
    artist = "artist"
    label_admin = "label_admin"
    platform_admin = "platform_admin"


class SongSource(StrEnum):
    jamendo = "jamendo"
    artist_upload = "artist_upload"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    retry = "retry"
    complete = "complete"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('listener','artist','label_admin','platform_admin')", name="valid_role"),
        Index("ix_users_email_lower", func.lower(text("email")), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(24), nullable=False, default=UserRole.listener.value)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LabelMember(Base):
    __tablename__ = "label_members"
    __table_args__ = (UniqueConstraint("label_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    label_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("labels.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    membership_role: Mapped[str] = mapped_column(String(24), nullable=False, default="admin")


class ArtistProfile(Base):
    __tablename__ = "artist_profiles"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    label_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("labels.id", ondelete="SET NULL"))
    stage_name: Mapped[str] = mapped_column(String(180), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CatalogArtist(Base):
    __tablename__ = "catalog_artists"
    __table_args__ = (UniqueConstraint("jamendo_artist_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    jamendo_artist_id: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        UniqueConstraint("jamendo_album_id"),
        CheckConstraint("source IN ('jamendo','artist_upload')", name="valid_source"),
        CheckConstraint("(source = 'jamendo' AND jamendo_album_id IS NOT NULL AND artist_profile_id IS NULL) OR (source = 'artist_upload' AND jamendo_album_id IS NULL AND artist_profile_id IS NOT NULL)", name="album_source_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    jamendo_album_id: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    catalog_artist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_artists.id", ondelete="SET NULL"))
    artist_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artist_profiles.id", ondelete="SET NULL"))
    artwork_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="jamendo")
    released_at: Mapped[date | None] = mapped_column(Date)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Song(Base):
    __tablename__ = "songs"
    __table_args__ = (
        CheckConstraint("source IN ('jamendo','artist_upload')", name="valid_source"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="nonnegative_duration"),
        CheckConstraint("(source = 'jamendo' AND jamendo_track_id IS NOT NULL AND artist_profile_id IS NULL) OR (source = 'artist_upload' AND jamendo_track_id IS NULL AND artist_profile_id IS NOT NULL)", name="source_identity"),
        CheckConstraint("analysis_status IN ('pending','completed','failed','unavailable')", name="valid_analysis_status"),
        Index("ix_songs_title", "title"),
        Index("ix_songs_catalog_artist", "catalog_artist_id"),
        Index("ix_songs_artist_profile", "artist_profile_id"),
        Index("ix_songs_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    jamendo_track_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    album_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("albums.id", ondelete="SET NULL"))
    catalog_artist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_artists.id", ondelete="SET NULL"))
    artist_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artist_profiles.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    artist_name: Mapped[str] = mapped_column(String(180), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    released_at: Mapped[date | None] = mapped_column(Date)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    jamendo_musicinfo: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    artwork_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(Text)
    audio_url_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    license_url: Mapped[str | None] = mapped_column(Text)
    upload_rights_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audiodownload_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    upload_path: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    analysis_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SongFeature(Base):
    __tablename__ = "song_features"

    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True)
    essentia_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    derived_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    analyzer_version: Mapped[str | None] = mapped_column(String(100))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SongEmbedding(Base):
    __tablename__ = "song_embeddings"
    __table_args__ = (
        Index("ix_song_embeddings_vector", "vector", postgresql_using="hnsw",
              postgresql_ops={"vector": "vector_cosine_ops"}),
    )

    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(180), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    representation: Mapped[str] = mapped_column(Text, nullable=False)
    vector: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimensions), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (
        CheckConstraint("generation_type IN ('manual','vibe','weekly')", name="valid_generation_type"),
        Index("uq_playlists_owner_weekly", "owner_id", "week_start", unique=True,
              postgresql_where=text("generation_type = 'weekly'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    generation_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    original_prompt: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    week_start: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlaylistSong(Base):
    __tablename__ = "playlist_songs"
    __table_args__ = (
        UniqueConstraint("playlist_id", "song_id"),
        UniqueConstraint("playlist_id", "position"),
        CheckConstraint("position >= 0", name="nonnegative_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    playlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"))
    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlayEvent(Base):
    __tablename__ = "play_events"
    __table_args__ = (
        CheckConstraint("duration_played_seconds >= 0", name="nonnegative_play_duration"),
        Index("ix_play_events_user_played", "user_id", "played_at"),
        Index("ix_play_events_song_played", "song_id", "played_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    duration_played_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    qualified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


class UserSongStat(Base):
    __tablename__ = "user_song_stats"
    __table_args__ = (UniqueConstraint("user_id", "song_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"))
    qualified_plays: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    listening_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserDailyStat(Base):
    __tablename__ = "user_daily_stats"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date, nullable=False)
    qualified_plays: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    listening_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class ArtistDailyStat(Base):
    __tablename__ = "artist_daily_stats"
    __table_args__ = (UniqueConstraint("artist_profile_id", "song_id", "day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    artist_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artist_profiles.id", ondelete="CASCADE"))
    song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date, nullable=False)
    qualified_plays: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    listening_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class ItemSimilarity(Base):
    __tablename__ = "item_similarities"
    __table_args__ = (UniqueConstraint("source_song_id", "target_song_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"))
    target_song_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (CheckConstraint("attempts >= 0", name="nonnegative_attempts"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=JobStatus.queued.value)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CatalogSyncRun(Base):
    __tablename__ = "catalog_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    configured_max_tracks: Mapped[int] = mapped_column(Integer, nullable=False)
    tracks_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tracks_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DemoCounter(Base):
    __tablename__ = "demo_counters"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
