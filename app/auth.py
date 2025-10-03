from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette import status
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth

from .config import get_settings
from .crud import ensure_user, get_user_by_email, init_admins
from .models import UserRole

router = APIRouter()
_oauth: OAuth | None = None
_google_client = None


def init_session(app: FastAPI) -> None:
    settings = get_settings()
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

    global _oauth, _google_client
    if _oauth is None:
        _oauth = OAuth()
        _google_client = _oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("user"))


@router.get("/auth/login")
async def login(request: Request) -> RedirectResponse:
    if not _oauth:
        raise HTTPException(status_code=500, detail="OAuth not initialized")
    redirect_uri = str(get_settings().oauth_redirect_url)
    return await _oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def auth_callback(request: Request, code: str, state: str | None = None):
    if not _oauth:
        raise HTTPException(status_code=500, detail="OAuth not initialized")

    settings = get_settings()

    try:
        token = await _oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        request.session.clear()
        request.session["unauthorized_email"] = None
        return RedirectResponse(url="/auth-required", status_code=status.HTTP_303_SEE_OTHER)
    user_info = token.get("userinfo")
    if not user_info:
        user_info = await _oauth.google.parse_id_token(request, token)

    if not user_info:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to retrieve user info")

    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email not provided")

    user = get_user_by_email(email)
    if not user:
        request.session.clear()
        request.session["unauthorized_email"] = email
        return RedirectResponse(url="/auth/unauthorized", status_code=status.HTTP_303_SEE_OTHER)

    user = ensure_user(email=email, name=user_info.get("name"), picture=user_info.get("picture"), create_if_missing=False)

    if not user or not user.active:
        request.session.clear()
        request.session["unauthorized_email"] = email
        return RedirectResponse(url="/auth/unauthorized", status_code=status.HTTP_303_SEE_OTHER)

    request.session.pop("oauth_state", None)
    request.session.pop("unauthorized_email", None)
    request.session["user"] = {
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "role": user.role.value if user.role else UserRole.viewer.value,
        "id": user.id,
    }
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/auth/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/")


@router.get("/auth/status")
async def auth_status(request: Request):
    user = request.session.get("user")
    if user:
        return JSONResponse(content={"authenticated": True, "user": user})
    return JSONResponse(content={"authenticated": False})
