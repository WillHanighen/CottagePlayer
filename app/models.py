from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint


class UserRole(str, Enum):
    viewer = "viewer"
    uploader = "uploader"
    admin = "admin"


class MediaType(str, Enum):
    image = "image"
    video = "video"
    audio = "audio"


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, nullable=False)
    name: Optional[str] = None
    picture: Optional[str] = None
    role: UserRole = Field(default=UserRole.viewer)
    active: bool = Field(default=True)

    media: list["Media"] = Relationship(back_populates="owner")


class Playlist(SQLModel, table=True):
    __tablename__ = "playlists"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, nullable=False)
    description: Optional[str] = None
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    owner: Optional[User] = Relationship()
    items: list["PlaylistItem"] = Relationship(back_populates="playlist")


class Media(SQLModel, table=True):
    __tablename__ = "media"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str = Field(index=True)
    original_filename: Optional[str] = None
    media_type: MediaType
    mime_type: str
    url: str
    thumbnail_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    playlists: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list))
    duration_seconds: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")
    owner: Optional[User] = Relationship(back_populates="media")
    playlist_items: list["PlaylistItem"] = Relationship(back_populates="media")


class PlaylistItem(SQLModel, table=True):
    __tablename__ = "playlist_items"

    playlist_id: int = Field(foreign_key="playlists.id", primary_key=True)
    media_id: int = Field(foreign_key="media.id", primary_key=True)
    position: int = Field(default=0)

    playlist: Playlist = Relationship(back_populates="items")
    media: Media = Relationship(back_populates="playlist_items")
