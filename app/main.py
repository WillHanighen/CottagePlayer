from pathlib import Path
from typing import Any, Iterable, Sequence

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import init_session, router as auth_router
from .config import get_settings
from .crud import (
    add_media_to_playlist,
    add_or_activate_user,
    create_media,
    create_playlist,
    delete_media,
    delete_playlist,
    ensure_user,
    get_media_by_filename,
    get_playlist,
    init_admins,
    list_media,
    list_playlists,
    list_users,
    remove_media_from_playlist,
    set_playlist_items,
    set_user_active,
    update_media,
    update_playlist,
    update_user_role,
)
from .dependencies import require_admin, require_auth, require_uploader
from .media_service import save_media_file, delete_media_file
from .models import MediaType, UserRole
from .schemas import MediaItem
from .database import engine, ensure_media_schema
from sqlmodel import SQLModel

from datetime import datetime

settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
async def on_startup():
    SQLModel.metadata.create_all(engine)
    ensure_media_schema()
    # ensure initial admins exist
    init_admins(settings.initial_admin_emails)


init_session(app)
app.include_router(auth_router)


static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
# Media endpoint is protected via route below; do not mount publicly

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    if exc.status_code in (status.HTTP_307_TEMPORARY_REDIRECT, status.HTTP_401_UNAUTHORIZED) and exc.headers and exc.headers.get("Location"):
        return RedirectResponse(url=exc.headers["Location"], status_code=exc.status_code)
    raise exc


def _build_media_items(records: Iterable[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        items.append(
            MediaItem(
                id=record.id,
                filename=record.filename,
                url=record.url,
                media_type=record.mime_type,
                thumbnail=record.thumbnail_url,
                title=record.title,
                description=record.description,
                tags=getattr(record, "tags", []) or [],
                playlists=getattr(record, "playlists", []) or [],
                original_filename=record.original_filename,
                uploaded_at=record.created_at.isoformat() if getattr(record, "created_at", None) else None,
                owner_id=getattr(record, "owner_id", None),
            ).dict()
        )
    return items


def _filter_media_records(
    records: list[Any],
    *,
    types: list[str] | None = None,
    tags: list[str] | None = None,
    playlists: list[str] | None = None,
) -> list[Any]:
    types = [t.lower() for t in types or []]
    tags = [t.lower() for t in tags or []]
    playlists = [p.lower() for p in playlists or []]

    def _matches(record: Any) -> bool:
        if types and not any(str(record.mime_type or '').lower().startswith(t) for t in types):
            return False
        record_tags = [str(tag).lower() for tag in getattr(record, 'tags', []) or []]
        record_lists = [str(pl).lower() for pl in getattr(record, 'playlists', []) or []]
        if tags and not any(tag in record_tags for tag in tags):
            return False
        if playlists and not any(pl in record_lists for pl in playlists):
            return False
        return True

    return [record for record in records if _matches(record)]


def _render_library(
    request: Request,
    session_user: dict,
    *,
    title: str,
    subtitle: str,
    initial_filters: dict[str, Any] | None = None,
    records_override: list[Any] | None = None,
):
    db_user = ensure_user(
        email=session_user["email"],
        name=session_user.get("name"),
        picture=session_user.get("picture"),
        create_if_missing=False,
    )

    if not db_user:
        request.session.pop("user", None)
        request.session["unauthorized_email"] = session_user["email"]
        return RedirectResponse(url="/auth/unauthorized", status_code=status.HTTP_303_SEE_OTHER)

    user_payload = {
        "email": db_user.email,
        "name": db_user.name,
        "picture": db_user.picture,
        "role": db_user.role.value,
        "id": db_user.id,
    }

    request.session["user"] = user_payload

    records = records_override if records_override is not None else list_media()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user_payload,
            "media_items": _build_media_items(records),
            "app_name": settings.app_name,
            "title": title,
            "subtitle": subtitle,
            "can_upload": db_user.role in {UserRole.uploader, UserRole.admin},
            "is_admin": db_user.role == UserRole.admin,
            "role": db_user.role.value,
            "user_id": db_user.id,
            "tag_options": settings.tag_options,
            "playlist_options": settings.playlist_options,
            "initial_filters": initial_filters or {},
            "category": initial_filters.get("category"),
        },
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, session_user=Depends(require_auth)):
    return _render_library(
        request,
        session_user,
        title="Library",
        subtitle="Upload, view, and play your media",
        initial_filters={},
    )


