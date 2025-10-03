from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import init_session, router as auth_router
from .config import get_settings
from .crud import add_or_activate_user, create_media, delete_media, ensure_user, init_admins, list_media, list_users, set_user_active, update_user_role
from .dependencies import require_admin, require_auth, require_uploader
from .media_service import delete_media_file, save_media_file
from .models import MediaType, SQLModel, UserRole
from .schemas import MediaItem
from .database import engine, ensure_media_schema

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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, session_user=Depends(require_auth)):
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

    media_records = list_media()
    media_items = []
    for record in media_records:
        media_items.append(
            MediaItem(
                id=record.id,
                filename=record.filename,
                url=record.url,
                media_type=record.mime_type,
                thumbnail=record.thumbnail_url,
                title=record.title,
                description=record.description,
                tags=record.tags,
                original_filename=record.original_filename,
                uploaded_at=record.created_at.isoformat() if getattr(record, "created_at", None) else None,
            ).dict()
        )
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user_payload,
            "media_items": media_items,
            "app_name": settings.app_name,
            "title": "Library",
            "subtitle": "Upload, view, and play your media",
            "can_upload": db_user.role in {UserRole.uploader, UserRole.admin},
            "is_admin": db_user.role == UserRole.admin,
        },
    )


@app.post("/upload")
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(None),
    description: str = Form(None),
    tags: str = Form(""),
    user=Depends(require_uploader),
):
    _ = user
    media_item = save_media_file(file, title=title)
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
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
async def delete_media_item(filename: str, user=Depends(require_uploader)):
    _ = user
    delete_media_file(filename)
    delete_media(filename)
    return {"status": "ok"}


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