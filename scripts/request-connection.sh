#!/usr/bin/env bash
# Usuário solicita um novo terminal/aplicação (fica pending até o admin aprovar).
# Uso:
#   ./scripts/request-connection.sh usuario "Meu RDP" rdp 10.10.20.50 3389 "Acesso ao sistema X"
set -euo pipefail

USER_NAME="${1:-}"
CONN_NAME="${2:-}"
PROTOCOL="${3:-}"
HOSTNAME="${4:-}"
PORT="${5:-}"
JUSTIFICATION="${6:-}"

if [[ -z "$USER_NAME" || -z "$CONN_NAME" || -z "$PROTOCOL" || -z "$HOSTNAME" || -z "$JUSTIFICATION" ]]; then
  echo "Uso: $0 <username> <nome_conexao> <rdp|vnc|ssh|browser> <host> [porta] <justificativa>" >&2
  exit 1
fi

PG_HOST="${POSTGRES_HOSTNAME:-localhost}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_DB="${POSTGRES_DATABASE:-guacamole_db}"
PG_USER="${POSTGRES_USER:-guacamole_user}"
PG_PASS="${POSTGRES_PASSWORD:?Defina POSTGRES_PASSWORD no ambiente}"
export PGPASSWORD="$PG_PASS"

# Validação estrita dos valores antes de tocar o banco (mitiga injeção SQL).
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [[ "$PORT" -lt 1 || "$PORT" -gt 65535 ]]; then
  if [[ -n "$PORT" ]]; then
    echo "ERRO: porta inválida: $PORT" >&2
    exit 1
  fi
fi
for var in USER_NAME PROTOCOL HOSTNAME; do
  if [[ "${!var}" =~ [^a-zA-Z0-9._-] ]]; then
    echo "ERRO: campo inválido ($var): ${!var}" >&2
    exit 1
  fi
done
if [[ "$CONN_NAME" =~ [^a-zA-Z0-9._ -] ]] || [[ "$JUSTIFICATION" =~ [^a-zA-Z0-9á-úÁ-Úã-õÃ-Õ â-úà-ùçñ.,:;()/-] ]]; then
  echo "ERRO: caracteres inválidos em nome da conexão ou justificativa" >&2
  exit 1
fi

# Parâmetros passados via psql -v (escapados pelo cliente, não interpolação SQL).
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 \
  -v v_user="$USER_NAME" \
  -v v_name="$CONN_NAME" \
  -v v_protocol="$PROTOCOL" \
  -v v_host="$HOSTNAME" \
  -v v_port="${PORT:-NULL}" \
  -v v_just="$JUSTIFICATION" <<'SQL'
INSERT INTO segportal_connection_request (
  requester_username, connection_name, protocol, hostname, port, justification
) VALUES (
  :'v_user', :'v_name', lower(:'v_protocol'), :'v_host',
  CASE WHEN :'v_port' = 'NULL' THEN NULL ELSE cast(:'v_port' AS integer) END,
  :'v_just'
)
RETURNING request_id, status;
SQL

echo "Pedido registrado como pending. O administrador deve aprovar com:"
echo "  ./scripts/approve-connection-request.sh <request_id>"