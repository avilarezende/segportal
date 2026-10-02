"""Catálogo de computadores/aplicações do SegPortal.

A autorização é feita aqui no servidor (o papel do usuário define o que é
retornado). O frontend nunca deve ser a fonte de verdade para restringir
acesso — ele apenas exibe o que a API já autorizou.
"""

from __future__ import annotations

from typing import Any

# Catálogo completo. `admin_only` é aplicado no servidor.
CATALOG: list[dict[str, Any]] = [
    {
        "id": "browser-html",
        "title": "Navegador Web SegPortal",
        "description": "Navegação corporativa HTML5 já disponível na aba Navegador.",
        "kind": "browser",
        "badge": "Padrão",
        "admin_only": False,
    },
    {
        "id": "desktop-financeiro",
        "title": "Desktop Financeiro",
        "description": "Estação remota com sistemas financeiros (liberação sob demanda).",
        "kind": "desktop",
        "badge": "RDP",
        "embed": "/browser/desktop.html?name=Desktop%20Financeiro",
        "admin_only": False,
    },
    {
        "id": "desktop-admin",
        "title": "Desktop Administrativo",
        "description": "Estação remota para tarefas administrativas.",
        "kind": "desktop",
        "badge": "RDP",
        "embed": "/browser/desktop.html?name=Desktop%20Administrativo",
        "admin_only": True,
    },
]


def catalogo_para_usuario(role: str) -> list[dict[str, Any]]:
    """Devolve apenas os itens que o papel do usuário tem permissão de ver.

    Itens restritos (admin_only) só são retornados para admin. Nunca confie
    em filtragem no cliente.
    """
    is_admin = role == "admin"
    items = []
    for item in CATALOG:
        if item.get("admin_only") and not is_admin:
            continue
        public = {k: v for k, v in item.items() if k != "admin_only"}
        items.append(public)
    return items


def item_autorizado(role: str, item_id: str) -> dict[str, Any] | None:
    """Valida se o usuário pode abrir um item específico (por id)."""
    for item in CATALOG:
        if item.get("id") != item_id:
            continue
        if item.get("admin_only") and role != "admin":
            return None
        public = {k: v for k, v in item.items() if k != "admin_only"}
        return public
    return None
