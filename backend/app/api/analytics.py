from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.db.models import PlayEvent, Song, SongFeature, UserDailyStat
from app.db.session import get_db
from app.recommendations.hybrid import recommend_for_user
from app.schemas.catalog import SongOut

router = APIRouter(prefix="/users/me", tags=["analytics and recommendations"])


@router.get("/recommendations")
def recommendations(user: CurrentUser, db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100)):
    results = recommend_for_user(db, user.id, limit=limit)
    return [{"song": SongOut.model_validate(song), "score": round(score, 4), "content_score": round(content, 4),
             "collaborative_score": round(collab, 4)} for song, score, content, collab in results]


@router.get("/stats")
def listening_stats(user: CurrentUser, db: Session = Depends(get_db), days: int = Query(30, ge=7, le=365)):
    start_day = datetime.now(UTC).date() - timedelta(days=days - 1)
    start_at = datetime.combine(start_day, datetime.min.time(), tzinfo=UTC)
    event_filter = (PlayEvent.user_id == user.id, PlayEvent.qualified.is_(True), PlayEvent.played_at >= start_at)
    totals = db.execute(
        select(func.coalesce(func.sum(PlayEvent.duration_played_seconds), 0),
               func.count(PlayEvent.id), func.count(func.distinct(Song.id)),
               func.count(func.distinct(Song.artist_name)))
        .join(Song, Song.id == PlayEvent.song_id)
        .where(*event_filter)
    ).one()
    top_songs = db.execute(
        select(Song.id, Song.title, Song.artist_name, Song.artwork_url,
               func.count(PlayEvent.id).label("plays"),
               func.sum(PlayEvent.duration_played_seconds).label("seconds"))
        .join(PlayEvent, PlayEvent.song_id == Song.id)
        .where(*event_filter)
        .group_by(Song.id)
        .order_by(func.count(PlayEvent.id).desc(), func.sum(PlayEvent.duration_played_seconds).desc())
        .limit(10)
    ).all()
    top_artists = db.execute(
        select(Song.artist_name, func.count(PlayEvent.id).label("plays"),
               func.sum(PlayEvent.duration_played_seconds).label("seconds"))
        .join(PlayEvent, PlayEvent.song_id == Song.id)
        .where(*event_filter)
        .group_by(Song.artist_name)
        .order_by(func.count(PlayEvent.id).desc()).limit(10)
    ).all()
    tags = Counter()
    moods = Counter()
    tag_rows = db.execute(
        select(Song.id, Song.tags, SongFeature.derived_values, SongFeature.essentia_values,
               func.count(PlayEvent.id).label("plays"))
        .join(PlayEvent, PlayEvent.song_id == Song.id)
        .outerjoin(SongFeature, SongFeature.song_id == Song.id)
        .where(*event_filter)
        .group_by(Song.id, Song.tags, SongFeature.derived_values, SongFeature.essentia_values)
    ).all()
    for _song_id, song_tags, derived, essentia, plays in tag_rows:
        for tag in song_tags or []:
            tags[str(tag).lower()] += int(plays)
        descriptors = {**(derived or {}), **(essentia or {})}
        mood = descriptors.get("mood") or descriptors.get("mood_category")
        if mood:
            moods[str(mood).lower()] += int(plays)

    daily = {day: (count, seconds) for day, count, seconds in db.execute(
        select(UserDailyStat.day, UserDailyStat.qualified_plays, UserDailyStat.listening_seconds)
        .where(UserDailyStat.user_id == user.id, UserDailyStat.day >= start_day)
        .order_by(UserDailyStat.day.asc())
    )}
    trend = [{"date": (start_day + timedelta(days=offset)).isoformat(),
              "qualified_plays": daily.get(start_day + timedelta(days=offset), (0, 0))[0],
              "listening_seconds": daily.get(start_day + timedelta(days=offset), (0, 0))[1]}
             for offset in range(days)]
    top_genres = [{"name": name, "qualified_plays": count} for name, count in tags.most_common(10)]
    top_moods = [{"name": name, "qualified_plays": count} for name, count in moods.most_common(10)]
    personality_tags = [name for name, _count in tags.most_common(3)]
    personality = ("Your listening currently leans toward " + ", ".join(personality_tags) + ".") if personality_tags else "Keep listening to build your music profile."
    return {
        "total_listening_seconds": int(totals[0]),
        "qualified_plays": int(totals[1]),
        "distinct_songs": int(totals[2]),
        "distinct_artists": int(totals[3]),
        "top_songs": [{"song_id": row.id, "title": row.title, "artist_name": row.artist_name,
                       "artwork_url": row.artwork_url, "qualified_plays": int(row.plays),
                       "listening_seconds": int(row.seconds)} for row in top_songs],
        "top_artists": [{"name": row.artist_name, "qualified_plays": int(row.plays),
                         "listening_seconds": int(row.seconds)} for row in top_artists],
        "top_genres_and_tags": top_genres,
        "mood_distribution": top_moods,
        "trend": trend,
        "personality_summary": personality,
        "generated_at": datetime.now(UTC).isoformat(),
    }
