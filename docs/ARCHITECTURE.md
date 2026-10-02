# Arquitetura — SegPortal AQNE

SegPortal implementa **ZTNA (Zero Trust Network Access)** para o AQNE com portal clientless HTML5 SegPortal clientless HTML5.

## Visão geral

![Arquitetura](images/architecture-overview.jpg)

| Componente | Função | Serviço / pod |
|------------|--------|----------------|
| **portal-auth** | Dashboard pessoal: AD shares, OneDrive/Google Drive, file manager HTML | `portal-auth` (`:8090`) |
| **SegPortal** | Portal web, autenticação e autorização de sessões | `sessões` (`:8080`) |
| **guacd** | Proxy de protocolos RDP, VNC e SSH | `guacd` |
| **web-browser** | Firefox via VNC — navegador HTML **padrão** | `web-browser` |
| **proxy-egress** | Squid — HTTP(S) com IP institucional | `proxy-egress` |
| **PostgreSQL** | Metadados de conexões, usuários e sessões | `postgres` |
| **Bootstrap** | Seed idempotente: papéis + navegador padrão | `segportal-bootstrap` |

## Fluxo de autenticação

![Fluxo LDAP + MFA](images/auth-flow.jpg)

1. Usuário acessa o **portal-auth** (`:8090`) e/ou o SegPortal
2. Autentica via **conta local** (usuários de `SEGPORTAL_LOCAL_USERS`/`SEGPORTAL_LOCAL_PASSWORDS`) e/ou **LDAP/AD** (`aqne.jus.br`, bind real via `ldap3` quando `LDAP_ENABLED=true`)
3. No dashboard, recebe pastas AD e opção de montar OneDrive/Google Drive
4. MFA: **TOTP** por usuário (`SEGPORTAL_TOTP_SECRETS`, login em 2 etapas) e/ou **RADIUS** (`MFA_ENABLED=true`)
5. Sessões remotas: no mínimo o **Navegador Web SegPortal**

> **LDAP fail-closed**: com LDAP habilitado, sem bind válido → `401`; usuários locais só autenticam com LDAP desligado. A sessão do portal exige `PORTAL_SESSION_SECRET` (o portal não inicia sem ela).

## Deploy Kubernetes

![Pods K8s](images/k8s-pods.jpg)

| Workload | Escala típica |
|----------|---------------|
| `portal-auth` | HPA 2–6 |
| `sessões-html5` | HPA 2–10 |
| `guacd` | HPA 2–20 |
| `web-browser` | HPA 2–10 |
| `proxy-egress` | HPA 1–5 |
| `postgres` | StatefulSet 1 |
| `segportal-bootstrap` | Job (uma execução por deploy/boot) |

## Mockup do portal

![Mockup](images/segportal-mockup.jpg)

## Modularidade

```
segportal/
├── services/portal-auth/   # Dashboard AD/nuvem + file manager (:8090)
├── services/guacamole/     # Backend interno de sessões HTML5 (não exposto na UI)
├── services/guacd/         # Daemon de protocolos (interno)
├── services/web-browser/   # Firefox via VNC
├── services/egress-proxy/  # Squid
├── config/files/shares.yaml
├── scripts/bootstrap-segportal.sh
├── scripts/capture-portal-docs.py
├── k8s/web-browser/
├── k8s/bootstrap/
└── k8s/overlays/
```

## Decisões de design

| Decisão | Motivo |
|---------|--------|
| portal-auth separado | UI de arquivos/AD/nuvem sem acoplar ao SegPortal Java |
| Usuários locais via ENV | Remove senhas demo do código; provisionamento por Secret/ambiente |
| LDAP real via ldap3 (fail-closed) | Sem bind válido → 401; nada de fallback silencioso para contas locais |
| MFA TOTP nativo | 2FA por usuário sem infra adicional (além do autenticador) |
| Rate limiting (slowapi) | Mitiga brute force em login e escrita da API |
| Catálogo de computadores server-side | Frontend sem catálogo hardcoded; `/api/computers/{id}/authorize` valida no servidor |
| Navegador padrão no boot | Todo usuário navega sem VPN desde o primeiro login |
| Bootstrap automático | Elimina seed manual e drift de configuração |
| Pedidos com aprovação | Usuário não cria conexões sozinho |
| LDAP opcional | Homologação e emergência sem AD |
| Pods separados | Escala e blast radius independentes |
| Squid whitelist | Egress controlado no lugar da VPN HTTP |

## Referências

- [USER_MANUAL.md](USER_MANUAL.md) · [ADMIN_MANUAL.md](ADMIN_MANUAL.md)
- [FILES.md](FILES.md) · [CONNECTIONS.md](CONNECTIONS.md)
- [ROLES.md](ROLES.md) · [CONFIGURATION.md](CONFIGURATION.md)
- [DEPLOYMENT.md](DEPLOYMENT.md) · [SECURITY.md](SECURITY.md)
- [CI_CD.md](CI_CD.md)
