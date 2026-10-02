"""Proteção CSRF por double-submit cookie (defesa em profundidade além do
SameSite=Lax do cookie de sessão).

O cookie `segportal_csrf` é legível por JavaScript (não HttpOnly); o frontend
reenvia o valor no cabeçalho `X-CSRF-Token` nas requisições de escrita. Uma
origem externa não consegue ler o cookie (SOP) nem forjar o cabeçalho, de modo
que requisições cross-site de escrita são rejeitadas.
"""

from __future__ import annotations

import hmac
import os
import secrets

from fastapi import HTTPException, Request, Response

CSRF_COOKIE = "segportal_csrf"
CSRF_HEADER = "x-csrf-token"
_MAX_AGE = 8 * 3600


def _cookie_secure() -> bool:
    raw = os.getenv("SEGPORTAL_COOKIE_SECURE", "1").strip().lower()
    return raw not in {"0", "false", "no"}


def issue_csrf(response: Response, request: Request | None = None) -> str:
    """Garante um token CSRF no response; reaproveita o existente, se houver."""
    token = request.cookies.get(CSRF_COOKIE) if request is not None else None
    if not token:
        token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        httponly=False,
        secure=_cookie_secure(),
        samesite="lax",
        max_age=_MAX_AGE,
        path="/",
    )
    return token


def require_csrf(request: Request) -> None:
    """Valida o double-submit: cookie e cabeçalho devem existir e coincidir."""
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Token CSRF inválido ou ausente")
