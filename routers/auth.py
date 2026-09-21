"""ログイン・初期管理者作成・職員ポータル認証。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from data.facility import get_facility_context
from services import auth as auth_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(tags=["認証"])


class AdminLoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class AdminSetupBody(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=50)


class StaffPortalLoginBody(BaseModel):
    staff_id: int
    pin: str = Field(min_length=4, max_length=8)


def _set_cookie(response: Response, name: str, token: str) -> None:
    response.set_cookie(
        key=name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=auth_service.SESSION_TTL_SECONDS,
        path="/",
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if auth_service.setup_needed():
        return RedirectResponse(url="/setup", status_code=303)
    if auth_service.current_admin(request):
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {**get_facility_context(), "next": next or "/", "error": None},
    )


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    if not auth_service.setup_needed():
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "auth/setup.html",
        {**get_facility_context(), "error": None},
    )


@router.post("/api/auth/setup")
def api_setup(data: AdminSetupBody, response: Response):
    if not auth_service.setup_needed():
        raise HTTPException(status_code=409, detail="管理者は既に作成済みです。")
    try:
        admin = auth_service.create_admin(data.username, data.password, data.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = auth_service.issue_session({**admin, "role": "admin"})
    _set_cookie(response, auth_service.AUTH_COOKIE, token)
    return {"ok": True, "admin": {"username": admin["username"], "display_name": admin["display_name"]}}


@router.post("/api/auth/login")
def api_login(data: AdminLoginBody, response: Response):
    admin = auth_service.authenticate_admin(data.username, data.password)
    if admin is None:
        raise HTTPException(status_code=401, detail="ユーザー名またはパスワードが違います。")
    token = auth_service.issue_session(admin)
    _set_cookie(response, auth_service.AUTH_COOKIE, token)
    return {"ok": True, "admin": {"username": admin["username"], "display_name": admin["display_name"]}}


@router.post("/api/auth/logout")
def api_logout(response: Response):
    response.delete_cookie(auth_service.AUTH_COOKIE, path="/")
    return {"ok": True}


@router.get("/api/auth/status")
def api_status(request: Request):
    admin = auth_service.current_admin(request)
    return {
        "setup_needed": auth_service.setup_needed(),
        "auth_enforced": auth_service.auth_enforced(),
        "admin": (
            {"username": admin.get("username"), "name": admin.get("name")}
            if admin
            else None
        ),
    }


@router.post("/portal/api/login")
def portal_login(data: StaffPortalLoginBody, response: Response):
    staff = auth_service.authenticate_staff(data.staff_id, data.pin)
    if staff is None:
        raise HTTPException(
            status_code=401,
            detail="PINが違うか、この職員のポータルPINが未設定です。管理者に確認してください。",
        )
    token = auth_service.issue_session(staff)
    _set_cookie(response, auth_service.STAFF_COOKIE, token)
    return {"ok": True, "staff": {"id": staff["id"], "name": staff["name"]}}


@router.post("/portal/api/logout")
def portal_logout(response: Response):
    response.delete_cookie(auth_service.STAFF_COOKIE, path="/")
    return {"ok": True}


@router.get("/portal/api/me")
def portal_me(request: Request):
    staff = auth_service.current_staff(request)
    if staff is None:
        raise HTTPException(status_code=401, detail="職員ログインが必要です。")
    return {"id": staff["id"], "name": staff.get("name")}
