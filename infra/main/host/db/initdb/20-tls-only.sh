#!/usr/bin/env bash
# Runs once, after the image has written pg_hba.conf. Every TCP rule becomes hostssl, so the
# server itself refuses a connection without TLS (not only a client setting). The local socket
# lines stay, for `docker exec ... psql`.
set -euo pipefail

sed -i 's/^host\([[:space:]]\)/hostssl\1/' "$PGDATA/pg_hba.conf"

grep -q '^hostssl' "$PGDATA/pg_hba.conf"
if grep -q '^host[[:space:]]' "$PGDATA/pg_hba.conf"; then
  echo "pg_hba.conf still has a non-TLS TCP rule" >&2
  exit 1
fi