def _match_option(options: list[str], *candidates: str) -> list[str]:
    lowered = {opt.lower(): opt for opt in options}
    matches: list[str] = []
    for candidate in candidates:
        value = lowered.get(candidate.lower())
        if value:
            matches.append(value)
    return matches


@app.get("/library/music", response_class=HTMLResponse)
async def library_music(request: Request, session_user=Depends(require_auth)):
    initial_filters: dict[str, Any] = {"types": ["audio"], "category": "music"}
    records = list_media()
    playlists = _match_option(settings.playlist_options, "Music", "Music & Playlists")
    tags = _match_option(settings.tag_options, "Music", "Audio")
    if playlists:
        initial_filters["playlists"] = playlists[:1]
        records = _filter_media_records(records, types=["audio"], playlists=playlists)
    elif tags:
        initial_filters["tags"] = tags[:1]
        records = _filter_media_records(records, types=["audio"], tags=tags)
    else:
        records = _filter_media_records(records, types=["audio"])
    return _render_library(
        request,
        session_user,
        title="Music & Playlists",
        subtitle="Stream audio and curated playlists",
        initial_filters=initial_filters,
        records_override=records,
    )


@app.get("/library/movies", response_class=HTMLResponse)
async def library_movies(request: Request, session_user=Depends(require_auth)):
    initial_filters: dict[str, Any] = {"types": ["video"], "category": "movies"}
    records = list_media()
    playlists = _match_option(settings.playlist_options, "Movies", "Films")
    tags = _match_option(settings.tag_options, "Movie", "Film")
    if playlists:
        initial_filters["playlists"] = playlists[:1]
        records = _filter_media_records(records, types=["video"], playlists=playlists)
    elif tags:
        initial_filters["tags"] = tags[:1]
        records = _filter_media_records(records, types=["video"], tags=tags)
    else:
        records = _filter_media_records(records, types=["video"])
    return _render_library(
        request,
        session_user,
        title="Movies",
        subtitle="Feature-length videos and films",
        initial_filters=initial_filters,
        records_override=records,
    )


@app.get("/library/tv", response_class=HTMLResponse)
async def library_tv(request: Request, session_user=Depends(require_auth)):
    initial_filters: dict[str, Any] = {"types": ["video"], "category": "tv"}
    records = list_media()
    playlists = _match_option(settings.playlist_options, "TV Shows", "Series")
    tags = _match_option(settings.tag_options, "TV", "Series")
    if playlists:
        initial_filters["playlists"] = playlists[:1]
        records = _filter_media_records(records, types=["video"], playlists=playlists)
    elif tags:
        initial_filters["tags"] = tags[:1]
        records = _filter_media_records(records, types=["video"], tags=tags)
    else:
        records = _filter_media_records(records, types=["video"])
    return _render_library(
        request,
        session_user,
        title="TV Shows",
        subtitle="Serialized video content",
        initial_filters=initial_filters,
        records_override=records,
    )


@app.get("/library/photos", response_class=HTMLResponse)
async def library_photos(request: Request, session_user=Depends(require_auth)):
    initial_filters: dict[str, Any] = {"types": ["image"], "category": "photos"}
    records = list_media()
    playlists = _match_option(settings.playlist_options, "Photos", "Photography", "Images")
    tags = _match_option(settings.tag_options, "Photos", "Images", "GIF")
    if playlists:
        initial_filters["playlists"] = playlists[:1]
        records = _filter_media_records(records, types=["image"], playlists=playlists)
    elif tags:
        initial_filters["tags"] = tags[:1]
        records = _filter_media_records(records, types=["image"], tags=tags)
    else:
        records = _filter_media_records(records, types=["image"])
    return _render_library(
        request,
        session_user,
        title="Photos & GIFs",
        subtitle="Image collections and galleries",
        initial_filters=initial_filters,
        records_override=records,
    )


