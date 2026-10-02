# Usuários locais e administrador — SegPortal AQNE

Manual operacional completo: **[ADMIN_MANUAL.md](ADMIN_MANUAL.md)**.  
Manual do usuário final: [USER_MANUAL.md](USER_MANUAL.md).

O SegPortal possui autenticação **local** (PostgreSQL / JDBC) e/ou **LDAP**. Usuários locais **não são mais criados com senhas embutidas no código**: eles vêm das variáveis `SEGPORTAL_LOCAL_USERS` e `SEGPORTAL_LOCAL_PASSWORDS`. **Sem essas variáveis não há usuários locais** — as antigas contas demo `admin`/`admin` e `usuario`/`usuario` foram removidas do código.

O **portal-auth** (`:8090`) usa as **mesmas variáveis** para autenticar o dashboard de arquivos.

---

## Usuários locais (provisionamento via ENV)

### Variáveis

| Variável | Formato | Obrigatória? |
|----------|---------|:-------------:|
| `SEGPORTAL_LOCAL_USERS` | `login:Nome de exibição:Papel:email;...` (vários separados por `;`) | Sim, para haver usuários locais |
| `SEGPORTAL_LOCAL_PASSWORDS` | Senhas na **mesma ordem** dos usuários, separadas por `;` | Sim, para haver usuários locais |

- **Papel**: `admin` ou `user` (mapeamento em [ROLES.md](ROLES.md)).
- **Email**: usado para identificação/contato do usuário no portal.
- As senhas devem ser fortes e provisionadas via **Secret** (Kubernetes) ou `.env` **fora** do repositório — nunca em claro no código.

Exemplo:

```bash
SEGPORTAL_LOCAL_USERS="admin:Administrador:admin:admin@aqne.jus.br;usuario:Usuário Padrão:user:usuario@aqne.jus.br"
SEGPORTAL_LOCAL_PASSWORDS="<senha_forte_admin>;<senha_forte_usuario>"
```

> **Sem `SEGPORTAL_LOCAL_USERS` / `SEGPORTAL_LOCAL_PASSWORDS` o portal não tem usuários locais** e só aceita login se o LDAP estiver habilitado.

Os usuários são sincronizados/criados no banco de sessões pelo entrypoint (`bootstrap`) a partir dessas variáveis. Alterou as variáveis? Reaplique o bootstrap:

```bash
./scripts/bootstrap-segportal.sh   # idempotente
```

### Admin criado pelo bootstrap (`GUACAMOLE_ADMIN_PASSWORD`)

O usuário administrador inicial é criado pelo job **`segportal-bootstrap`** com a senha da variável `GUACAMOLE_ADMIN_PASSWORD` (**obrigatória** — o bootstrap não roda sem ela). Após o boot, você pode seguir a gestão normal de usuários locais:

| Campo | Valor inicial |
|-------|----------------|
| Usuário | o que estiver em `SEGPORTAL_LOCAL_USERS` (ex.: `admin`) |
| Senha | `GUACAMOLE_ADMIN_PASSWORD` |
| Origem | Job `segportal-bootstrap` (ENV/Secret) |
| Depende de LDAP? | **Não** |

> **Obrigatório em produção:** use senhas fortes e diferentes para cada ambiente; jamais deixe valores em claro no repositório.

---

## Alterar a senha de um usuário local

### Opção A — Interface SegPortal

1. Login como administrador
2. Menu do usuário → **Settings → Preferences** (ou perfil)
3. Defina a nova senha
4. Faça logout e valide o novo login

### Opção B — Script (SQL)

```bash
export POSTGRES_PASSWORD=...
./scripts/change-local-password.sh admin 'NovaSenhaForte!'
```

Via Docker:

```bash
docker compose -f docker-compose.dev.yml exec -T postgres \
  env POSTGRES_PASSWORD=devpassword \
  bash -c 'apt-get update -qq && apt-get install -y -qq postgresql-client python3 >/dev/null'
# Ou rode o script a partir do host com psql apontando para a porta publicada
```

### Opção C — API REST SegPortal

Com token de sessão admin, `PUT /api/session/data/{dataSource}/users/admin/password`.

---

## Desativar ou excluir um usuário local

> Só faça isso **depois** de garantir outro administrador local (via `SEGPORTAL_LOCAL_USERS`/`SEGPORTAL_LOCAL_PASSWORDS`) ou admins via LDAP (`GG-SegPortal-Admin`).

### Desativar (recomendado)

Mantém o registro, impede login:

```bash
./scripts/delete-local-user.sh admin --disable
```

### Excluir permanentemente

```bash
./scripts/delete-local-user.sh admin --delete
```

