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
from .catalog import catalogo_para_usuario, item_autorizado
from .cloud_drives import mount_demo, start_oauth, unmount, user_cloud_state
from .config import settings
from .csrf import issue_csrf, require_csrf
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
    # retry_after não existe em todas as versões do slowapi; usar getattr evita
    # que o handler quebre (500) e mascare a proteção anti-força-bruta (429).
    retry_after = getattr(exc, "retry_after", None)
    headers = {"Retry-After": str(int(retry_after))} if retry_after else None
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas requisições. Tente novamente mais tarde."},
        headers=headers,
    )

# Content-Security-Policy: bloqueia scripts inline (defesa XSS), restringe
# origens e impede clickjacking. 'unsafe-inline' fica só em style-src (fontes
# Google + estilos do tema); frame-src https: permite o navegador incorporado.
_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data: blob:; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "connect-src 'self'; "
    "frame-src 'self' https:; "
    "child-src 'self' https:"
)

_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    # HSTS apenas sob HTTPS (atrás do ingress/TLS) para não afetar dev em HTTP.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if proto == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")
app.mount("/browser", StaticFiles(directory=str(STATIC_DIR / "browser")), name="browser")

@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> FileResponse:
    response = FileResponse(STATIC_DIR / "index.html")
    issue_csrf(response, request)
    return response


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
    issue_csrf(response, request)
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
        "computers": catalogo_para_usuario(user.role),
        "ldap_enabled": settings.ldap_enabled or user.auth_source == "ldap",
        "features": {
            "embedded_browser": True,
            "computers": True,
            "reminders": True,
            "calendar": True,
        },
    }


@app.get("/api/computers/{item_id}/authorize")
def authorize_computer(item_id: str, request: Request) -> JSONResponse:
    """Autoriza a abertura de um item do catálogo — decisão no servidor.

    Usuário sem o papel necessário recebe 403, mesmo chamando direto.
    """
    user = current_user(request)
    item = item_autorizado(user.role, item_id)
    if not item:
        return JSONResponse(
            {"detail": "Você não tem permissão para abrir este computador/aplicação"},
            status_code=403,
        )
    return JSONResponse({"ok": True, "item": item})


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
    require_csrf(request)
    return await upload_file(current_user(request), share_id, path, file)


@app.post("/api/files/{share_id}/mkdir")
@limiter.limit(API_WRITE_LIMIT)
async def api_mkdir(share_id: str, request: Request) -> dict:
    require_csrf(request)
    body = await request.json()
    path = body.get("path", "")
    name = body.get("name", "Nova pasta")
    return mkdir(current_user(request), share_id, path, name)


@app.post("/api/files/{share_id}/rename")
@limiter.limit(API_WRITE_LIMIT)
async def api_rename(share_id: str, request: Request) -> dict:
    require_csrf(request)
    body = await request.json()
    return rename(current_user(request), share_id, body["path"], body["new_name"])


@app.delete("/api/files/{share_id}")
@limiter.limit(API_WRITE_LIMIT)
def api_delete(share_id: str, request: Request, path: str) -> dict:
    require_csrf(request)
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
    require_csrf(request)
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
    require_csrf(request)
    return {"drives": unmount(current_user(request), provider)}


@app.get("/api/cloud/{provider}/callback")
def api_cloud_callback(provider: str) -> RedirectResponse:
    _ = provider
    return RedirectResponse("/?cloud=connected", status_code=302)
