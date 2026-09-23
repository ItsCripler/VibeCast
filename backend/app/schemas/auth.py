import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StaffLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    created_at: datetime
