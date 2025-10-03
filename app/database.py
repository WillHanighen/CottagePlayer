from contextlib import contextmanager
from typing import Iterator
from datetime import datetime

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
    if "media" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("media")}

    statements: list[str] = []
    if "original_filename" not in existing_columns:
        statements.append("ALTER TABLE media ADD COLUMN original_filename VARCHAR")
    if "thumbnail_url" not in existing_columns:
        statements.append("ALTER TABLE media ADD COLUMN thumbnail_url VARCHAR")
    if "created_at" not in existing_columns:
        statements.append("ALTER TABLE media ADD COLUMN created_at TIMESTAMP")

    if statements:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
            if "created_at" not in existing_columns:
                conn.execute(text("UPDATE media SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
