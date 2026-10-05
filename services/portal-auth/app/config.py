"""Configuração do portal-auth SegPortal."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
SHARES_YAML = Path(os.getenv("SEGPORTAL_SHARES_CONFIG", ROOT / "config" / "files" / "shares.yaml"))
LDAP_YAML = ROOT / "config" / "ldap" / "ldap-settings.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache
def shares_config() -> dict[str, Any]:
    return _load_yaml(SHARES_YAML)


@lru_cache
def ldap_config() -> dict[str, Any]:
    return _load_yaml(LDAP_YAML)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.env = os.getenv("SEGPORTAL_ENV", "development")
        if self.env not in {"development", "staging", "production"}:
            raise RuntimeError("SEGPORTAL_ENV inválido")
        demo = shares_config().get("shares", {}).get("demo", {})
        ui = shares_config().get("ui", {})
        ldap_on = bool(ldap_config().get("ldap", {}).get("enabled", False))
        demo_root = demo.get("root", str(Path.home() / ".local" / "share" / "segportal" / "shares"))

        # Chave de assinatura da sessão: obrigatória e sem default conhecido.
        secret = os.getenv("PORTAL_SESSION_SECRET", "")
        if not secret or secret in ("segportal-dev-secret-change-me", "change-me", "change_me"):
            raise RuntimeError(
                "PORTAL_SESSION_SECRET não configurada (ou com valor padrão). "
                "Defina uma chave forte via variável de ambiente antes de iniciar o portal."
            )
        self.session_secret = secret

        if self.env in {"staging", "production"}:
            if len(secret) < 32 or any(
                s in secret.lower() for s in ("change-me", "test-", "example")
            ):
                raise RuntimeError("PORTAL_SESSION_SECRET forte é obrigatória em produção")
            if not env_bool("SEGPORTAL_COOKIE_SECURE", True):
                raise RuntimeError("Produção requer cookies Secure (HTTPS)")
            if not env_bool("SEGPORTAL_RATE_LIMIT_ENABLED", True):
                raise RuntimeError("Produção requer rate limiting")
            if demo.get("enabled", True):
                raise RuntimeError("Produção requer shares de demonstração desativados")

        self.ldap_enabled = env_bool("LDAP_ENABLED", ldap_on)
        # URL interna de sessões (nunca exposta na UI)
        self.sessions_internal_url = os.getenv("SESSIONS_INTERNAL_URL", "")
        self.demo_shares_root = Path(os.getenv("DEMO_SHARES_ROOT", demo_root))
        max_upload = str(ui.get("max_upload_mb", 100))
        self.max_upload_mb = int(os.getenv("PORTAL_MAX_UPLOAD_MB", max_upload))
        self.portal_port = int(os.getenv("PORTAL_PORT", "8090"))


settings = Settings()