# Playlist API


@app.get("/playlists", response_model=list[dict[str, Any]])
async def list_playlists_endpoint(user=Depends(require_auth)):
    del user
    playlists = list_playlists()
    return [
        {
            "id": playlist.id,
            "name": playlist.name,
            "description": playlist.description,
            "owner_id": playlist.owner_id,
            "created_at": playlist.created_at.isoformat() if playlist.created_at else None,
        }
        for playlist in playlists
    ]


@app.post("/playlists", response_model=dict)
async def create_playlist_endpoint(
    name: str = Form(...),
    description: str | None = Form(None),
    user=Depends(require_auth),
):
    playlist = create_playlist(name=name, description=description, owner_id=user.get("id"))
    return {
        "id": playlist.id,
        "name": playlist.name,
        "description": playlist.description,
        "owner_id": playlist.owner_id,
        "created_at": playlist.created_at.isoformat() if playlist.created_at else None,
    }


@app.put("/playlists/{playlist_id}", response_model=dict)
async def update_playlist_endpoint(
    playlist_id: int,
    name: str = Form(None),
    description: str | None = Form(None),
    user=Depends(require_auth),
):
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    if playlist.owner_id and playlist.owner_id != user.get("id") and user.get("role") != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    updated = update_playlist(playlist_id, name=name, description=description)
    return {
        "id": updated.id,
        "name": updated.name,
        "description": updated.description,
        "owner_id": updated.owner_id,
        "created_at": updated.created_at.isoformat() if updated.created_at else None,
    }


@app.delete("/playlists/{playlist_id}", response_model=dict)
async def delete_playlist_endpoint(playlist_id: int, user=Depends(require_auth)):
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    if playlist.owner_id and playlist.owner_id != user.get("id") and user.get("role") != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    delete_playlist(playlist_id)
    return {"status": "ok"}


@app.post("/playlists/{playlist_id}/items", response_model=dict)
async def add_playlist_item_endpoint(
    playlist_id: int,
    media_id: int = Form(...),
    position: int | None = Form(None),
    user=Depends(require_auth),
):
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    if playlist.owner_id and playlist.owner_id != user.get("id") and user.get("role") != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        item = add_media_to_playlist(playlist_id, media_id, position)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "playlist_id": item.playlist_id,
        "media_id": item.media_id,
        "position": item.position,
    }


@app.delete("/playlists/{playlist_id}/items/{media_id}", response_model=dict)
async def remove_playlist_item_endpoint(playlist_id: int, media_id: int, user=Depends(require_auth)):
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    if playlist.owner_id and playlist.owner_id != user.get("id") and user.get("role") != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        remove_media_from_playlist(playlist_id, media_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"status": "ok"}


@app.post("/upload")
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(None),
    description: str = Form(None),
    tags: str = Form(""),
    playlists: str = Form(""),
    user=Depends(require_uploader),
):
    _ = user
    media_item = save_media_file(file, title=title)
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    playlists_list = [item.strip() for item in playlists.split(",") if item.strip()]
    allowed_mime = media_item.media_type
    created = create_media(
        filename=media_item.filename,
        original_filename=media_item.original_filename,
        media_type=MediaType.video if allowed_mime.startswith("video/") else MediaType.image if allowed_mime.startswith("image/") else MediaType.audio,
        mime_type=allowed_mime,
        url=media_item.url,
        thumbnail_url=media_item.thumbnail,
        title=title,
        description=description,
        tags=tags_list,
        playlists=playlists_list,
        owner_id=user.get("id"),
    )
    media_dict = MediaItem(
        id=created.id,
        filename=created.filename,
        url=created.url,
        media_type=created.mime_type,
        thumbnail=created.thumbnail_url,
        title=created.title,
        description=created.description,
        tags=created.tags,
        playlists=getattr(created, "playlists", []),
        original_filename=created.original_filename,
        uploaded_at=created.created_at.isoformat() if created.created_at else None,
    ).dict()
    return {"status": "ok", "media_item": media_dict}


