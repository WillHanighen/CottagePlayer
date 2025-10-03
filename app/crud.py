from typing import Optional, Tuple

from sqlmodel import Session, select

from .database import get_session
from .models import Media, MediaType, User, UserRole


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
