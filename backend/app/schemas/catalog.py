import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class SongOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    jamendo_track_id: str | None
    title: str
    artist_name: str
    duration_seconds: int | None
    released_at: date | None
    tags: list[str]
    artwork_url: str | None
    source_url: str | None
    license_url: str | None
    audiodownload_allowed: bool


class ArtistSongOut(SongOut):
    analysis_status: str
    is_public: bool


class PlaybackOut(BaseModel):
    song_id: uuid.UUID
    url: str
    source: str
    source_url: str | None
    license_url: str | None
    audiodownload_allowed: bool


class CatalogPage(BaseModel):
    items: list[SongOut]
    page: int
    page_size: int
    total: int


class CatalogArtistOut(BaseModel):
    id: uuid.UUID
    jamendo_artist_id: str
    name: str
    source_url: str | None
    image_url: str | None


class AlbumOut(BaseModel):
    id: uuid.UUID
    title: str
    artwork_url: str | None
    jamendo_album_id: str | None
    songs: list[SongOut]