Checklist antes de excluir:

1. Existe outro usuário com permissão `ADMINISTER`?
2. LDAP admin testado (se LDAP estiver habilitado)?
3. Backup do PostgreSQL realizado?

Para **reativar** um usuário desativado (SQL no schema interno de sessões — nomes de tabela não aparecem na UI):

```sql
UPDATE guacamole_user u
SET disabled = FALSE
FROM guacamole_entity e
WHERE u.entity_id = e.entity_id AND e.name = 'admin';
```

---

## Usuários locais (sem LDAP)

Com `LDAP_ENABLED=false` (padrão até o admin configurar o AD), a autenticação é **somente local**, e os usuários vêm das variáveis `SEGPORTAL_LOCAL_USERS` / `SEGPORTAL_LOCAL_PASSWORDS`:

1. Defina as variáveis no `.env`/Secret **antes** do primeiro boot (não há contas demo no código)
2. O `segportal-bootstrap` cria/sincroniza os usuários e a senha do admin (`GUACAMOLE_ADMIN_PASSWORD`)
3. Associe a grupos de negócio (`segportal-financeiro`, etc.) conforme [ROLES.md](ROLES.md)
4. Para contas adicionais, você também pode usar **Settings → Users → New User** na UI SegPortal após o login como admin

---

## Configurar apontamentos LDAP (pelo administrador)

Arquivo de referência: `config/ldap/ldap-settings.yaml`

| Campo | Variável / chave | Exemplo |
|-------|------------------|---------|
| Ligar LDAP | `LDAP_ENABLED` | `true` |
| Servidor | `LDAP_HOSTNAME` | `ldap.aqne.jus.br` |
| Porta | `LDAP_PORT` | `636` |
| Criptografia | `LDAP_ENCRYPTION_METHOD` | `ssl` / `starttls` / `none` |
| Domínio | `ldap.domain` | `aqne.jus.br` |
| Base DN | `LDAP_USER_BASE_DN` | `OU=Usuarios,DC=aqne,DC=jus,DC=br` |
| UID / atributo | `LDAP_USERNAME_ATTRIBUTE` | `sAMAccountName` ou `uid` |
| Bind DN | `LDAP_SEARCH_BIND_DN` | conta de serviço |
| Senha bind | `LDAP_SEARCH_BIND_PASSWORD` | Secret |
| Cadeia CA | `LDAP_CA_CHAIN_FILE` | PEM montado no pod |
| Cert. servidor | `LDAP_SERVER_CERTIFICATE_FILE` | opcional |

### Procedimento

1. Preencha `config/ldap/ldap-settings.yaml` (ou Secret/ConfigMap no Rancher)
2. Monte a cadeia CA em `/etc/certs/ldap-ca-chain.pem`
3. Defina `LDAP_ENABLED=true` e demais variáveis
4. Reinicie o deployment `sessions` / portal
5. Teste login com conta AD

> **Comportamento (LDAP real via `ldap3`):** com LDAP habilitado, o login faz bind LDAP de verdade usando `LDAP_HOSTNAME`, `LDAP_PORT`, `LDAP_USER_BASE_DN` e `LDAP_USERNAME_ATTRIBUTE`, e resolve os grupos de papel em `role_groups`. **Fail-closed**: sem bind válido (credencial errada, servidor indisponível, grupo sem papel mapeado) → **`401`**. Nesse modo, usuários **locais não autenticam** — a conta local só é aceita com `LDAP_ENABLED=false`.

Se LDAP não for configurado (`LDAP_ENABLED=false`), o entrypoint remove todas as chaves `ldap-*` e o portal opera **somente com usuários locais** (via `SEGPORTAL_LOCAL_USERS`/`SEGPORTAL_LOCAL_PASSWORDS`).

Detalhes técnicos: [CONFIGURATION.md](CONFIGURATION.md).

---

## Relação LDAP × usuários locais

```
LDAP_ENABLED=false  →  só local (usuários de SEGPORTAL_LOCAL_USERS / SEGPORTAL_LOCAL_PASSWORDS)
LDAP_ENABLED=true   →  somente LDAP real (bind via ldap3) — sem bind válido → 401
                        — usuários locais NÃO autenticam nesse modo
LDAP fora do ar     →  fail-closed → 401 (exceto se LDAP for desligado via ENV)
```

---

## Referências

- [ROLES.md](ROLES.md) — papéis admin / usuário
- [CONFIGURATION.md](CONFIGURATION.md) — LDAP completo
- [SECURITY.md](SECURITY.md) — hardening
- Scripts: `change-local-password.sh`, `delete-local-user.sh`, `seed-roles.sh`, `bootstrap-segportal.sh`
