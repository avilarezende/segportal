"""MFA TOTP (RFC 6238) para o SegPortal — segundo fator obrigatório quando há segredo."""

from __future__ import annotations

import hmac
import json
import os

import pyotp

# Segredos TOTP por usuário, em JSON via env:
#   SEGPORTAL_TOTP_SECRETS='{"admin": "JBSWY3DPEHPK3PXP", "fulano": "BASE32SECRET..."}'
# Os segredos devem ser provisionados via Secret (K8s/env), nunca em código.


def _totp_secrets() -> dict[str, str]:
    raw = os.getenv("SEGPORTAL_TOTP_SECRETS", "{}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    return {str(k).lower(): str(v).strip() for k, v in data.items() if str(v).strip()}


def totp_enabled_for(username: str) -> bool:
    return bool(_totp_secrets().get(username.strip().lower(), ""))


def totp_uri(accountname: str, issuer: str = "SegPortal") -> str:
    """Gera a URI otpauth:// para cadastro do app autenticador."""
    username = accountname.strip().lower()
    secret = _totp_secrets().get(username, "")
    if not secret:
        raise ValueError(f"MFA TOTP não configurado para {accountname}")
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(username: str, code: str) -> bool:
    """Valida o código TOTP do usuário com tolerância de ±1 intervalo."""
    username = username.strip().lower()
    secret = _totp_secrets().get(username, "")
    if not secret:
        # Sem segredo cadastrado, o fator não é obrigatório e a validação passa.
        return True
    code = (code or "").strip()
    if not code:
        return False
    totp = pyotp.TOTP(secret)
    # Tolerância de 1 janela para compensar dessincronização de relógio.
    return totp.verify(code, valid_window=1) or hmac.compare_digest(str(totp.now()), code)
