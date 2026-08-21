#!/bin/bash
# OctoAgent all-in-one entrypoint.
# Prepares the bundled PostgreSQL 16 (PGDG) data directory:
#   - reuses the existing /var/lib/postgresql/data volume (same PG16 format)
#   - initdb only when the volume is empty
# then hands off to supervisord which runs the five processes:
#   pg-bootstrap (one-shot) -> postgres -> system-executor -> app-server -> frontend -> nginx
set -euo pipefail

PG_BIN_DIR=/usr/lib/postgresql/16/bin
PG_DATA=/var/lib/postgresql/data
PGCONF=${PG_DATA}/postgresql.conf

install -d -o postgres -g postgres -m 0700 "${PG_DATA}"
mkdir -p /var/run/postgresql && chown postgres:postgres /var/run/postgresql

if [ ! -s "${PG_DATA}/PG_VERSION" ]; then
    echo "[entrypoint] fresh volume: running initdb"
    su -s /bin/bash postgres -c "${PG_BIN_DIR}/initdb -D ${PG_DATA} --auth-local=trust --auth-host=scram-sha-256"
else
    echo "[entrypoint] reusing existing PG$(cat "${PG_DATA}/PG_VERSION") data directory"
fi

# Runtime overrides (idempotent, marker-guarded).
if ! grep -q "octoagent all-in-one runtime overrides" "${PGCONF}" 2>/dev/null; then
    cat >> "${PGCONF}" <<'EOF'

# ---- octoagent all-in-one runtime overrides ----
listen_addresses = '127.0.0.1'
port = 5432
unix_socket_directories = '/var/run/postgresql'
EOF
fi

if [ ! -s "${PG_DATA}/PG_VERSION" ]; then
    echo "[entrypoint] ERROR: no PostgreSQL cluster present" >&2
    exit 1
fi

# Remove a stale postmaster.pid left behind if the previous postmaster did
# not exit cleanly. It is safe inside this container: only the postgres
# program we start can ever hold that pid file, and no postgres process is
# running at entrypoint time.
if [ -f "${PG_DATA}/postmaster.pid" ]; then
    echo "[entrypoint] removing stale postmaster.pid"
    rm -f "${PG_DATA}/postmaster.pid"
fi

# Render the nginx configuration from its template. Only variables that are
# defined in the environment get substituted, so nginx runtime variables
# ($host, $scheme, ...) are preserved.
echo "[entrypoint] rendering /etc/nginx/nginx.allinone.conf"
envsubst "$(env | cut -d= -f1 | sed -e 's/^/\$/g' | tr '\n' ' ')" \
    < /etc/nginx/templates/nginx.allinone.conf.template \
    > /etc/nginx/nginx.allinone.conf

echo "[entrypoint] starting supervisord"
exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf