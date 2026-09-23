from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.db.models import PlayEvent, Song
from app.db.session import get_db
from app.schemas.activity import PlayEventCreate, PlayEventOut

router = APIRouter(prefix="/plays", tags=["listening history"])


def is_qualified_play(duration_seconds: int, track_duration_seconds: int | None) -> bool:
    return duration_seconds > 0 and (
        duration_seconds >= 30
        or (track_duration_seconds is not None and track_duration_seconds > 0
            and duration_seconds / track_duration_seconds >= 0.8)
    )


@router.post("", response_model=PlayEventOut, status_code=201)
def record_play(payload: PlayEventCreate, user: CurrentUser, db: Session = Depends(get_db)):
    existing = db.scalar(select(PlayEvent).where(
        PlayEvent.client_event_id == payload.client_event_id, PlayEvent.user_id == user.id))
    if existing:
        return existing
    song = db.scalar(select(Song).where(Song.id == payload.song_id, Song.is_public.is_(True)))
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    now = datetime.now(UTC)
    played_at = payload.played_at or now
    if played_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="played_at must include a timezone")
    if played_at > now + timedelta(minutes=5) or played_at < now - timedelta(days=7):
        raise HTTPException(status_code=422, detail="Playback time is outside the accepted window")
    duration = payload.duration_played_seconds
    if song.duration_seconds:
        duration = min(duration, song.duration_seconds + 2)
    qualified = is_qualified_play(duration, song.duration_seconds)
    event = PlayEvent(client_event_id=payload.client_event_id, user_id=user.id,
                      song_id=song.id, played_at=played_at, duration_played_seconds=duration,
                      qualified=qualified)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/history", response_model=list[PlayEventOut])
def play_history(user: CurrentUser, db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200)):
    return db.scalars(select(PlayEvent).where(PlayEvent.user_id == user.id)
                      .order_by(PlayEvent.played_at.desc()).limit(limit)).all()
