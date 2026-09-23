import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.catalog import SongOut

PlaylistName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]


class PlaylistCreate(BaseModel):
    name: PlaylistName
    is_public: bool = False


class PlaylistUpdate(BaseModel):
    name: PlaylistName | None = None
    is_public: bool | None = None


class VibeRequest(BaseModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
    limit: int = Field(default=25, ge=1, le=100)


class PlaylistSongOut(BaseModel):
    song: SongOut
    position: int
    relevance_score: float | None


class PlaylistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    is_public: bool
    generation_type: str
    original_prompt: str | None
    generated_at: datetime | None
    created_at: datetime
    songs: list[PlaylistSongOut] = Field(default_factory=list)


class ReorderSongs(BaseModel):
    song_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class VibeResult(BaseModel):
    song: SongOut
    score: float
    semantic_score: float
    tag_score: float
    feature_score: float | None


class VibePlaylistOut(BaseModel):
    playlist_id: uuid.UUID
    name: str
    prompt: str
    generated_at: datetime
    results: list[VibeResult]
