"""Testes do MFA TOTP do portal SegPortal."""

from __future__ import annotations

import sys
from pathlib import Path

import pyotp
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "portal-auth"))

# Segredo TOTP fixo para os testes (base32 válido).
_TEST_SECRET = "JBSWY3DPEHPK3PXP"

from app.mfa import totp_enabled_for, totp_uri, verify_totp  # noqa: E402


@pytest.fixture(autouse=True)
def _totp_secret_env(monkeypatch):
    """Define SEGPORTAL_TOTP_SECRETS só para os testes deste módulo."""
    monkeypatch.setenv("SEGPORTAL_TOTP_SECRETS", '{"admin": "' + _TEST_SECRET + '"}')
    yield
    # Monkeypatch restaura o valor original ao final de cada teste.


def test_totp_enabled_for():
    assert totp_enabled_for("admin")
    assert not totp_enabled_for("usuario_inexistente")


def test_totp_verify_correct_code():
    totp = pyotp.TOTP(_TEST_SECRET)
    assert verify_totp("admin", totp.now())


def test_totp_verify_wrong_code():
    assert not verify_totp("admin", "000000")


def test_totp_verify_missing_code():
    # Usuário sem segredo: fator não obrigatório, validação aceita.
    assert verify_totp("sem-segredo", "")


def test_totp_uri_provisioning():
    uri = totp_uri("admin")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=SegPortal" in uri
