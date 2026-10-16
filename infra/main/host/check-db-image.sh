#!/usr/bin/env bash
# Builds the cloud database image and checks what the acceptance criteria promise: both
# extensions exist after the first start, TCP works only over TLS, and there are enough
# connections for the backend. Run by CI (db-image job) and by hand with Docker running:
#   bash infra/main/host/check-db-image.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
image=cragmatch-db:check
container=cragmatch-db-check
tls_volume=cragmatch-db-check-tls
password=check-only-not-a-secret

cleanup() {
  docker rm -f "$container" > /dev/null 2>&1 || true
  docker volume rm "$tls_volume" > /dev/null 2>&1 || true
}
trap cleanup EXIT

fail() {
  echo "FAILED: $1" >&2
  exit 1
}

# Always over TCP and TLS, like the backend will connect.
psql_in_container() {
  docker exec -e PGPASSWORD="$password" -e PGSSLMODE=require "$container" \
    psql -h 127.0.0.1 -U cragmatch -d cragmatch -v ON_ERROR_STOP=1 -tA "$@"
}

echo "1. Build the image"
docker build -t "$image" "$here/db"

echo "2. Generate a throwaway certificate (same openssl line as host-setup.sh)"
# A volume, not a bind mount: the key must belong to uid 999 with mode 600, which a host folder
# cannot guarantee on every OS.
cleanup
docker volume create "$tls_volume" > /dev/null
docker run --rm -v "$tls_volume":/tls --entrypoint bash "$image" -c '
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=db" \
    -addext "subjectAltName=DNS:db,DNS:localhost,IP:127.0.0.1" \
    -keyout /tls/server.key -out /tls/server.crt 2> /dev/null
  chown 999:999 /tls/server.key /tls/server.crt
  chmod 600 /tls/server.key
  chmod 644 /tls/server.crt'

echo "3. Start the database"
docker run -d --name "$container" \
  -e POSTGRES_USER=cragmatch -e POSTGRES_DB=cragmatch -e POSTGRES_PASSWORD="$password" \
  -v "$tls_volume":/tls:ro "$image" > /dev/null

echo "4. Wait until it is ready"
# -h 127.0.0.1: during first-start init the image runs a temporary server on the Unix socket
# only, so a socket check can say ready too early.
timeout 120 bash -c "until docker exec $container pg_isready -h 127.0.0.1 -U cragmatch -d cragmatch > /dev/null 2>&1; do sleep 1; done" \
  || { docker logs "$container" >&2; fail "the database did not become ready"; }

echo "5. Extensions"
extensions="$(psql_in_container -c "select extname from pg_extension order by 1" 2> /dev/null || true)"
echo "$extensions" | grep -qx postgis || fail "postgis is not created after init"
echo "$extensions" | grep -qx vector || fail "vector is not created after init"

echo "6. TCP without TLS is refused"
if docker exec -e PGPASSWORD="$password" -e PGSSLMODE=disable "$container" \
  psql -h 127.0.0.1 -U cragmatch -d cragmatch -tA -c "select 1" > /dev/null 2>&1; then
  fail "a connection with sslmode=disable was accepted"
fi

echo "7. TCP with TLS connects and really uses TLS"
ssl="$(psql_in_container -c "select ssl from pg_stat_ssl where pid = pg_backend_pid()")" \
  || fail "sslmode=require did not connect"
[ "$ssl" = "t" ] || fail "the connection is not encrypted (pg_stat_ssl.ssl = $ssl)"

echo "8. Connection limit"
max_connections="$(psql_in_container -c "show max_connections")"
[ "$max_connections" -ge 50 ] || fail "max_connections is $max_connections, the backend needs about 38"

echo "OK: extensions, TLS-only TCP and connection limit"
