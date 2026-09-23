import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.db.models import ArtistDailyStat, ArtistProfile, Label, LabelMember, Song, User
from app.db.session import get_db

router = APIRouter(prefix="/labels", tags=["labels"])


def _authorized_label_ids(db: Session, user: User) -> list[uuid.UUID]:
    if user.role == "platform_admin":
        return list(db.scalars(select(Label.id).order_by(Label.name)))
    if user.role != "label_admin":
        raise HTTPException(status_code=403, detail="Label administrator access required")
    return list(db.scalars(select(LabelMember.label_id).where(
        LabelMember.user_id == user.id, LabelMember.membership_role == "admin")))


@router.get("/me")
def my_labels(user: CurrentUser, db: Session = Depends(get_db)):
    label_ids = _authorized_label_ids(db, user)
    labels = db.scalars(select(Label).where(Label.id.in_(label_ids)).order_by(Label.name)).all() if label_ids else []
    return [{"id": label.id, "name": label.name} for label in labels]


@router.get("/{label_id}/artists")
def label_artists(label_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db)):
    if label_id not in _authorized_label_ids(db, user):
        raise HTTPException(status_code=404, detail="Label not found")
    rows = db.execute(select(ArtistProfile, User.name, User.email)
                      .join(User, User.id == ArtistProfile.user_id)
                      .where(ArtistProfile.label_id == label_id)
                      .order_by(ArtistProfile.stage_name)).all()
    return [{"artist_profile_id": profile.id, "stage_name": profile.stage_name,
             "user_id": profile.user_id, "name": name, "email": email} for profile, name, email in rows]


@router.get("/{label_id}/performance")
def label_performance(label_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db),
                      days: int = Query(30, ge=7, le=365)):
    if label_id not in _authorized_label_ids(db, user):
        raise HTTPException(status_code=404, detail="Label not found")
    query = (
        select(ArtistProfile.id, ArtistProfile.stage_name, Song.id, Song.title,
               func.coalesce(func.sum(ArtistDailyStat.qualified_plays), 0).label("plays"),
               func.coalesce(func.sum(ArtistDailyStat.listening_seconds), 0).label("seconds"))
        .join(Song, Song.artist_profile_id == ArtistProfile.id)
        .outerjoin(ArtistDailyStat, ArtistDailyStat.song_id == Song.id)
        .where(ArtistProfile.label_id == label_id, Song.source == "artist_upload",
               (ArtistDailyStat.day >= datetime.now(UTC).date() - timedelta(days=days)) | (ArtistDailyStat.day.is_(None)))
        .group_by(ArtistProfile.id, ArtistProfile.stage_name, Song.id, Song.title)
        .order_by(func.sum(ArtistDailyStat.qualified_plays).desc().nullslast())
    )
    rows = db.execute(query).all()
    return [{"artist_profile_id": artist_id, "artist_name": stage_name,
             "song_id": song_id, "title": title, "qualified_plays": int(plays),
             "listening_seconds": int(seconds)} for artist_id, stage_name, song_id, title, plays, seconds in rows]
