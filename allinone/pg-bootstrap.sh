#!/bin/bash
# One-shot PostgreSQL bootstrap for the all-in-one container (PGDG PG16).
#
# Local connections are trust-authenticated (the reused volume's
# pg_hba.conf and the fresh initdb both use --auth-local=trust), so psql
# connects directly without su.
#
# Two cases, both handled by probing which role can connect:
#  1. Reused data volume: the app user (POSTGRES_USER, default octoagent)
#     is the bootstrap superuser and the postgres role does not exist.
#  2. Fresh volume (initdb by the postgres OS user): the postgres role is
#     the superuser and the app role/db are created here.
# Idempotent: on an existing volume everything is a no-op except keeping
# the app role password in sync with the environment.
#
# NOTE: no psql :variable substitution is used (it does not survive
# multi-layer shell quoting); the password is interpolated by bash.
# POSTGRES_PASSWORD in this deployment is a 48-hex-char string, which is
# safe inside single quotes.
set -euo pipefail

PG_BIN_DIR=/usr/lib/postgresql/16/bin
PG_USER="${POSTGRES_USER:-octoagent}"
PG_DB="${POSTGRES_DB:-octoagent}"
PG_PASSWORD="${POSTGRES_PASSWORD:-octoagent}"

for _ in $(seq 1 90); do
    if "${PG_BIN_DIR}/pg_isready" -q -t 2 -U "${PG_USER}" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ! "${PG_BIN_DIR}/pg_isready" -q -t 2 -U "${PG_USER}" >/dev/null 2>&1; then
    echo "[pg-bootstrap] ERROR: postgres did not become ready in time" >&2
    exit 1
fi

# Pick the usable superuser: the app user when it already exists
# (reused volume), otherwise the postgres role (fresh initdb).
if psql -U "${PG_USER}" -d "${PG_DB}" -tAc 'SELECT 1' >/dev/null 2>&1; then
    BOOT_USER=${PG_USER}
    echo "[pg-bootstrap] bootstrapping as app superuser '${PG_USER}'"
else
    BOOT_USER=postgres
    echo "[pg-bootstrap] bootstrapping as postgres role (fresh volume)"
fi

role_exists() {
    psql -U "${BOOT_USER}" -d postgres -tAc \
        "SELECT 1 FROM pg_roles WHERE rolname='${PG_USER}'" | grep -q 1
}

if role_exists; then
    echo "[pg-bootstrap] role '${PG_USER}' exists; syncing password"
    psql -U "${BOOT_USER}" -d postgres -v ON_ERROR_STOP=1 \
        -c "ALTER ROLE ${PG_USER} LOGIN PASSWORD '${PG_PASSWORD}'"
else
    echo "[pg-bootstrap] creating role '${PG_USER}'"
    psql -U "${BOOT_USER}" -d postgres -v ON_ERROR_STOP=1 \
        -c "CREATE ROLE ${PG_USER} SUPERUSER LOGIN PASSWORD '${PG_PASSWORD}'"
fi

if ! psql -U "${BOOT_USER}" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${PG_DB}'" | grep -q 1; then
    echo "[pg-bootstrap] creating database '${PG_DB}'"
    psql -U "${BOOT_USER}" -d postgres -v ON_ERROR_STOP=1 \
        -c "CREATE DATABASE ${PG_DB} OWNER ${PG_USER}"
fi

psql -U "${BOOT_USER}" -d "${PG_DB}" -v ON_ERROR_STOP=1 \
    -c "CREATE EXTENSION IF NOT EXISTS vector"

echo "[pg-bootstrap] bootstrap complete"