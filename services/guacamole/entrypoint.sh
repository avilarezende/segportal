#!/bin/sh
set -eu

GUACAMOLE_HOME="${GUACAMOLE_HOME:-/etc/guacamole}"
TEMPLATE="${GUACAMOLE_HOME}/guacamole.properties.template"
TARGET="${GUACAMOLE_HOME}/guacamole.properties"

# envsubst has no default-value syntax (${VAR:default} is left untouched), so
# provide defaults for optional variables here and reference plain ${VAR} in the
# template. Required variables (POSTGRES_PASSWORD, LDAP_*) come from the runtime
# environment and are read by envsubst directly.
: "${POSTGRES_HOSTNAME:=postgres}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:=guacamole_db}"
: "${POSTGRES_USER:=guacamole_user}"
: "${SESSION_TIMEOUT_MINUTES:=60}"
: "${MAX_CONCURRENT_CONNECTIONS:=3}"
: "${LDAP_PORT:=636}"
: "${LDAP_ENCRYPTION_METHOD:=ssl}"
: "${LDAP_USERNAME_ATTRIBUTE:=sAMAccountName}"
: "${MFA_RADIUS_HOST:=}"
: "${MFA_RADIUS_PORT:=1812}"
: "${MFA_RADIUS_SECRET:=}"
: "${EGRESS_PROXY_HOST:=proxy-egress}"
: "${EGRESS_PROXY_PORT:=3128}"
: "${GUACD_HOSTNAME:=guacd}"
: "${GUACD_PORT:=4822}"
export POSTGRES_HOSTNAME POSTGRES_PORT POSTGRES_DB POSTGRES_USER \
  SESSION_TIMEOUT_MINUTES MAX_CONCURRENT_CONNECTIONS \
  LDAP_PORT LDAP_ENCRYPTION_METHOD LDAP_USERNAME_ATTRIBUTE \
  MFA_RADIUS_HOST MFA_RADIUS_PORT MFA_RADIUS_SECRET \
  EGRESS_PROXY_HOST EGRESS_PROXY_PORT GUACD_HOSTNAME GUACD_PORT

# The upstream Guacamole image only installs the PostgreSQL JDBC auth extension
# when POSTGRESQL_DATABASE is set (its POSTGRES_* compatibility shim maps
# POSTGRES_DATABASE, not the POSTGRES_DB name used by the Postgres image and our
# compose file). Export the canonical POSTGRESQL_* names so start.sh loads and
# wires the extension; without it only LDAP loads and database users (guacadmin)
# cannot authenticate.
export POSTGRESQL_HOSTNAME="$POSTGRES_HOSTNAME"
export POSTGRESQL_PORT="$POSTGRES_PORT"
export POSTGRESQL_DATABASE="$POSTGRES_DB"
export POSTGRESQL_USER="$POSTGRES_USER"
export POSTGRESQL_PASSWORD="${POSTGRES_PASSWORD:-}"

# Render guacamole.properties from template with environment substitution
if [ -f "$TEMPLATE" ]; then
  envsubst < "$TEMPLATE" > "$TARGET"
fi

# Optional MFA: remove RADIUS settings when disabled
if [ "${MFA_ENABLED:-true}" != "true" ]; then
  sed -i '/^radius-/d' "$TARGET" 2>/dev/null || true
fi

exec "$@"
