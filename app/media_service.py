import mimetypes
import os
import uuid
from pathlib import Path
from typing import Iterable

import cv2
from fastapi import HTTPException, UploadFile, status
from PIL import Image

from .config import get_settings
from .schemas import MediaItem

ALLOWED_MIME_PREFIXES = (
    "image/",
    "video/",
    "audio/",
)


def _validate_mime_type(path: Path, mime: str) -> None:
    if not mime or not mime.startswith(ALLOWED_MIME_PREFIXES):
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only standard image, video, or audio files are allowed.",
        )


def save_media_file(file: UploadFile, title: str | None = None) -> MediaItem:
    settings = get_settings()
    media_root = Path(settings.media_root)
    media_root.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or "").name
    if not original_name:
        raise ValueError("Uploaded file must have a filename")

    safe_name = original_name.replace("/", "_").replace("\\", "_")
    destination = media_root / safe_name
    if destination.exists():
        stem = destination.stem
        suffix = destination.suffix
        destination = media_root / f"{stem}-{uuid.uuid4().hex[:8]}{suffix}"

    with destination.open("wb") as f:
        f.write(file.file.read())

    mime_type = mimetypes.guess_type(destination.name)[0] or "application/octet-stream"
    _validate_mime_type(destination, mime_type)

    thumbnail_name = generate_thumbnail(destination, mime_type)

    url = f"/media/{destination.name}"
    thumbnail_url = f"/media/{thumbnail_name}" if thumbnail_name else None
    return MediaItem(
        filename=destination.name,
        url=url,
        media_type=mime_type,
        thumbnail=thumbnail_url,
        original_filename=original_name,
    )


def list_media_files() -> Iterable[MediaItem]:
    settings = get_settings()
    media_root = Path(settings.media_root)
    if not media_root.exists():
        return []

    items: list[MediaItem] = []
    for path in sorted(media_root.glob("*")):
        if path.is_file():
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if mime_type.startswith(ALLOWED_MIME_PREFIXES):
                thumbnail_path = path.with_suffix(path.suffix + ".thumb.jpg")
                thumbnail_url = f"/media/{thumbnail_path.name}" if thumbnail_path.exists() else None
                items.append(
                    MediaItem(
                        filename=path.name,
                        url=f"/media/{path.name}",
                        media_type=mime_type,
                        thumbnail=thumbnail_url,
                    )
                )
    return items


def generate_thumbnail(path: Path, mime_type: str) -> str | None:
    media_root = path.parent
    thumb_path = path.with_suffix(path.suffix + ".thumb.jpg")

    try:
        if mime_type.startswith("image/"):
            with Image.open(path) as img:
                img = img.convert("RGB")
                img.thumbnail((400, 400))
                img.save(thumb_path, format="JPEG", quality=85)
                return thumb_path.name

        if mime_type.startswith("video/"):
            cap = cv2.VideoCapture(str(path))
            success, frame = cap.read()
            cap.release()
            if success:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                img.thumbnail((400, 400))
                img.save(thumb_path, format="JPEG", quality=80)
                return thumb_path.name

        if mime_type.startswith("audio/"):
            placeholder = Image.new("RGB", (400, 400), color=(44, 62, 80))
            placeholder.save(thumb_path, format="JPEG", quality=80)
            return thumb_path.name
    except Exception:
        thumb_path.unlink(missing_ok=True)

    return None


def delete_media_file(filename: str) -> None:
    settings = get_settings()
    media_root = Path(settings.media_root)
    target = (media_root / filename).resolve()
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    if media_root not in target.parents and target != media_root:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        target.unlink()
    finally:
        thumb = target.with_suffix(target.suffix + ".thumb.jpg")
        thumb.unlink(missing_ok=True)
