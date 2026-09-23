from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ItemSimilarity, PlayEvent, Song, SongEmbedding, UserSongStat
from app.recommendations.embeddings import normalize_vector


def normalize_scores(values: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if high == low:
        return {key: 1.0 if high > 0 else 0.0 for key in values}
    return {key: (value - low) / (high - low) for key, value in values.items()}


def _interaction_weight(play_count: int, last_played_at: datetime) -> float:
    age_days = max(0.0, (datetime.now(UTC) - last_played_at).total_seconds() / 86400)
    capped = min(4.0, 1.0 + math.log1p(max(0, play_count)))
    return capped * math.exp(-age_days / 90.0)


def train_item_similarity(db: Session, *, max_neighbors: int = 50,
                           max_items_per_user: int = 100) -> int:
    """Fit weighted item-item cosine similarity from qualified, real/simulated plays."""
    statement = select(UserSongStat.user_id, UserSongStat.song_id,
                       UserSongStat.qualified_plays, UserSongStat.last_played_at).order_by(UserSongStat.user_id)
    rows = db.execute(statement).yield_per(2000)
    by_user: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = defaultdict(list)
    for user_id, song_id, plays, last_played in rows:
        by_user[user_id].append((song_id, _interaction_weight(plays, last_played)))

    pair_products: dict[tuple[uuid.UUID, uuid.UUID], float] = defaultdict(float)
    item_norms: dict[uuid.UUID, float] = defaultdict(float)
    for entries in by_user.values():
        entries.sort(key=lambda pair: (-pair[1], pair[0].hex))
        entries = entries[:max_items_per_user]
        for song_id, weight in entries:
            item_norms[song_id] += weight * weight
        for index, (source_id, source_weight) in enumerate(entries):
            for target_id, target_weight in entries[index + 1:]:
                product = source_weight * target_weight
                pair_products[(source_id, target_id)] += product
                pair_products[(target_id, source_id)] += product

    neighbors: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = defaultdict(list)
    for (source_id, target_id), product in pair_products.items():
        denominator = math.sqrt(item_norms[source_id] * item_norms[target_id])
        if denominator:
            neighbors[source_id].append((target_id, product / denominator))
    version = f"itemknn-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    values = []
    for source_id, matches in neighbors.items():
        for target_id, score in sorted(matches, key=lambda item: (-item[1], item[0].hex))[:max_neighbors]:
            values.append({"source_song_id": source_id, "target_song_id": target_id,
                           "score": score, "model_version": version})
    db.execute(delete(ItemSimilarity))
    if values:
        db.execute(pg_insert(ItemSimilarity).values(values))
    db.commit()
    return len(values)


def _artist_key(song: Song) -> str:
    return str(song.catalog_artist_id or song.artist_profile_id or song.artist_name.casefold())


def _diverse(items: list[tuple[Song, float, float, float]], limit: int) -> list[tuple[Song, float, float, float]]:
    counts: dict[str, int] = defaultdict(int)
    result = []
    for item in sorted(items, key=lambda row: (-row[1], row[0].id.hex)):
        key = _artist_key(item[0])
        if counts[key] >= 2:
            continue
        result.append(item)
        counts[key] += 1
        if len(result) >= limit:
            break
    return result


def recommend_for_user(db: Session, user_id: uuid.UUID, *, limit: int = 20) -> list[tuple[Song, float, float, float]]:
    history_rows = db.execute(
        select(UserSongStat, SongEmbedding.vector)
        .join(SongEmbedding, SongEmbedding.song_id == UserSongStat.song_id)
        .where(UserSongStat.user_id == user_id, SongEmbedding.model_name == settings.embedding_model,
               SongEmbedding.model_version == "v1")
    ).all()
    history_weights: dict[uuid.UUID, float] = {}
    vectors = []
    for stats, vector in history_rows:
        weight = _interaction_weight(stats.qualified_plays, stats.last_played_at)
        history_weights[stats.song_id] = weight
        vectors.append((np.asarray(vector, dtype=np.float32), weight))
    profile: list[float] | None = None
    if vectors:
        weighted = sum((vector * weight for vector, weight in vectors), np.zeros_like(vectors[0][0]))
        profile = normalize_vector(weighted).tolist()

    content_raw: dict[uuid.UUID, float] = {}
    if profile:
        distance = SongEmbedding.vector.cosine_distance(profile)
        rows = db.execute(
            select(Song.id, distance.label("distance"))
            .join(SongEmbedding, SongEmbedding.song_id == Song.id)
            .where(Song.is_public.is_(True), SongEmbedding.model_name == settings.embedding_model,
                   SongEmbedding.model_version == "v1")
            .order_by(distance.asc()).limit(500)
        )
        content_raw = {song_id: max(0.0, min(1.0, (1.0 - float(dist) + 1.0) / 2.0))
                       for song_id, dist in rows}

    collab_raw: dict[uuid.UUID, float] = {}
    if history_weights:
        collab_rows = db.execute(
            select(ItemSimilarity.target_song_id, ItemSimilarity.score,
                   UserSongStat.qualified_plays, UserSongStat.last_played_at)
            .join(UserSongStat, UserSongStat.song_id == ItemSimilarity.source_song_id)
            .where(UserSongStat.user_id == user_id)
        )
        for song_id, similarity, plays, last_played in collab_rows:
            collab_raw[song_id] = collab_raw.get(song_id, 0.0) + float(similarity) * _interaction_weight(plays, last_played)

    excluded = set(history_weights)
    # Also avoid repeating recent plays that had not yet crossed the qualified-play threshold.
    recent_ids = set(db.scalars(select(PlayEvent.song_id).where(
        PlayEvent.user_id == user_id,
        PlayEvent.played_at >= datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0),
    )))
    excluded |= recent_ids
    candidate_ids = set(content_raw) | set(collab_raw)
    if not candidate_ids:
        candidate_ids = set(db.scalars(
            select(Song.id).where(Song.is_public.is_(True))
            .order_by(Song.released_at.desc().nullslast(), Song.last_synced_at.desc().nullslast())
            .limit(500)
        ))
    candidate_ids -= excluded
    if not candidate_ids:
        candidate_ids = set(db.scalars(select(Song.id).where(Song.is_public.is_(True)).limit(500)))

    songs = list(db.scalars(select(Song).where(Song.id.in_(candidate_ids), Song.is_public.is_(True)))) if candidate_ids else []
    if not songs:
        return []
    popularity_rows = db.execute(
        select(PlayEvent.song_id, func.count(PlayEvent.id))
        .where(PlayEvent.qualified.is_(True), PlayEvent.played_at >= datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0))
        .group_by(PlayEvent.song_id)
    )
    popularity = normalize_scores({song_id: math.log1p(count) for song_id, count in popularity_rows})
    content = normalize_scores({song_id: score for song_id, score in content_raw.items() if song_id in candidate_ids})
    collaborative = normalize_scores({song_id: score for song_id, score in collab_raw.items() if song_id in candidate_ids})

    ranked = []
    has_collab = bool(collaborative)
    for song in songs:
        content_score = content.get(song.id, 0.0)
        collaborative_score = collaborative.get(song.id, 0.0)
        popularity_score = popularity.get(song.id, 0.0)
        if history_weights and has_collab:
            final_score = settings.recommendation_content_weight * content_score + (1 - settings.recommendation_content_weight) * collaborative_score
        elif history_weights:
            final_score = content_score if content else popularity_score
        else:
            final_score = 0.70 * popularity_score + 0.30 * content_score
        ranked.append((song, final_score, content_score, collaborative_score))
    return _diverse(ranked, limit)
