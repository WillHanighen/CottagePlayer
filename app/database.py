from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlmodel import Session

from .config import get_settings

_settings = get_settings()
database_url = _settings.database_connection_url
connect_args = {}
if database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(database_url, connect_args=connect_args)


def ensure_media_schema() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "media" in table_names:
        existing_columns = {column["name"] for column in inspector.get_columns("media")}

        statements: list[str] = []
        if "original_filename" not in existing_columns:
            statements.append("ALTER TABLE media ADD COLUMN original_filename VARCHAR")
        if "thumbnail_url" not in existing_columns:
            statements.append("ALTER TABLE media ADD COLUMN thumbnail_url VARCHAR")
        if "created_at" not in existing_columns:
            statements.append("ALTER TABLE media ADD COLUMN created_at TIMESTAMP")
        if "playlists" not in existing_columns:
            statements.append("ALTER TABLE media ADD COLUMN playlists JSON")

        if statements:
            with engine.begin() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
                if "created_at" not in existing_columns:
                    conn.execute(text("UPDATE media SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
                if "playlists" not in existing_columns:
                    conn.execute(text("UPDATE media SET playlists = '[]' WHERE playlists IS NULL"))

    if "playlists" not in table_names:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    description TEXT,
                    owner_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(owner_id) REFERENCES users(id)
                )
            """))

    if "playlist_items" not in table_names:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE playlist_items (
                    playlist_id INTEGER NOT NULL,
                    media_id INTEGER NOT NULL,
                    position INTEGER DEFAULT 0,
                    PRIMARY KEY (playlist_id, media_id),
                    FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                    FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE
                )
            """))


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