@app.get("/media/{path:path}")
async def serve_media(path: str, user=Depends(require_auth)):
    del user  # access enforced via dependency
    root = Path(settings.media_root).resolve()
    requested = (root / path).resolve()

    if not requested.exists() or not requested.is_file() or root not in requested.parents and requested != root:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    return FileResponse(requested)


@app.delete("/media/{filename}")
async def delete_media_item(filename: str, user=Depends(require_auth)):
    role = user.get("role")
    user_id = user.get("id")

    if role not in {UserRole.uploader.value, UserRole.admin.value}:
        # allow owners (even viewers) to remove their own uploads
        record = get_media_by_filename(filename)
        if not record or record.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    else:
        record = get_media_by_filename(filename)

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    delete_media_file(filename)
    delete_media(filename)
    return {"status": "ok"}


@app.put("/media/{filename}")
async def update_media_item(
    filename: str,
    title: str = Form(None),
    description: str = Form(None),
    tags: str = Form(""),
    playlists: str = Form(""),
    user=Depends(require_auth),
):
    role = user.get("role")
    user_id = user.get("id")

    record = get_media_by_filename(filename)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    if role not in {UserRole.uploader.value, UserRole.admin.value} and record.owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    tags_list = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    playlists_list = [item.strip() for item in (playlists or "").split(",") if item.strip()]
    updated = update_media(filename, title=title, description=description, tags=tags_list, playlists=playlists_list)

    return {
        "status": "ok",
        "media_item": MediaItem(
            id=updated.id,
            filename=updated.filename,
            url=updated.url,
            media_type=updated.mime_type,
            thumbnail=updated.thumbnail_url,
            title=updated.title,
            description=updated.description,
            tags=updated.tags,
            original_filename=updated.original_filename,
            uploaded_at=updated.created_at.isoformat() if getattr(updated, "created_at", None) else None,
        ).dict(),
    }


@app.get("/auth-required", response_class=HTMLResponse)
async def auth_required(request: Request):
    return templates.TemplateResponse(
        "auth_required.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "title": "Authentication Required",
            "user": request.session.get("user"),
        },
    )


@app.get("/auth/unauthorized", response_class=HTMLResponse)
async def auth_unauthorized(request: Request):
    email = request.session.pop("unauthorized_email", None)
    return templates.TemplateResponse(
        "auth_unauthorized.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "title": "Access Denied",
            "user": request.session.get("user"),
            "email": email,
        },
    )


@app.get("/admin/users", response_class=HTMLResponse)
async def manage_users(request: Request, user=Depends(require_admin)):
    users = list_users()
    return templates.TemplateResponse(
        "admin_users.html",
        {
            "request": request,
            "users": users,
            "user": user,
            "app_name": settings.app_name,
            "roles": [role.value for role in UserRole],
            "title": "User Management",
            "subtitle": "Authorize accounts and manage roles",
        },
    )


@app.post("/admin/users/{user_id}/role")
async def change_user_role(user_id: int, role: str = Form(...), _: dict = Depends(require_admin)):
    try:
        update_user_role(user_id, UserRole(role))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/active")
async def change_user_active(user_id: int, active: str = Form(...), _: dict = Depends(require_admin)):
    set_user_active(user_id, active.lower() == "true")
    return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users")
async def admin_add_user(
    email: str = Form(...),
    name: str | None = Form(None),
    role: str = Form(UserRole.viewer.value),
    _: dict = Depends(require_admin),
):
    if not email.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")
    try:
        add_or_activate_user(email=email, name=name, role=UserRole(role))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RedirectResponse(url="/admin/users", status_code=303)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0"
    }
