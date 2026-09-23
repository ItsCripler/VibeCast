import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

StaffRole = Literal["artist", "label_admin", "platform_admin"]
UserRoleValue = Literal["listener", "artist", "label_admin", "platform_admin"]


class StaffUserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: StaffRole
    label_id: uuid.UUID | None = None


class UserRoleUpdate(BaseModel):
    role: UserRoleValue


class LabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)


class LabelMemberCreate(BaseModel):
    user_id: uuid.UUID
