"""API FastAPI do portal SegPortal."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    authenticate,
    clear_session_cookie,
    current_user,
    set_session_cookie,
)
from .cloud_drives import mount_demo, start_oauth, unmount, user_cloud_state
from .config import settings
from .files import delete, list_dir, mkdir, open_file_path, rename, upload_file
from .ldap_shares import ensure_demo_tree, list_user_shares
from .mfa import totp_enabled_for, verify_totp
from .rate_limit import API_WRITE_LIMIT, LOGIN_LIMIT, limiter

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_demo_tree()
    yield


app = FastAPI(title="SegPortal AQNE", version="1.2.0", lifespan=lifespan)
app.state.limiter = limiter
from slowapi.errors import RateLimitExceeded  # noqa: E402


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    headers = {"Retry-After": str(int(exc.retry_after))} if exc.retry_after else None
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas requisições. Tente novamente mais tarde."},
        headers=headers,
    )

app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")
app.mount("/browser", StaticFiles(directory=str(STATIC_DIR / "browser")), name="browser")

@app.get("/", response_class=HTMLResponse)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "ldap_enabled": settings.ldap_enabled,
    }


@app.post("/api/login")
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request) -> JSONResponse:
    body = await request.json()
    user = authenticate(
        str(body.get("username", "")),
        str(body.get("password", "")),
        prefer_ldap=bool(body.get("use_active_directory", False)),
    )

    totp_code = str(body.get("totp_code", "") or "").strip()
    if totp_enabled_for(user.username):
        if not verify_totp(user.username, totp_code):
            return JSONResponse(
                {
                    "username": user.username,
                    "mfa_required": True,
                    "error": "Código de verificação (2FA) inválido ou ausente",
                },
                status_code=401,
            )

    payload = {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "email": user.email,
        "auth_source": user.auth_source,
        "ldap_enabled": settings.ldap_enabled,
    }
    response = JSONResponse(payload)
    set_session_cookie(response, user)
    return response


@app.post("/api/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response


@app.get("/api/me")
def me(request: Request) -> dict:
    user = current_user(request)
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "email": user.email,
        "auth_source": user.auth_source,
        "ldap_enabled": settings.ldap_enabled,
    }


@app.get("/api/dashboard")
def dashboard(request: Request) -> dict:
    user = current_user(request)
    return {
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "auth_source": user.auth_source,
        },
        "shares": list_user_shares(user),
        "cloud_drives": user_cloud_state(user),
        "ldap_enabled": settings.ldap_enabled or user.auth_source == "ldap",
        "features": {
            "embedded_browser": True,
            "computers": True,
            "reminders": True,
            "calendar": True,
        },
    }


@app.get("/api/files/{share_id}")
def api_list(share_id: str, request: Request, path: str = "") -> dict:
    return list_dir(current_user(request), share_id, path)


@app.post("/api/files/{share_id}/upload", response_model=None)
async def api_upload(
    share_id: str,
    request: Request,
    path: str = Form(""),
    file: UploadFile = File(...),
) -> dict:
    return await upload_file(current_user(request), share_id, path, file)


@app.post("/api/files/{share_id}/mkdir")
@limiter.limit(API_WRITE_LIMIT)
async def api_mkdir(share_id: str, request: Request) -> dict:
    body = await request.json()
    path = body.get("path", "")
    name = body.get("name", "Nova pasta")
    return mkdir(current_user(request), share_id, path, name)


@app.post("/api/files/{share_id}/rename")
@limiter.limit(API_WRITE_LIMIT)
async def api_rename(share_id: str, request: Request) -> dict:
    body = await request.json()
    return rename(current_user(request), share_id, body["path"], body["new_name"])


@app.delete("/api/files/{share_id}")
@limiter.limit(API_WRITE_LIMIT)
def api_delete(share_id: str, request: Request, path: str) -> dict:
    return delete(current_user(request), share_id, path)


@app.get("/api/files/{share_id}/download")
def api_download(share_id: str, request: Request, path: str) -> FileResponse:
    target = open_file_path(current_user(request), share_id, path)
    return FileResponse(path=target, filename=target.name)


@app.get("/api/cloud")
def api_cloud(request: Request) -> dict:
    return {"drives": user_cloud_state(current_user(request))}


@app.post("/api/cloud/{provider}/mount")
@limiter.limit(API_WRITE_LIMIT)
async def api_cloud_mount(provider: str, request: Request) -> dict:
    user = current_user(request)
    try:
        oauth = start_oauth(user, provider, str(request.base_url).rstrip("/"))
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    if oauth["mode"] == "demo":
        return {"mode": "demo", "message": oauth["message"], "drives": mount_demo(user, provider)}
    return oauth


@app.post("/api/cloud/{provider}/unmount")
def api_cloud_unmount(provider: str, request: Request) -> dict:
    return {"drives": unmount(current_user(request), provider)}


@app.get("/api/cloud/{provider}/callback")
def api_cloud_callback(provider: str) -> RedirectResponse:
    _ = provider
    return RedirectResponse("/?cloud=connected", status_code=302)
