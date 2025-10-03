from datetime import datetime
from pydantic import BaseModel, Field


class MediaItem(BaseModel):
    id: int | None = None
    filename: str
    url: str
    media_type: str
    thumbnail: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    original_filename: str | None = None
    uploaded_at: str | None = None


class MediaCreate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class MediaUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class UserRead(BaseModel):
    id: int
    email: str
    name: str | None
    picture: str | None
    role: str
    active: bool
