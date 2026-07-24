import hmac

from fastapi import HTTPException, Request

from .config import env_settings


def check_password(password: str) -> bool:
    return hmac.compare_digest(password.encode("utf-8"), env_settings().admin_password.encode("utf-8"))


def require_auth(request: Request) -> None:
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Authentication required")
