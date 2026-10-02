# Arquivos e nuvem — SegPortal

O **portal-auth** (porta **8090**) oferece o dashboard pessoal com:

1. **Compartilhamentos Active Directory** — home (`homeDirectory` / `homeDrive`), pastas departamentais e públicos  
2. **OneDrive e Google Drive** — montagem opcional no dashboard  
3. **Gerenciador HTML** — listar, enviar (arrastar e soltar), criar pasta, renomear, baixar e excluir  

Manuais: [USER_MANUAL.md](USER_MANUAL.md) · [ADMIN_MANUAL.md](ADMIN_MANUAL.md).

![Dashboard com pastas AD](images/portal-home-ad.jpg)

---

## Fluxo com Active Directory

1. Usuário marca **Autenticar via Active Directory** (ou `LDAP_ENABLED=true`)  
2. O portal resolve shares em [`config/files/shares.yaml`](../config/files/shares.yaml) (`shares.ad_attributes` + `shares.corporate`)  
3. Em produção, o UNC do `homeDirectory` é montado no backend; em demo, usa árvore local em `DEMO_SHARES_ROOT`  

![Gerenciador de arquivos](images/portal-files.jpg)

---

## OneDrive / Google Drive

![Nuvem montada](images/portal-cloud-mounted.jpg)

```yaml
cloud_drives:
  onedrive:
    enabled: true
    client_id: ""   # vazio = modo demo
  google_drive:
    enabled: true
    client_id: ""
```

Sem `client_id`, a montagem cria pasta demo sob `DEMO_SHARES_ROOT/cloud/...`.

---

## API (resumo)

| Método | Rota | Uso |
|--------|------|-----|
| POST | `/api/login` | Sessão cookie (`use_active_directory`; com TOTP ativo responde `mfa_required` em 2 etapas) |
| GET | `/api/dashboard` | Shares AD + estado das nuvens + `computers` **filtrados pelo papel** |
| GET | `/api/computers/{id}/authorize` | Valida permissão **no servidor** (403 para comum em item admin) |
| GET | `/api/files/{share_id}` | Listar pasta |
| POST | `/api/files/{share_id}/upload` | Enviar arquivo |
| POST | `/api/files/{share_id}/mkdir` | Criar pasta |
| POST | `/api/files/{share_id}/rename` | Renomear |
| DELETE | `/api/files/{share_id}/delete` | Excluir |
| POST | `/api/cloud/{provider}/mount` | Montar OneDrive / Google Drive |
| GET | `/api/health` | Saúde do serviço |

> **Rate limiting (slowapi):** login **5/min**; escrita (`upload`/`mkdir`/`rename`/`delete`/`mount`) **30/min** — acima do limite → `429`. Desligar só em dev com `SEGPORTAL_RATE_LIMIT_ENABLED=0`.

---

## UI

Interface em HTML/CSS/JS (`services/portal-auth/static`):

- Tipografia Source Sans 3 + Fraunces  
- Cores institucionais AQNE (navy / ouro)  
- Abas **Início · Arquivos · Sessões**  
- Diálogo acessível para nova pasta/renomear  
- Arrastar e soltar; alvos de clique ≥ 44px  

![Nova pasta](images/portal-files-folder.jpg)

---

## Operação (admin)

Ver [ADMIN_MANUAL.md](ADMIN_MANUAL.md) §3. Variáveis: `PORTAL_SESSION_SECRET` *(obrigatória)*, `SEGPORTAL_COOKIE_SECURE`, `SEGPORTAL_LOCAL_USERS`/`SEGPORTAL_LOCAL_PASSWORDS`, `SEGPORTAL_TOTP_SECRETS`, `SEGPORTAL_RATE_LIMIT_ENABLED`, `DEMO_SHARES_ROOT`, `SESSIONS_INTERNAL_URL`, `LDAP_ENABLED`.
