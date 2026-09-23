from __future__ import annotations

import re
import uuid
from functools import lru_cache
from threading import Lock
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Song, SongEmbedding, SongFeature
from app.services.catalog_sync import EMBEDDING_VERSION

_model_lock = Lock()


@lru_cache(maxsize=1)
def _sentence_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return normalized sentence-transformer vectors with a checked dimension."""
    if not texts:
        return np.empty((0, settings.embedding_dimensions), dtype=np.float32)
    with _model_lock:
        vectors = np.asarray(
            _sentence_model().encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                                     show_progress_bar=False), dtype=np.float32
        )
    if vectors.ndim != 2 or vectors.shape != (len(texts), settings.embedding_dimensions):
        raise ValueError(f"Embedding model returned unexpected shape {vectors.shape}")
    return vectors


def song_representation(song: Song, feature: SongFeature | None = None) -> str:
    parts = [f"Track title: {song.title}.", f"Artist: {song.artist_name}."]
    if song.tags:
        parts.append("Jamendo tags: " + ", ".join(sorted({str(tag).lower() for tag in song.tags})) + ".")
    music_tags = (song.jamendo_musicinfo or {}).get("tags", {})
    if isinstance(music_tags, dict):
        groups = [f"{category}: {', '.join(map(str, values))}" for category, values in music_tags.items()
                  if isinstance(values, list) and values]
        if groups:
            parts.append("Jamendo music information: " + "; ".join(groups) + ".")
    if feature and feature.essentia_values:
        descriptors = ", ".join(f"{key}: {value}" for key, value in sorted(feature.essentia_values.items()))
        parts.append(f"Locally extracted Essentia descriptors: {descriptors}.")
    if feature and feature.derived_values:
        descriptors = ", ".join(f"{key}: {value}" for key, value in sorted(feature.derived_values.items()))
        parts.append(f"Derived descriptors: {descriptors}.")
    return " ".join(parts)


def persist_song_embedding(db: Session, song_id: str) -> None:
    song = db.scalar(select(Song).where(Song.id == uuid.UUID(song_id)))
    if song is None:
        return
    feature = db.get(SongFeature, song.id)
    representation = song_representation(song, feature)
    vector = embed_texts([representation])[0].tolist()
    statement = pg_insert(SongEmbedding).values(
        song_id=song.id,
        model_name=settings.embedding_model,
        model_version=EMBEDDING_VERSION,
        representation=representation,
        vector=vector,
    ).on_conflict_do_update(
        index_elements=[SongEmbedding.song_id],
        set_={"model_name": settings.embedding_model, "model_version": EMBEDDING_VERSION,
              "representation": representation, "vector": vector},
    )
    db.execute(statement)
    if song.source == "artist_upload":
        song.is_public = True
    db.commit()


def normalize_vector(vector: Any) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if not norm:
        raise ValueError("Cannot normalize a zero-length embedding")
    return arr / norm


def prompt_tokens(prompt: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "into", "during", "music", "song", "songs", "that", "this", "a", "an", "to", "of", "in", "on", "at", "by", "me", "my"}
    return {token for token in re.findall(r"[a-z0-9]+", prompt.lower()) if len(token) > 2 and token not in stop}
