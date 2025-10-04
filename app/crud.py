from typing import Optional, Tuple

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from .database import get_session
from .models import Media, MediaType, Playlist, PlaylistItem, User, UserRole


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def init_admins(emails: list[str]) -> None:
    for email in emails:
        if not email:
            continue
        normalized = _normalize_email(email)
        with get_session() as session:
            user = _get_user_by_email(session, normalized)
            if user:
                user.role = UserRole.admin
                user.active = True
                session.add(user)
            else:
                session.add(User(email=normalized, role=UserRole.admin, active=True))


def get_user_by_email(email: str) -> Optional[User]:
    with get_session() as session:
        return _get_user_by_email(session, _normalize_email(email))


def _get_user_by_email(session: Session, email: str) -> Optional[User]:
    statement = select(User).where(User.email == email)
    return session.exec(statement).first()


def get_user_by_id(user_id: int) -> Optional[User]:
    with get_session() as session:
        return session.get(User, user_id)


def create_user(email: str, name: str | None, picture: str | None, role: UserRole = UserRole.viewer) -> User:
    with get_session() as session:
        user = User(email=_normalize_email(email), name=name, picture=picture, role=role)
        session.add(user)
        session.flush()
        session.refresh(user)
        return user


def ensure_user(email: str, name: str | None, picture: str | None, *, create_if_missing: bool = True) -> Optional[User]:
    normalized_email = _normalize_email(email)
    with get_session() as session:
        user = _get_user_by_email(session, normalized_email)
        if user:
            if name and user.name != name:
                user.name = name
            if picture and user.picture != picture:
                user.picture = picture
            session.add(user)
        elif create_if_missing:
            user = User(email=normalized_email, name=name, picture=picture, role=UserRole.viewer)
            session.add(user)
        else:
            return None
        session.flush()
        session.refresh(user)
        return user


def list_users() -> list[User]:
    with get_session() as session:
        return list(session.exec(select(User)))


def update_user_role(user_id: int, role: UserRole) -> None:
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        user.role = role
        session.add(user)


def set_user_active(user_id: int, active: bool) -> None:
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        user.active = active
        session.add(user)


def add_or_activate_user(email: str, name: str | None, role: UserRole = UserRole.viewer) -> Tuple[User, bool]:
    normalized_email = _normalize_email(email)
    with get_session() as session:
        user = _get_user_by_email(session, normalized_email)
        created = False
        if user:
            user.active = True
            if name:
                user.name = name
            if role and user.role != role:
                user.role = role
            session.add(user)
        else:
            user = User(email=normalized_email, name=name, role=role, active=True)
            session.add(user)
            created = True
        session.flush()
        session.refresh(user)
        return user, created


def list_media() -> list[Media]:
    with get_session() as session:
        return list(session.exec(select(Media)))


def list_playlists() -> list[Playlist]:
    with get_session() as session:
        statement = select(Playlist).options(
            selectinload(Playlist.items).selectinload(PlaylistItem.media)
        )
        return list(session.exec(statement))


def get_playlist(playlist_id: int) -> Optional[Playlist]:
    with get_session() as session:
        statement = select(Playlist).options(
            selectinload(Playlist.items).selectinload(PlaylistItem.media)
        ).where(Playlist.id == playlist_id)
        return session.exec(statement).first()


def create_playlist(name: str, description: str | None, owner_id: int | None = None) -> Playlist:
    with get_session() as session:
        playlist = Playlist(name=name.strip(), description=description, owner_id=owner_id)
        session.add(playlist)
        session.flush()
        session.refresh(playlist)
        return playlist


def update_playlist(playlist_id: int, *, name: str | None = None, description: str | None = None) -> Playlist:
    with get_session() as session:
        playlist = session.get(Playlist, playlist_id)
        if not playlist:
            raise ValueError("Playlist not found")
        if name is not None:
            playlist.name = name.strip()
        if description is not None:
            playlist.description = description
        session.add(playlist)
        session.flush()
        session.refresh(playlist)
        return playlist


def delete_playlist(playlist_id: int) -> None:
    with get_session() as session:
        playlist = session.get(Playlist, playlist_id)
        if not playlist:
            raise ValueError("Playlist not found")
        session.delete(playlist)


def set_playlist_items(playlist_id: int, media_ids: list[int]) -> Playlist:
    with get_session() as session:
        playlist = session.get(Playlist, playlist_id)
        if not playlist:
            raise ValueError("Playlist not found")

        session.exec(select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id)).delete()

        for position, media_id in enumerate(media_ids):
            session.add(PlaylistItem(playlist_id=playlist_id, media_id=media_id, position=position))

        session.flush()
        session.refresh(playlist)
        return playlist


def add_media_to_playlist(playlist_id: int, media_id: int, position: int | None = None) -> PlaylistItem:
    with get_session() as session:
        playlist = session.get(Playlist, playlist_id)
        if not playlist:
            raise ValueError("Playlist not found")
        media = session.get(Media, media_id)
        if not media:
            raise ValueError("Media not found")
        if position is None:
            existing_count = session.exec(select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id)).count()
            position = existing_count
        item = PlaylistItem(playlist_id=playlist_id, media_id=media_id, position=position)
        session.add(item)
        session.flush()
        session.refresh(item)
        return item


def remove_media_from_playlist(playlist_id: int, media_id: int) -> None:
    with get_session() as session:
        item = session.get(PlaylistItem, (playlist_id, media_id))
        if not item:
            raise ValueError("Playlist item not found")
        session.delete(item)


def create_media(
    filename: str,
    original_filename: str | None,
    media_type: MediaType,
    mime_type: str,
    url: str,
    thumbnail_url: str | None,
    title: str | None,
    description: str | None,
    tags: list[str],
    playlists: list[str],
    owner_id: int | None = None,
) -> Media:
    with get_session() as session:
        media = Media(
            filename=filename,
            original_filename=original_filename,
            media_type=media_type,
            mime_type=mime_type,
            url=url,
            thumbnail_url=thumbnail_url,
            title=title,
            description=description,
            tags=tags,
            playlists=playlists,
            owner_id=owner_id,
        )
        session.add(media)
        session.flush()
        session.refresh(media)
        return media


def delete_media(filename: str) -> None:
    with get_session() as session:
        media = session.exec(select(Media).where(Media.filename == filename)).first()
        if not media:
            raise ValueError("Media not found")
        session.delete(media)


def get_media_by_filename(filename: str) -> Optional[Media]:
    with get_session() as session:
        return session.exec(select(Media).where(Media.filename == filename)).first()


def update_media(
    filename: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    playlists: Optional[list[str]] = None,
) -> Media:
    with get_session() as session:
        media = session.exec(select(Media).where(Media.filename == filename)).first()
        if not media:
            raise ValueError("Media not found")
        if title is not None:
            media.title = title
        if description is not None:
            media.description = description
        if tags is not None:
            media.tags = tags
        if playlists is not None:
            media.playlists = playlists
        session.add(media)
        session.flush()
        session.refresh(media)
        return media
