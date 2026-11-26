from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from backend import config
from backend.database.db import audit, get_db
from backend.security import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
def login(body: LoginIn):
    user = auth.authenticate(body.username.strip(), body.password)
    token = auth.create_session(user["id"])
    with get_db() as db:
        audit(db, user["username"], "auth.login", "user", user["id"])
    return {"token": token, "user": {"username": user["username"], "display_name": user["display_name"],
                                      "role": user["role"]}}


@router.get("/me")
def me(user: dict = Depends(auth.current_user)):
    return user


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), user: dict = Depends(auth.current_user)):
    token = auth._token_from_header(authorization)
    if token:
        auth.destroy_session(token)
    return {"ok": True}


@router.get("/demo-logins")
def demo_logins():
    """Prototype convenience only: lists synthetic demo accounts. Disable with GOVASSIST_SHOW_DEMO_LOGINS=false."""
    if not config.SHOW_DEMO_LOGINS:
        return []
    return [{"username": u["username"], "password": u["password"], "role": u["role"]} for u in config.DEMO_USERS]
