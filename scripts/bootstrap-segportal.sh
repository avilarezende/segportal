#!/bin/sh
# Bootstrap SegPortal — schema JDBC (se necessário) + papéis + navegador HTML + pedidos.
# Roda automaticamente no boot (serviço segportal-bootstrap / Job K8s).
# Idempotente. Compatível com /bin/sh (Alpine ash).
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Compose/K8s montam em /scripts (com /scripts/sql); no repo fica em scripts/
if [ -d "${SCRIPT_DIR}/sql" ]; then
  SQL_DIR="${SCRIPT_DIR}/sql"
else
  SQL_DIR="${SCRIPT_DIR}/../scripts/sql"
fi

PG_HOST="${POSTGRES_HOSTNAME:-${POSTGRES_HOST:-localhost}}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_DB="${POSTGRES_DATABASE:-${POSTGRES_DB:-guacamole_db}}"
PG_USER="${POSTGRES_USER:-guacamole_user}"
PG_PASS="${POSTGRES_PASSWORD:?Define POSTGRES_PASSWORD no ambiente}"
WAIT_MAX="${SEGPORTAL_BOOTSTRAP_WAIT_SECONDS:-300}"

export PGPASSWORD="$PG_PASS"

psql_q() {
  psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 "$@"
}

echo "==> SegPortal bootstrap: aguardando PostgreSQL em ${PG_HOST}:${PG_PORT}/${PG_DB}..."
elapsed=0
until pg_isready -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; do
  if [ "$elapsed" -ge "$WAIT_MAX" ]; then
    echo "ERRO: PostgreSQL indisponível após ${WAIT_MAX}s" >&2
    exit 1
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done

table_exists() {
  psql_q -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='$1'" 2>/dev/null | grep -q 1
}

# Gera hash no formato Guacamole: SHA-256( UTF-8(password) || UPPER(hex(salt)) ).
# IMPORTANTE: o Guacamole concatena a senha com a representação HEXADECIMAL
# MAIÚSCULA do salt (não com os bytes crus do salt). Compatível com o guacadmin
# canônico. Usa sha256sum (presente no host e em postgres:16-alpine).
guac_hash() {
  password="$1"
  salt_hex=$(printf '%s' "$2" | tr 'a-f' 'A-F')
  if command -v openssl >/dev/null 2>&1; then
    printf '%s%s' "$password" "$salt_hex" | openssl dgst -sha256 | awk '{print $NF}' | tr 'a-f' 'A-F'
  else
    printf '%s%s' "$password" "$salt_hex" | sha256sum | cut -d' ' -f1 | tr 'a-f' 'A-F'
  fi
}
gen_salt() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    od -An -tx1 -N32 /dev/urandom | tr -d ' \n'
  fi
}

if ! table_exists guacamole_connection; then
  echo "==> Schema Guacamole ausente — aplicando SQL local (001/002)..."
  if [ ! -f "${SQL_DIR}/001-create-schema.sql" ] || [ ! -f "${SQL_DIR}/002-create-admin-user.sql" ]; then
    echo "ERRO: arquivos 001/002 ausentes em ${SQL_DIR}" >&2
    exit 1
  fi
  psql_q -f "${SQL_DIR}/001-create-schema.sql"
  GUAC_ADMIN_USER="${GUACAMOLE_ADMIN_USER:-guacadmin}"
  GUAC_ADMIN_PASSWORD="${GUACAMOLE_ADMIN_PASSWORD:?Defina GUACAMOLE_ADMIN_PASSWORD no ambiente}"
  ADMIN_SALT=$(gen_salt)
  ADMIN_HASH=$(guac_hash "$GUAC_ADMIN_PASSWORD" "$ADMIN_SALT")
  psql_q -v v_admin_user="$GUAC_ADMIN_USER" -v v_admin_hash="$ADMIN_HASH" -v v_admin_salt="$ADMIN_SALT" -f "${SQL_DIR}/002-create-admin-user.sql"
  echo "==> Schema Guacamole aplicado (admin provisionado via Secret)."
else
  echo "==> Schema Guacamole já presente."
fi

# Garante usuário admin (caso só 001 tenha rodado)
if ! psql_q -tAc "SELECT 1 FROM guacamole_entity WHERE name='guacadmin' AND type='USER'" 2>/dev/null | grep -q 1; then
  echo "==> Criando usuário admin padrão..."
  GUAC_ADMIN_PASSWORD="${GUACAMOLE_ADMIN_PASSWORD:?Defina GUACAMOLE_ADMIN_PASSWORD no ambiente}"
  ADMIN_SALT=$(gen_salt)
  ADMIN_HASH=$(guac_hash "$GUAC_ADMIN_PASSWORD" "$ADMIN_SALT")
  psql_q -v v_admin_user="guacadmin" -v v_admin_hash="$ADMIN_HASH" -v v_admin_salt="$ADMIN_SALT" -f "${SQL_DIR}/002-create-admin-user.sql"
fi

for f in 003-segportal-roles.sql 004-default-browser.sql 005-connection-requests.sql; do
  echo "==> Aplicando $f"
  case "$f" in
    004-default-browser.sql)
      VNC_PASS="${SEGPORTAL_VNC_PASSWORD:?Defina SEGPORTAL_VNC_PASSWORD no ambiente}"
      psql_q -v v_vnc_password="$VNC_PASS" -f "${SQL_DIR}/${f}"
      ;;
    *)
      psql_q -f "${SQL_DIR}/${f}"
      ;;
  esac
done

# Remove apenas CR/LF do fim da saída do psql (-tA não gera espaços nas bordas);
# NÃO pode remover espaços internos, senão nomes como "Navegador Web SegPortal"
# ficam corrompidos na comparação.
trim() { tr -d '\r\n'; }

NAME=$(psql_q -tAc "SELECT connection_name FROM guacamole_connection WHERE connection_name='Navegador Web SegPortal'" | trim)
if [ "$NAME" != "Navegador Web SegPortal" ]; then
  echo "ERRO: conexão Navegador Web SegPortal não foi criada (obtido='${NAME}')" >&2
  exit 1
fi

HOST=$(psql_q -tAc "SELECT parameter_value FROM guacamole_connection_parameter cp JOIN guacamole_connection c ON c.connection_id=cp.connection_id WHERE c.connection_name='Navegador Web SegPortal' AND cp.parameter_name='hostname'" | trim)
if [ "$HOST" != "web-browser" ]; then
  echo "ERRO: hostname VNC esperado 'web-browser', obtido '${HOST}'" >&2
  exit 1
fi

PASS=$(psql_q -tAc "SELECT parameter_value FROM guacamole_connection_parameter cp JOIN guacamole_connection c ON c.connection_id=cp.connection_id WHERE c.connection_name='Navegador Web SegPortal' AND cp.parameter_name='password'" | trim)
if [ -z "$PASS" ]; then
  echo "ERRO: parâmetro password VNC ausente na conexão" >&2
  exit 1
fi

READERS=$(psql_q -tAc "SELECT COUNT(*) FROM guacamole_connection_permission cp JOIN guacamole_connection c ON c.connection_id=cp.connection_id WHERE c.connection_name='Navegador Web SegPortal' AND cp.permission='READ'" | trim)
echo "OK: Firefox/VNC padrão habilitado (${READERS} permissões READ, password=***). Login: http://localhost:8080/guacamole"
