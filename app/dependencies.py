from fastapi import HTTPException, Request, status


def require_auth(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Authentication required",
            headers={"Location": "/auth-required"},
        )
    return user


def refresh_session_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        return {}
    return {
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "role": user.get("role"),
        "id": user.get("id"),
    }


def require_role(request: Request, allowed_roles: set[str]) -> dict:
    user = require_auth(request)
    role = user.get("role")
    if role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user


def require_uploader(request: Request) -> dict:
    return require_role(request, {"uploader", "admin"})


def require_admin(request: Request) -> dict:
    return require_role(request, {"admin"})
