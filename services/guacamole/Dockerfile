# SegPortal TJSE — Guacamole web application
# Build context: repository root (docker-compose / CI)
ARG GUACAMOLE_VERSION=1.5.5

FROM guacamole/guacamole:${GUACAMOLE_VERSION}

USER root

# Re-declare build args for use in RUN (ARG before FROM is not available here)
ARG GUACAMOLE_VERSION=1.5.5
ARG LDAP_EXTENSION_VERSION=1.5.5
ARG GUACAMOLE_BINARY_BASE=https://dlcdn.apache.org/guacamole

# gettext-base provides envsubst, used by entrypoint.sh to render guacamole.properties
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base \
    && rm -rf /var/lib/apt/lists/*

# The guacamole/guacamole base image already bundles the LDAP auth extension
# (/opt/guacamole/ldap/guacamole-auth-ldap-${LDAP_EXTENSION_VERSION}.jar) and
# auto-enables it at runtime whenever LDAP_* variables are set. Installing the
# jar again into GUACAMOLE_HOME/extensions makes start.sh try to link two copies
# under the same name ("File exists" -> crash loop), so we only pin/verify that
# the released extension archive matches the version we build against.
RUN mkdir -p /tmp/guac-ext \
    && curl -fsSL \
      "${GUACAMOLE_BINARY_BASE}/${GUACAMOLE_VERSION}/binary/guacamole-auth-ldap-${LDAP_EXTENSION_VERSION}.tar.gz" \
      -o /tmp/guac-ext/ldap.tar.gz \
    && tar -tzf /tmp/guac-ext/ldap.tar.gz \
      | grep -q "guacamole-auth-ldap-${LDAP_EXTENSION_VERSION}.jar" \
    && rm -rf /tmp/guac-ext

# TJSE branding and configuration
COPY config/guacamole/guacamole.properties /etc/guacamole/guacamole.properties.template
COPY services/guacamole/branding/ /etc/guacamole/branding/
COPY services/guacamole/entrypoint.sh /opt/segportal/entrypoint.sh

RUN chmod +x /opt/segportal/entrypoint.sh \
    && chown -R guacamole:guacamole /etc/guacamole

USER guacamole

ENV GUACAMOLE_HOME=/etc/guacamole
EXPOSE 8080

ENTRYPOINT ["/opt/segportal/entrypoint.sh"]
CMD ["/opt/guacamole/bin/start.sh", "--foreground"]
