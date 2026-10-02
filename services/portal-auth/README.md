# Portal Auth — SegPortal AQNE

Serviço FastAPI do **dashboard pessoal**: autenticação (local / Active Directory),
montagem de pastas corporativas indicadas pelo AD, OneDrive/Google Drive e
gerenciador de arquivos HTML.

## URLs

| Ambiente | URL |
|----------|-----|
| Compose local | http://localhost:8090 |
| Health | `GET /api/health` |

## Usuários locais (via ENV)

Não há mais credenciais demo (`admin`/`admin`, `usuario`/`usuario`) no código. Os usuários locais vêm de `SEGPORTAL_LOCAL_USERS` (`login:Nome:Papel:email;...`) e `SEGPORTAL_LOCAL_PASSWORDS` (senhas na mesma ordem):

```bash
SEGPORTAL_LOCAL_USERS="admin:Administrador:admin:admin@aqne.jus.br;usuario:Usuário Padrão:user:usuario@aqne.jus.br"
SEGPORTAL_LOCAL_PASSWORDS="<senha_forte_admin>;<senha_forte_usuario>"
```

Sem essas variáveis **não há usuários locais**. MFA TOTP: `SEGPORTAL_TOTP_SECRETS` (JSON por usuário) — login em 2 etapas (`mfa_required` + código de 6 dígitos). Rate limiting (`SEGPORTAL_RATE_LIMIT_ENABLED`): login 5/min e escrita 30/min.

Marque **Autenticar via Active Directory** no login para usar LDAP real (`ldap3`, fail-closed: sem bind válido → `401`).

## OneDrive / Google Drive

No painel **Início**, use **Montar**. Sem `client_id` em `config/files/shares.yaml`,
a montagem é em **modo demonstração** (pasta local sob `/data/shares/cloud/...`).
Com OAuth configurado, o portal redireciona ao provedor.

## Arquivos

- Configuração: `config/files/shares.yaml`
- Atributos AD: `homeDirectory`, `homeDrive`, `profilePath`, `extensionAttribute10`
- UI: `static/index.html` + `static/assets/`

## Desenvolvimento local (sem Docker)

```bash
cd services/portal-auth
pip install -r requirements.txt
export PORTAL_SESSION_SECRET=$(openssl rand -hex 32)   # obrigatória — sem ela o portal não inicia
export SEGPORTAL_LOCAL_USERS="admin:Administrador:admin:admin@aqne.jus.br"
export SEGPORTAL_LOCAL_PASSWORDS="<senha_forte>"
DEMO_SHARES_ROOT=/tmp/segportal-shares uvicorn app.main:app --reload --port 8090
```

## Compose

O serviço `portal-auth` sobe com a stack em `docker-compose.yml` (porta **8090**).
