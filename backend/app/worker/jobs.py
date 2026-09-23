from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Job, JobStatus, Playlist, PlaylistSong, User, UserRole
from app.db.session import SessionLocal, set_rls_context
from app.recommendations.embeddings import persist_song_embedding
from app.recommendations.hybrid import recommend_for_user, train_item_similarity
from app.services.catalog_sync import run_catalog_sync


def _week_start(today: date | None = None) -> date:
    current = today or datetime.now(UTC).date()
    return current - timedelta(days=current.weekday())


def schedule_periodic_jobs(db: Session) -> None:
    week = _week_start()
    year, week_number, _ = week.isocalendar()
    entries = [
        {"idempotency_key": f"itemknn:{year}-W{week_number:02d}", "kind": "train_collaborative",
         "payload": {"week": f"{year}-W{week_number:02d}"}},
        {"idempotency_key": f"weekly-playlists:{week.isoformat()}", "kind": "weekly_playlists",
         "payload": {"week_start": week.isoformat()}},
    ]
    # Retrain is queued before the playlist run so weekly lists use the latest persisted model.
    db.execute(pg_insert(Job).values(entries).on_conflict_do_nothing(index_elements=[Job.idempotency_key]))
    db.commit()


def claim_job(db: Session) -> Job | None:
    now = datetime.now(UTC)
    job = db.scalar(
        select(Job).where(Job.status.in_([JobStatus.queued.value, JobStatus.retry.value]),
                          Job.available_at <= now)
        .order_by(case((Job.kind == "sync_catalog", -1), (Job.kind == "train_collaborative", 0),
                       (Job.kind == "embed_song", 1), (Job.kind == "analyze_song", 2),
                       (Job.kind == "weekly_playlists", 3), else_=4),
                  Job.created_at.asc()).with_for_update(skip_locked=True).limit(1)
    )
    if job is None:
        db.rollback()
        return None
    job.status = JobStatus.running.value
    job.attempts += 1
    job.locked_at = now
    db.commit()
    return job


def recover_abandoned_jobs(db: Session) -> None:
    stale = datetime.now(UTC) - timedelta(minutes=10)
    db.execute(update(Job).where(Job.status == JobStatus.running.value, Job.locked_at < stale)
               .values(status=JobStatus.retry.value, locked_at=None, available_at=datetime.now(UTC)))
    db.commit()


def _run_weekly_playlists(db: Session, job: Job) -> None:
    week = date.fromisoformat(job.payload["week_start"])
    user_ids = list(db.scalars(select(User.id).where(User.is_active.is_(True), User.role == UserRole.listener.value)))
    for user_id in user_ids:
        recommendations = recommend_for_user(db, user_id, limit=30)
        playlist = db.scalar(select(Playlist).where(Playlist.owner_id == user_id,
                                                   Playlist.generation_type == "weekly",
                                                   Playlist.week_start == week))
        if playlist is None:
            playlist = Playlist(owner_id=user_id, name="Your week in music", is_public=False,
                                generation_type="weekly", generated_at=datetime.now(UTC), week_start=week)
            db.add(playlist)
            db.flush()
        else:
            playlist.generated_at = datetime.now(UTC)
            db.execute(delete(PlaylistSong).where(PlaylistSong.playlist_id == playlist.id))
        db.add_all([
            PlaylistSong(playlist_id=playlist.id, song_id=song.id, position=position,
                         relevance_score=score)
            for position, (song, score, _content, _collab) in enumerate(recommendations)
        ])
        db.commit()


def _execute(db: Session, job: Job) -> None:
    if job.kind == "embed_song":
        persist_song_embedding(db, job.payload["song_id"])
    elif job.kind == "sync_catalog":
        run_catalog_sync(db, requested_by=uuid.UUID(job.payload["requested_by"])
                         if job.payload.get("requested_by") else None,
                         max_tracks=job.payload.get("max_tracks"), page_size=job.payload.get("page_size"))
    elif job.kind == "train_collaborative":
        train_item_similarity(db)
    elif job.kind == "weekly_playlists":
        _run_weekly_playlists(db, job)
    elif job.kind == "analyze_song":
        from app.services.audio_analysis import analyze_song

        analyze_song(db, job.payload["song_id"])
    else:
        raise ValueError(f"Unsupported job type: {job.kind}")


def process_one(db: Session) -> bool:
    set_rls_context(db, None, "", worker=True)
    job = claim_job(db)
    if job is None:
        return False
    job_id = job.id
    try:
        _execute(db, job)
        db.execute(update(Job).where(Job.id == job_id)
                   .values(status=JobStatus.complete.value, locked_at=None, last_error=None))
        db.commit()
    except Exception as exc:
        db.rollback()
        row = db.get(Job, job_id)
        if row is not None:
            if row.attempts < settings.worker_job_attempts:
                row.status = JobStatus.retry.value
                row.available_at = datetime.now(UTC) + timedelta(seconds=min(30 * 2 ** (row.attempts - 1), 3600))
            else:
                row.status = JobStatus.failed.value
            row.last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
            row.locked_at = None
            db.commit()
    return True


def run_worker(poll_seconds: float | None = None) -> None:
    delay = poll_seconds if poll_seconds is not None else settings.worker_poll_seconds
    with SessionLocal() as db:
        set_rls_context(db, None, "", worker=True)
        recover_abandoned_jobs(db)
    last_schedule = 0.0
    while True:
        now = time.monotonic()
        if now - last_schedule >= 60:
            with SessionLocal() as db:
                set_rls_context(db, None, "", worker=True)
                schedule_periodic_jobs(db)
            last_schedule = now
        with SessionLocal() as db:
            set_rls_context(db, None, "", worker=True)
            did_work = process_one(db)
        if not did_work:
            time.sleep(delay)
