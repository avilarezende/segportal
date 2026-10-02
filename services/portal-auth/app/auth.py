"""Autenticação do portal (sessão cookie + LDAP real + usuários locais via env)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import HTTPException, Request, Response

from .config import ldap_config, settings

# Usuários locais agora vêm de variáveis de ambiente — nada de senha em claro
# no repositório. Formato esperado (uma entrada separada por ";"):
#   SEGPORTAL_LOCAL_USERS="admin:Admin SegPortal:admin:admin@aqne.jus.br;"
#                          "usuario:Usuário:user:usuario@aqne.jus.br"
# As senhas vêm em SEGPORTAL_LOCAL_PASSWORDS no mesmo formato indexado:
#   SEGPORTAL_LOCAL_PASSWORDS="senhaAdmin;senhaUsuario"


def _local_users() -> dict[str, dict[str, Any]]:
    raw_users = os.getenv("SEGPORTAL_LOCAL_USERS", "")
    raw_pws = os.getenv("SEGPORTAL_LOCAL_PASSWORDS", "")
    if not raw_users or not raw_pws:
        return {}

    users: dict[str, dict[str, Any]] = {}
    u_lines = [u for u in raw_users.split(";") if u]
    p_lines = [p for p in raw_pws.split(";") if p]
    if len(u_lines) != len(p_lines):
        return {}

    for entry, password in zip(u_lines, p_lines, strict=False):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) != 4:
            continue
        username, display_name, role, email = parts
        users[username.lower()] = {
            "password": password,
            "display_name": display_name,
            "role": role,
            "email": email,
        }
    return users


@dataclass
class PortalUser:
    username: str
    display_name: str
    role: str
    email: str
    auth_source: str  # local | ldap


def _sign(payload: str) -> str:
    return hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_session_token(user: PortalUser) -> str:
    body = json.dumps(
        {**asdict(user), "exp": int(time.time()) + 8 * 3600},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"{body}.{_sign(body)}"


def parse_session_token(token: str | None) -> PortalUser | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(body), sig):
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if int(data.get("exp", 0)) < int(time.time()):
        return None
    return PortalUser(
        username=data["username"],
        display_name=data["display_name"],
        role=data["role"],
        email=data["email"],
        auth_source=data.get("auth_source", "local"),
    )


def _ldap_available() -> bool:
    try:
        import ldap3  # noqa: F401
    except ImportError:
        return False
    cfg = ldap_config().get("ldap", {})
    return bool(cfg.get("enabled")) or settings.ldap_enabled


def _authenticate_ldap(username: str, password: str) -> PortalUser:
    """Autentica contra o AD via bind LDAP real (ldap3).

    Falha com 401 (fail-closed) se o bind falhar — nunca cai para usuário
    local silenciosamente quando LDAP está habilitado.
    """
    import ldap3
    from ldap3.utils.conv import escape_filter_chars
    from ldap3.utils.dn import escape_rdn

    cfg = ldap_config().get("ldap", {})
    hostname = cfg.get("hostname") or os.getenv("LDAP_HOSTNAME", "")
    # Criptografia do canal: ssl/ldaps → TLS implícito; starttls → TLS após open.
    encryption = (
        cfg.get("encryption_method") or os.getenv("LDAP_ENCRYPTION_METHOD", "")
    ).strip().lower()
    use_ssl = encryption in {"ssl", "ldaps"}
    default_port = 636 if use_ssl else 389
    port = int(cfg.get("port") or os.getenv("LDAP_PORT", str(default_port)))
    if port == 636:
        use_ssl = True
    user_base = cfg.get("user_base_dn") or ""
    username_attr = cfg.get("username_attribute", "sAMAccountName")
    domain = cfg.get("domain", "")
    role_groups = cfg.get("role_groups", {}) or {}

    if not hostname or not user_base:
        raise HTTPException(status_code=500, detail="LDAP não configurado corretamente")

    # Senha vazia é rejeitada: o AD aceita "unauthenticated bind" (bind com senha
    # vazia retorna sucesso sem autenticar), o que permitiria login sem senha.
    if not password:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

    # Escapa a entrada do usuário para evitar LDAP injection no DN e no filtro.
    user_dn = f"{username_attr}={escape_rdn(username)},{user_base}"
    safe_filter_user = escape_filter_chars(username)
    server = ldap3.Server(hostname, port=port, use_ssl=use_ssl, get_info=ldap3.NONE)
    conn = ldap3.Connection(
        server,
        user=user_dn,
        password=password,
        raise_exceptions=True,
        auto_bind=False,
    )
    try:
        if encryption == "starttls" and not use_ssl:
            conn.open()
            conn.start_tls()
        bound = conn.bind()
        if not bound:
            raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

        # Busca os grupos do usuário para mapear papel
        role = "user"
        try:
            conn.search(
                search_base=user_base,
                search_filter=f"(&(objectClass=user)({username_attr}={safe_filter_user}))",
                attributes=[username_attr, "memberOf"],
                size_limit=1,
            )
            if conn.entries:
                member_of = conn.entries[0].memberOf or []
                group_values = [str(m).lower() for m in member_of]
                admin_group = str(role_groups.get("admin", "")).lower()
                if admin_group and any(admin_group in g for g in group_values):
                    role = "admin"
        except Exception:
            role = "user"  # sem groups mapeados mantém papél mínimo

        return PortalUser(
            username=username.lower(),
            display_name=username,
            role=role,
            email=f"{username}@{domain}".lower() if domain else "",
            auth_source="ldap",
        )
    except HTTPException:
        raise
    except Exception as exc:
        msg = (
            f"Falha na autenticação LDAP: {exc}"
            if os.getenv("SEGPORTAL_DEBUG")
            else "Falha na autenticação LDAP"
        )
        raise HTTPException(status_code=401, detail=msg) from exc
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def authenticate(username: str, password: str, prefer_ldap: bool = False) -> PortalUser:
    user = username.strip().lower()

    # Se LDAP está habilitado (config ou env), o fluxo é LDAP — sem fallback local.
    if prefer_ldap or settings.ldap_enabled or _ldap_available():
        return _authenticate_ldap(user, password)

    # Modo local: usuários provisionados via env (nada de senha em claro no código).
    local = _local_users()
    entry = local.get(user)
    if not entry or not hmac.compare_digest(entry["password"], password):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

    return PortalUser(
        username=user,
        display_name=entry["display_name"],
        role=entry["role"],
        email=entry["email"],
        auth_source="local",
    )


def current_user(request: Request) -> PortalUser:
    user = parse_session_token(request.cookies.get("segportal_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


def set_session_cookie(response: Response, user: PortalUser) -> None:
    # secure=True por padrão; em desenvolvimento HTTP local pode ser desligado
    # explicitamente com SEGPORTAL_COOKIE_SECURE=0.
    secure_raw = os.getenv("SEGPORTAL_COOKIE_SECURE", "1").strip().lower()
    cookie_secure = secure_raw not in {"0", "false", "no"}
    response.set_cookie(
        key="segportal_session",
        value=create_session_token(user),
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=8 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie("segportal_session", path="/")
