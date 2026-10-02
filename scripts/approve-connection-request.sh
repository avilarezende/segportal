#!/usr/bin/env bash
# Aprova um pedido de terminal/aplicação e cria a conexão Guacamole.
# Uso:
#   ./scripts/approve-connection-request.sh <request_id>
#   ./scripts/approve-connection-request.sh <request_id> --reject "motivo"
set -euo pipefail

REQUEST_ID="${1:-}"
ACTION="${2:---approve}"
NOTES="${3:-}"

if [[ -z "$REQUEST_ID" ]]; then
  echo "Uso: $0 <request_id> [--approve|--reject] [notas]" >&2
  exit 1
fi
if ! [[ "$REQUEST_ID" =~ ^[0-9]+$ ]]; then
  echo "ERRO: request_id inválido: $REQUEST_ID" >&2
  exit 1
fi

PG_HOST="${POSTGRES_HOSTNAME:-localhost}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_DB="${POSTGRES_DATABASE:-guacamole_db}"
PG_USER="${POSTGRES_USER:-guacamole_user}"
PG_PASS="${POSTGRES_PASSWORD:?Defina POSTGRES_PASSWORD no ambiente}"
REVIEWER="${REVIEWER_USERNAME:-guacadmin}"
export PGPASSWORD="$PG_PASS"

# Notas são passadas via parâmetro do psql (sem interpolação SQL).
NOTES_SAFE="${NOTES:-}"

if [[ "$ACTION" == "--reject" ]]; then
  psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 \
    -v v_reviewer="$REVIEWER" \
    -v v_notes="${NOTES_SAFE:-rejeitado}" \
    -v v_req="$REQUEST_ID" <<'SQL'
UPDATE segportal_connection_request
SET status = 'rejected',
    reviewed_by = :'v_reviewer',
    review_notes = :'v_notes',
    reviewed_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE request_id = :v_req::int AND status = 'pending';
SELECT 'OK: pedido ' || :v_req || ' rejeitado' AS resultado;
SQL
  exit 0
fi

# Busca os dados do pedido via parâmetros (sem eval e sem interpolação).
REQ_ROW=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -At \
  -v v_req="$REQUEST_ID" <<'SQL'
SELECT
  requester_username || E'\t' ||
  replace(connection_name, E'\t', '') || E'\t' ||
  lower(protocol) || E'\t' ||
  hostname || E'\t' ||
  COALESCE(port::text, '0')
FROM segportal_connection_request
WHERE request_id = :v_req::int AND status = 'pending';
SQL
)

if [[ -z "$REQ_ROW" ]]; then
  echo "ERRO: pedido ${REQUEST_ID} não encontrado ou não está pending" >&2
  exit 1
fi

IFS=$'\t' read -r REQ_USER REQ_NAME REQ_PROTO REQ_HOST REQ_PORT <<<"$REQ_ROW"

DEFAULT_PORT=3389
case "$REQ_PROTO" in
  vnc|browser) DEFAULT_PORT=5900; REQ_PROTO=vnc ;;
  ssh) DEFAULT_PORT=22 ;;
  rdp) DEFAULT_PORT=3389 ;;
esac
if [[ "$REQ_PORT" == "0" ]]; then REQ_PORT="$DEFAULT_PORT"; fi

# Entes vêm do banco, mas ainda passam por validação estrita (defesa em profundidade).
for var in REQ_USER REQ_PROTO REQ_HOST; do
  if [[ "${!var}" =~ [^a-zA-Z0-9._-] ]]; then
    echo "ERRO: valor inválido lido do banco ($var)" >&2
    exit 1
  fi
done
if [[ "$REQ_NAME" =~ [^a-zA-Z0-9._ -] ]]; then
  echo "ERRO: nome de conexão inválido lido do banco" >&2
  exit 1
fi
if ! [[ "$REQ_PORT" =~ ^[0-9]+$ ]] || [[ "$REQ_PORT" -lt 1 || "$REQ_PORT" -gt 65535 ]]; then
  echo "ERRO: porta inválida lida do banco" >&2
  exit 1
fi

psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 \
  -v v_req="$REQUEST_ID" \
  -v v_reviewer="$REVIEWER" \
  -v v_notes="${NOTES_SAFE:-aprovado}" \
  -v v_user="$REQ_USER" \
  -v v_name="$REQ_NAME" \
  -v v_proto="$REQ_PROTO" \
  -v v_host="$REQ_HOST" \
  -v v_port="$REQ_PORT" <<'SQL'
BEGIN;

INSERT INTO guacamole_connection (connection_name, protocol, max_connections_per_user)
SELECT :'v_name', :'v_proto', 1
WHERE NOT EXISTS (
  SELECT 1 FROM guacamole_connection WHERE connection_name = :'v_name'
);

INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value)
SELECT c.connection_id, p.n, p.v
FROM guacamole_connection c
CROSS JOIN (VALUES
  ('hostname', :'v_host'),
  ('port', :'v_port')
) AS p(n, v)
WHERE c.connection_name = :'v_name'
  AND NOT EXISTS (
    SELECT 1 FROM guacamole_connection_parameter cp
    WHERE cp.connection_id = c.connection_id AND cp.parameter_name = p.n
  );

-- Garante entidade do usuário
INSERT INTO guacamole_entity (name, type)
SELECT :'v_user', 'USER'
WHERE NOT EXISTS (
  SELECT 1 FROM guacamole_entity WHERE name = :'v_user' AND type = 'USER'
);

INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
SELECT e.entity_id, c.connection_id, 'READ'::guacamole_object_permission_type
FROM guacamole_entity e
JOIN guacamole_connection c ON c.connection_name = :'v_name'
WHERE e.name = :'v_user' AND e.type = 'USER'
  AND NOT EXISTS (
    SELECT 1 FROM guacamole_connection_permission cp
    WHERE cp.entity_id = e.entity_id AND cp.connection_id = c.connection_id
      AND cp.permission = 'READ'::guacamole_object_permission_type
  );

UPDATE segportal_connection_request r
SET status = 'approved',
    reviewed_by = :'v_reviewer',
    review_notes = :'v_notes',
    reviewed_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    guacamole_connection_id = c.connection_id
FROM guacamole_connection c
WHERE r.request_id = :v_req::int
  AND c.connection_name = :'v_name';

COMMIT;
SELECT 'OK: pedido ' || :v_req || ' aprovado — conexão ' || :'v_name' || ' liberada para ' || :'v_user' AS resultado;
SQL