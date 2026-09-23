import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PlayEventCreate(BaseModel):
    client_event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    song_id: uuid.UUID
    duration_played_seconds: int = Field(ge=0, le=86_400)
    played_at: datetime | None = None


class PlayEventOut(BaseModel):
    id: uuid.UUID
    song_id: uuid.UUID
    played_at: datetime
    duration_played_seconds: int
    qualified: bool
