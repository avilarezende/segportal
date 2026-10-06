FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEMO_SHARES_ROOT=/data/shares \
    PORTAL_PORT=8090

COPY services/portal-auth/requirements.lock /app/requirements.lock
RUN --mount=type=secret,id=egress_ca \
    if [ -f /run/secrets/egress_ca ]; then export PIP_CERT=/run/secrets/egress_ca; fi; \
    pip install --no-cache-dir --require-hashes -r /app/requirements.lock

COPY config /app/config
COPY services/portal-auth /app/services/portal-auth

# Executa como usuário não-root (OWASP: menor privilégio em contêineres).
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin portal \
    && mkdir -p /data/shares \
    && chown -R portal:portal /data/shares /app

WORKDIR /app/services/portal-auth
USER portal
EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
