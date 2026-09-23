from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Song, SongEmbedding, SongFeature
from app.recommendations.embeddings import embed_texts, prompt_tokens


@dataclass(frozen=True)
class VibeMatch:
    song: Song
    score: float
    semantic_score: float
    tag_score: float
    feature_score: float | None


FEATURE_INTENTS = {
    "calm": {"energy": "low"}, "relaxing": {"energy": "low"}, "gentle": {"energy": "low"},
    "upbeat": {"energy": "high"}, "energetic": {"energy": "high"}, "intense": {"energy": "high"},
    "melancholic": {"valence": "low"}, "sad": {"valence": "low"}, "joyful": {"valence": "high"},
    "happy": {"valence": "high"}, "danceable": {"danceability": "high"}, "dancing": {"danceability": "high"},
    "slow": {"tempo": "low"}, "fast": {"tempo": "high"},
}


def _tag_score(prompt: str, tags: list[str]) -> float:
    tokens = prompt_tokens(prompt)
    if not tokens or not tags:
        return 0.0
    normalized_tags = {str(tag).strip().lower() for tag in tags}
    tag_words = {word for tag in normalized_tags for word in tag.split()}
    matched = sum(1 for token in tokens if token in normalized_tags or token in tag_words)
    return matched / len(tokens)


def _feature_score(prompt: str, values: dict) -> float | None:
    tokens = prompt_tokens(prompt)
    intents = [intent for token in tokens for intent in FEATURE_INTENTS.get(token, {}).items()]
    if not intents:
        return None
    observed = 0
    matches = 0
    for field, expected in intents:
        alternate_fields = {
            "tempo": ("tempo", "tempo_bpm", "tempo_category"),
            "energy": ("energy", "energy_category"),
            "valence": ("valence", "valence_category"),
            "danceability": ("danceability", "danceability_category"),
        }
        value = next((values[key] for key in alternate_fields[field] if values.get(key) is not None), None)
        if value is None:
            continue
        observed += 1
        if isinstance(value, (int, float)):
            if field == "tempo":
                actual = "low" if value < 90 else "high" if value >= 115 else "mid"
            else:
                actual = "low" if value < 0.4 else "high" if value >= 0.6 else "mid"
        else:
            actual = str(value).lower()
            actual = {"slow": "low", "fast": "high", "moderate": "mid"}.get(actual, actual)
        if actual == expected:
            matches += 1
    return matches / observed if observed else None


def _weighted_score(semantic: float, tags: float, feature: float | None) -> float:
    weights = [(semantic, settings.vibe_semantic_weight), (tags, settings.vibe_tag_weight)]
    if feature is not None:
        weights.append((feature, settings.vibe_feature_weight))
    total = sum(weight for _score, weight in weights)
    if total <= 0:
        return 0.0
    return sum(score * weight for score, weight in weights) / total


def rank_vibe_songs(db: Session, prompt: str, *, limit: int = 30,
                    exclude_song_ids: set[uuid.UUID] | None = None) -> list[VibeMatch]:
    vector = embed_texts([prompt])[0].tolist()
    distance = SongEmbedding.vector.cosine_distance(vector)
    stmt = (select(Song, SongEmbedding, SongFeature, distance.label("distance"))
            .join(SongEmbedding, SongEmbedding.song_id == Song.id)
            .outerjoin(SongFeature, SongFeature.song_id == Song.id)
            .where(Song.is_public.is_(True), SongEmbedding.model_name == settings.embedding_model,
                   SongEmbedding.model_version == "v1")
            .order_by(distance.asc()).limit(min(max(limit * 12, 50), 500)))
    candidates = db.execute(stmt).all()
    prompt_words = prompt.lower()
    matches: list[VibeMatch] = []
    for song, _embedding, feature, distance_value in candidates:
        if exclude_song_ids and song.id in exclude_song_ids:
            continue
        cosine = max(-1.0, min(1.0, 1.0 - float(distance_value)))
        semantic = (cosine + 1.0) / 2.0
        tags = _tag_score(prompt_words, song.tags or [])
        feature_values = {}
        if feature:
            feature_values.update(feature.derived_values or {})
            feature_values.update(feature.essentia_values or {})
        feature_fit = _feature_score(prompt, feature_values)
        score = _weighted_score(semantic, tags, feature_fit)
        matches.append(VibeMatch(song, score, semantic, tags, feature_fit))

    matches.sort(key=lambda item: (-item.score, item.song.id.hex))
    diverse: list[VibeMatch] = []
    artist_counts: dict[str, int] = {}
    for item in matches:
        artist = item.song.catalog_artist_id or item.song.artist_profile_id or item.song.artist_name.lower()
        artist_key = str(artist)
        if artist_counts.get(artist_key, 0) >= 2:
            continue
        diverse.append(item)
        artist_counts[artist_key] = artist_counts.get(artist_key, 0) + 1
        if len(diverse) >= limit:
            break
    return diverse
