# Deploy — SegPortal AQNE

Guia de implantação em Docker Compose (dev) e Kubernetes/Rancher (produção).

## Desenvolvimento local

```bash
git clone https://github.com/avilarezende/segportal.git
cd segportal
cp .env.example .env
# Obrigatório: POSTGRES_PASSWORD, PORTAL_SESSION_SECRET,
# SEGPORTAL_LOCAL_USERS + SEGPORTAL_LOCAL_PASSWORDS,
# GUACAMOLE_ADMIN_PASSWORD, VNC_PASSWORD/SEGPORTAL_VNC_PASSWORD
# (LDAP/MFA TOTP opcionais)
docker compose up --build
```

> O portal **não inicia** sem `PORTAL_SESSION_SECRET`. Sem `SEGPORTAL_LOCAL_USERS`/`SEGPORTAL_LOCAL_PASSWORDS` não há usuários locais.

Acesse: http://localhost:8090

O serviço **`segportal-bootstrap`** aplica schema (se necessário), papéis, o admin (`GUACAMOLE_ADMIN_PASSWORD`), a conexão **Navegador Web SegPortal** (com `SEGPORTAL_VNC_PASSWORD`) e os usuários locais automaticamente. O serviço **`web-browser`** (Firefox/VNC) sobe junto ao stack.

Ambiente local **sem LDAP** — defina usuários antes de subir (não há credenciais demo no código):

```bash
SEGPORTAL_LOCAL_USERS="admin:Administrador:admin:admin@aqne.jus.br;usuario:Usuário Padrão:user:usuario@aqne.jus.br"
SEGPORTAL_LOCAL_PASSWORDS="<senha_forte_admin>;<senha_forte_usuario>"
docker compose -f docker-compose.dev.yml up --build
```

Reaplicar bootstrap (idempotente):

```bash
./scripts/bootstrap-segportal.sh
```

## Kubernetes

### Pré-requisitos

- Cluster Rancher 2.x com Ingress NGINX
- cert-manager para TLS
- Registry: `registry.aqne.jus.br/segportal`

### Secrets

```bash
kubectl create namespace segportal
kubectl apply -f k8s/postgres/secret.example.yaml -n segportal  # substitua valores
kubectl apply -f k8s/secret.example.yaml -n segportal
```

**Secrets obrigatórios/importantes** (sempre via Secret, nunca ConfigMap):

| Secret | Motivo |
|--------|--------|
| `POSTGRES_PASSWORD` | Banco de sessões |
| `PORTAL_SESSION_SECRET` | Cookie de sessão — **sem ela o portal não inicia** |
| `SEGPORTAL_LOCAL_USERS` / `SEGPORTAL_LOCAL_PASSWORDS` | Usuários locais (sem elas não há usuários locais) |
| `GUACAMOLE_ADMIN_PASSWORD` | Admin criado pelo bootstrap (obrigatória) |
| `VNC_PASSWORD` / `SEGPORTAL_VNC_PASSWORD` | Senha VNC do navegador padrão (**mesmo valor**) |
| `SEGPORTAL_TOTP_SECRETS` | 2FA TOTP por usuário (JSON `base32`) |

### Overlays

| Overlay | Uso | Comando |
|---------|-----|---------|
| `development` | Lab interno | `kubectl apply -k k8s/overlays/development` |
| `staging` | Homologação | `kubectl apply -k k8s/overlays/staging` |
| `production` | Produção | `kubectl apply -k k8s/overlays/production` |

O Job **`segportal-bootstrap`** (`k8s/bootstrap`) roda no apply e habilita o navegador padrão.

### Validação

```bash
./scripts/validate-k8s.sh
kubectl -n segportal get pods,job
kubectl -n segportal logs job/segportal-bootstrap
```

![Pods](images/k8s-pods.jpg)

## Rancher Fleet (GitOps)

1. Aplique `k8s/rancher-fleet/gitrepo.yaml` no cluster Fleet
2. O path `k8s/overlays/production` é sincronizado automaticamente
3. Clusters alvo: label `env=production`

## CI/CD

| Pipeline | Trigger | Ação |
|----------|---------|------|
| `ci.yml` | PR / push | Testes, lint, **security-scan (gitleaks+bandit)**, **compose-config (variáveis dummy)**, build Docker, validate K8s |
| `cd.yml` | Tag `v*.*.*` | Push imagens + deploy produção |

Detalhes: [CI_CD.md](CI_CD.md)

## Imagens Docker

| Imagem | Dockerfile |
|--------|------------|
| `sessões` | `services/Dockerfile` |
| `guacd` | `services/guacd/Dockerfile` |
| `egress-proxy` | `services/egress-proxy/Dockerfile` |
| `web-browser` | `services/web-browser/Dockerfile` |

## Rollback

```bash
kubectl rollout undo deployment -n segportal
kubectl rollout undo deployment/guacd -n segportal
kubectl rollout undo deployment/web-browser -n segportal
```

## Monitoramento

- Probes HTTP/TCP nos Deployments (`web-browser` na porta 5900)
- Logs: `kubectl logs -l app=sessions -n segportal`
- Bootstrap: `kubectl logs job/segportal-bootstrap -n segportal`

## Referências

- [CONFIGURATION.md](CONFIGURATION.md)
- [CONNECTIONS.md](CONNECTIONS.md)
- [MANUAL.md](MANUAL.md)
