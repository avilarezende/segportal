# Segurança — SegPortal AQNE

Controles de segurança do portal ZTNA com acesso clientless HTML5.

## Princípios Zero Trust

1. **Verificar explicitamente** — autenticação local e/ou LDAP + MFA antes de qualquer recurso
2. **Menor privilégio** — conexões mapeadas por grupo; pedidos extras exigem aprovação
3. **Assumir violação** — sessões isoladas, timeout agressivo
4. **Micro-segmentação** — pods e redes separados por função

## Autenticação

| Camada | Controle |
|--------|----------|
| Local (JDBC) | Provisionada via ENV (`SEGPORTAL_LOCAL_USERS` / `SEGPORTAL_LOCAL_PASSWORDS`) — **sem as variáveis não há usuários locais** (nada hardcoded) |
| Identidade AD | Opcional (`LDAP_ENABLED=true` / `use_active_directory`) via **LDAP real (`ldap3`)** — **fail-closed: sem bind válido → `401`** |
| MFA | **TOTP** por usuário (`SEGPORTAL_TOTP_SECRETS`, login em 2 etapas) e/ou RADIUS corporativo — opcional |
| Sessão | `PORTAL_SESSION_SECRET` **obrigatória** (sem ela o portal não inicia); cookie `secure=True` (desligar só em dev com `SEGPORTAL_COOKIE_SECURE=0`); timeout 60 min inatividade, limite de conexões simultâneas |

Conta de serviço `svc-segportal` só é necessária quando LDAP está habilitado.  
Guia de usuários locais: [LOCAL_ADMIN.md](LOCAL_ADMIN.md).

### Fluxo MFA TOTP (2 etapas)

1. `POST /api/login` sem código → resposta **`mfa_required`**
2. Usuário informa o **código de 6 dígitos** do autenticador → sessão liberada

Segredos: `SEGPORTAL_TOTP_SECRETS` (JSON, ex.: `{"admin": "BASE32SECRET"}`), gerados com `pyotp.random_base32()` e cadastrados via URI `otpauth://`. Detalhes: [CONFIGURATION.md](CONFIGURATION.md#4-mfa-radius-e-totp).

## Papéis e isolamento

| Papel | Grupo | Visão de sessões | Configuração |
|-------|-------|------------------|--------------|
| **Administrador** | `segportal-admins` / `GG-SegPortal-Admin` | Todas (`ADMINISTER`) | Completa + aprovações |
| **Usuário** | `segportal-users` / `GG-SegPortal-Usuarios` | Apenas a própria | Nenhuma |

Usuários normais recebem `READ` no **Navegador Web SegPortal** (padrão) e nas conexões dos grupos de negócio / aprovadas. Detalhes: [ROLES.md](ROLES.md) · [CONNECTIONS.md](CONNECTIONS.md).

## Navegador HTML padrão

| Controle | Medida |
|----------|--------|
| Exposição VNC | Apenas rede interna (guacd → `web-browser:5900`) |
| Senha VNC | **Obrigatória** via ENV — `VNC_PASSWORD` (serviço) e `SEGPORTAL_VNC_PASSWORD` (bootstrap SQL), sem defaults em claro |
| TLS VNC | `SECURE_CONNECTION=0` (SegPortal não usa VNC TLS) |
| Egress | Sites externos passam pelo Squid (`proxy-egress`) |
| Criação de conexões | Usuário **não** cria sozinho — aprovação admin |

## Rate limiting

O portal aplica **rate limiting (slowapi)**:

- Login (`POST /api/login`): **5/min**
- Escrita da API (`upload`/`mkdir`/`rename`/`delete`/`mount`): **30/min**
- Acima do limite → **`429 Too Many Requests`**
- Desligável apenas para testes/dev: `SEGPORTAL_RATE_LIMIT_ENABLED=0`

## Autorização server-side (catálogo de computadores)

- O catálogo **não é hardcoded no frontend**: `GET /api/dashboard` retorna `computers` já filtrado pelo papel.
- `GET /api/computers/{id}/authorize` valida no servidor antes de abrir a sessão.
- Usuário comum em item de admin → **`403 Forbidden`** (impossível burlar pelo cliente).

## Comunicação

- **TLS** em todo tráfego externo (Ingress + cert-manager)
- **LDAPS** para bind e busca de usuários (quando LDAP ligado)
- Tráfego interno do cluster: rede CNI isolada (NetworkPolicies recomendadas)

## Egress controlado

O proxy Squid permite apenas destinos na whitelist (ex.: `*.aqne.jus.br`, `*.jus.br`, `*.gov.br`). Demais destinos são **negados**. O IP de saída é o institucional do tribunal.

## Dados sensíveis

- Secrets Kubernetes para credenciais (não em ConfigMaps) — inclusive `SEGPORTAL_LOCAL_PASSWORDS`, `GUACAMOLE_ADMIN_PASSWORD`, `VNC_PASSWORD`/`SEGPORTAL_VNC_PASSWORD`, `SEGPORTAL_TOTP_SECRETS`, `PORTAL_SESSION_SECRET`, LDAP/RADIUS
- `.env` e `secrets/` no `.gitignore`
- **Nenhuma credencial padrão/demo no código** — sem variáveis de usuários locais, não há usuários locais
- `PORTAL_SESSION_SECRET` é gerada por ambiente (`openssl rand -hex 32`) — reutilizar o valor de exemplo faz o portal **recusar iniciar**

## Proteção no pipeline

- O CI roda o job **`security-scan`** (gitleaks — vazamento de segredos + bandit — análise estática Python) em todo PR/push
- O CI valida `docker compose config` com **variáveis dummy** (nenhum segredo real em CI)
- Detalhes: [CI_CD.md](CI_CD.md)

## Hardening de containers

- Imagens base oficiais SegPortal 1.5.5 / jlesage Firefox
- Usuário não-root onde aplicável
- Health checks e limites de recursos (requests/limits)
- Sem privilégios elevados nos pods

## Auditoria

- Pedidos de conexão registrados em `segportal_connection_request`
- Encaminhar logs Squid e SegPortal ao SIEM
- Retenção conforme política AQNE

## Resposta a incidentes

1. Revogar sessões: reiniciar deployment `sessions`
2. Rotacionar senhas/secrets LDAP e RADIUS + **rotacionar `PORTAL_SESSION_SECRET`** e `SEGPORTAL_TOTP_SECRETS` se houver suspeita de comprometimento
3. Bloquear egress: escalar `proxy-egress` para 0 ou NetworkPolicy deny-all
4. Isolar `web-browser` se houver abuso de navegação

## Conformidade

- Acesso remoto substitui VPN legada com controles equivalentes ou superiores
- Dados processuais acessados via RDP/VNC permanecem nos sistemas de origem
- Revisão periódica de grupos AD, aprovações pendentes e whitelist Squid

## Referências

- [CONFIGURATION.md](CONFIGURATION.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [CONNECTIONS.md](CONNECTIONS.md)
- [MANUAL.md](MANUAL.md)
