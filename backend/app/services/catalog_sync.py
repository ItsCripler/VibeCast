from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Album, CatalogArtist, CatalogSyncRun, Job, Song, SongEmbedding
from app.integrations.jamendo import JamendoAPIError, JamendoClient, JamendoTrack

EMBEDDING_VERSION = "v1"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class CatalogSyncService:
    def __init__(self, db: Session, client: JamendoClient | None = None):
        self.db = db
        self.client = client or JamendoClient()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def sync(self, *, requested_by: uuid.UUID | None = None, max_tracks: int | None = None,
             page_size: int | None = None, searches: list[str] | None = None) -> CatalogSyncRun:
        max_tracks = max_tracks or settings.jamendo_max_tracks
        page_size = min(page_size or settings.jamendo_page_size, 200)
        searches = searches if searches is not None else [
            term.strip() for term in settings.jamendo_search_queries.split(",") if term.strip()
        ]
        if not searches:
            searches = [""]
        run = CatalogSyncRun(requested_by=requested_by, configured_max_tracks=max_tracks)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        run_id = run.id
        processed = 0
        try:
            for search in searches:
                offset = 0
                while processed < max_tracks:
                    batch_limit = min(page_size, max_tracks - processed)
                    tracks = self.client.get_tracks(limit=batch_limit, offset=offset, search=search or None)
                    run.pages_fetched += 1
                    if not tracks:
                        self.db.commit()
                        break
                    seen_ids: set[str] = set()
                    page = [track for track in tracks if not (track.track_id in seen_ids or seen_ids.add(track.track_id))]
                    self._upsert_page(page)
                    processed += len(tracks)
                    run.tracks_seen = processed
                    run.tracks_upserted += len(page)
                    self.db.commit()
                    offset += len(tracks)
                    if len(tracks) < batch_limit:
                        break
            run.status = "complete"
            run.finished_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(run)
            return run
        except JamendoAPIError as exc:
            self.db.rollback()
            failed_run = self.db.get(CatalogSyncRun, run_id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error_summary = str(exc)[:500]
                failed_run.finished_at = datetime.now(UTC)
                self.db.commit()
            raise
        except Exception:
            self.db.rollback()
            failed_run = self.db.get(CatalogSyncRun, run_id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error_summary = "Unexpected catalog synchronization error"
                failed_run.finished_at = datetime.now(UTC)
                self.db.commit()
            raise

    def _upsert_page(self, tracks: list[JamendoTrack]) -> None:
        if not tracks:
            return
        now = datetime.now(UTC)
        artist_rows: dict[str, dict] = {}
        for track in tracks:
            if track.artist_id:
                artist_rows[track.artist_id] = {
                    "jamendo_artist_id": track.artist_id,
                    "name": track.artist_name,
                    "source_url": f"https://www.jamendo.com/artist/{track.artist_id}",
                    "last_synced_at": now,
                    "updated_at": now,
                }
        artist_ids: dict[str, uuid.UUID] = {}
        if artist_rows:
            stmt = pg_insert(CatalogArtist).values(list(artist_rows.values()))
            stmt = stmt.on_conflict_do_update(
                index_elements=[CatalogArtist.jamendo_artist_id],
                set_={"name": stmt.excluded.name, "source_url": stmt.excluded.source_url,
                      "last_synced_at": stmt.excluded.last_synced_at, "updated_at": now},
            ).returning(CatalogArtist.id, CatalogArtist.jamendo_artist_id)
            artist_ids = {external_id: internal_id for internal_id, external_id in self.db.execute(stmt)}

        album_rows: dict[str, dict] = {}
        for track in tracks:
            if track.album_id:
                album_rows[track.album_id] = {
                    "jamendo_album_id": track.album_id,
                    "title": track.album_name or track.title,
                    "catalog_artist_id": artist_ids.get(track.artist_id or ""),
                    "artwork_url": track.album_image or track.artwork_url,
                    "source": "jamendo",
                    "released_at": _parse_date(track.released_at),
                    "last_synced_at": now,
                }
        album_ids: dict[str, uuid.UUID] = {}
        if album_rows:
            stmt = pg_insert(Album).values(list(album_rows.values()))
            stmt = stmt.on_conflict_do_update(
                index_elements=[Album.jamendo_album_id],
                set_={"title": stmt.excluded.title, "catalog_artist_id": stmt.excluded.catalog_artist_id,
                      "artwork_url": stmt.excluded.artwork_url, "released_at": stmt.excluded.released_at,
                      "last_synced_at": now},
            ).returning(Album.id, Album.jamendo_album_id)
            album_ids = {external_id: internal_id for internal_id, external_id in self.db.execute(stmt)}

        song_rows: dict[str, dict] = {}
        for track in tracks:
            song_rows[track.track_id] = {
                "source": "jamendo",
                "jamendo_track_id": track.track_id,
                "album_id": album_ids.get(track.album_id or ""),
                "catalog_artist_id": artist_ids.get(track.artist_id or ""),
                "title": track.title,
                "artist_name": track.artist_name,
                "duration_seconds": track.duration_seconds,
                "released_at": _parse_date(track.released_at),
                "tags": track.tags,
                "jamendo_musicinfo": track.musicinfo,
                "artwork_url": track.artwork_url or track.album_image,
                "source_url": track.source_url,
                "audio_url": track.audio_url,
                "audio_url_checked_at": now if track.audio_url else None,
                "license_url": track.license_url,
                "audiodownload_allowed": track.audiodownload_allowed,
                "is_public": True,
                "analysis_status": "pending" if (track.audiodownload_allowed and track.license_url and
                                                   "creativecommons.org/licenses/" in track.license_url.lower())
                                   else "unavailable",
                "last_synced_at": now,
                "updated_at": now,
            }
        stmt = pg_insert(Song).values(list(song_rows.values()))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Song.jamendo_track_id],
            set_={key: getattr(stmt.excluded, key) for key in song_rows[next(iter(song_rows))]
                  if key not in {"jamendo_track_id", "source", "analysis_status"}},
        ).returning(Song.id, Song.jamendo_track_id)
        song_ids = {external_id: internal_id for internal_id, external_id in self.db.execute(stmt)}

        internal_ids = list(song_ids.values())
        embedded_ids = set(self.db.scalars(select(SongEmbedding.song_id).where(
            SongEmbedding.song_id.in_(internal_ids),
            SongEmbedding.model_name == settings.embedding_model,
            SongEmbedding.model_version == EMBEDDING_VERSION,
        ))) if internal_ids else set()
        jobs = [
            Job(kind="embed_song", idempotency_key=f"embed:{song_id}:{EMBEDDING_VERSION}",
                payload={"song_id": str(song_id), "version": EMBEDDING_VERSION})
            for song_id in internal_ids if song_id not in embedded_ids
        ]
        if jobs:
            stmt = pg_insert(Job).values([
                {"kind": job.kind, "idempotency_key": job.idempotency_key, "payload": job.payload}
                for job in jobs
            ]).on_conflict_do_nothing(index_elements=[Job.idempotency_key])
            self.db.execute(stmt)

        statuses = {song_id: status for song_id, status in
                    self.db.execute(select(Song.id, Song.analysis_status).where(Song.id.in_(internal_ids)))}
        track_by_internal_id = {song_ids[external_id]: track for external_id, track in
                                ((track.track_id, track) for track in tracks)}
        analysis_jobs = []
        for song_id, status in statuses.items():
            track = track_by_internal_id[song_id]
            if status == "pending" and track.audiodownload_allowed and track.license_url and \
                    "creativecommons.org/licenses/" in track.license_url.lower():
                analysis_jobs.append({
                    "kind": "analyze_song", "idempotency_key": f"jamendo-analysis:{song_id}:v1",
                    "payload": {"song_id": str(song_id)},
                })
        if analysis_jobs:
            self.db.execute(pg_insert(Job).values(analysis_jobs)
                            .on_conflict_do_nothing(index_elements=[Job.idempotency_key]))


def run_catalog_sync(db: Session, *, requested_by: uuid.UUID | None = None,
                     max_tracks: int | None = None, page_size: int | None = None) -> CatalogSyncRun:
    service = CatalogSyncService(db)
    try:
        return service.sync(requested_by=requested_by, max_tracks=max_tracks, page_size=page_size)
    finally:
        service.close()
