"""Testes das defesas OWASP do portal-auth (headers, path traversal, LDAP)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "portal-auth"))

# Ambiente mínimo para importar o app (chave de sessão obrigatória; rate limit off).
os.environ.setdefault("PORTAL_SESSION_SECRET", "test-secret-owasp-strong")
os.environ.setdefault("SEGPORTAL_RATE_LIMIT_ENABLED", "0")
os.environ.setdefault("SEGPORTAL_COOKIE_SECURE", "0")

from app.files import _join, _valid_name  # noqa: E402
from app.main import app  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app)


class TestSecurityHeaders:
    def test_core_headers_present(self) -> None:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Referrer-Policy"] == "no-referrer"
        assert "Permissions-Policy" in r.headers

    def test_csp_locks_down_scripts_and_framing(self) -> None:
        csp = client.get("/api/health").headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "'unsafe-eval'" not in csp
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp

    def test_hsts_only_under_https(self) -> None:
        assert "Strict-Transport-Security" not in client.get("/api/health").headers
        r = client.get("/api/health", headers={"x-forwarded-proto": "https"})
        assert r.headers["Strict-Transport-Security"].startswith("max-age=")


class TestSafeNames:
    @pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b", "x\x00y", 'a"b'])
    def test_rejects_dangerous_names(self, bad: str) -> None:
        assert _valid_name(bad) is False

    @pytest.mark.parametrize("ok", ["arquivo.txt", "Relatório 2026.pdf", "pasta-1"])
    def test_accepts_normal_names(self, ok: str) -> None:
        assert _valid_name(ok) is True


class TestPathTraversal:
    def test_valid_subpath_allowed(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        (root / "sub").mkdir(parents=True)
        assert _join(root, "sub") == (root / "sub").resolve()

    def test_parent_escape_is_contained(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        # Componentes '..' são descartados: o alvo permanece dentro da raiz.
        target = _join(root, "../../etc/passwd")
        root_resolved = root.resolve()
        assert target == root_resolved or root_resolved in target.parents

    def test_symlink_escape_blocked(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("top secret", encoding="utf-8")
        root = tmp_path / "root"
        root.mkdir()
        os.symlink(outside, root / "link")
        with pytest.raises(HTTPException) as exc:
            _join(root, "link/secret.txt")
        assert exc.value.status_code == 400


class TestCsrf:
    def test_write_without_token_is_rejected(self) -> None:
        r = client.post("/api/files/home/mkdir", json={"path": "", "name": "x"})
        assert r.status_code == 403

    def test_write_with_matching_token_passes_csrf(self) -> None:
        client.get("/")  # define o cookie segportal_csrf
        token = client.cookies.get("segportal_csrf")
        assert token
        # CSRF válido: passa da checagem e só então exige sessão (401), não 403.
        r = client.post(
            "/api/files/home/mkdir",
            json={"path": "", "name": "x"},
            headers={"X-CSRF-Token": token},
        )
        assert r.status_code == 401

    def test_home_sets_csrf_cookie(self) -> None:
        fresh = TestClient(app)
        fresh.get("/")
        assert fresh.cookies.get("segportal_csrf")


class TestLdapFailClosed:
    def test_empty_password_rejected_before_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Senha vazia deve ser recusada (evita unauthenticated bind do AD)."""
        from app import auth

        monkeypatch.setenv("LDAP_HOSTNAME", "ldap.example.test")
        monkeypatch.setattr(
            auth,
            "ldap_config",
            lambda: {"ldap": {"hostname": "ldap.example.test", "user_base_dn": "DC=x,DC=y"}},
        )
        with pytest.raises(HTTPException) as exc:
            auth._authenticate_ldap("alice", "")
        assert exc.value.status_code == 401
