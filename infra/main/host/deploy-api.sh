#!/usr/bin/env bash
# Usage: deploy-api.sh <40-character commit sha> <yes|no>
# Run as root by the SSM document cragmatch-deploy-api. The second argument says whether to apply the
# Alembic migrations first (no for a rollback: an older image does not know a newer revision).
# The output goes to a public workflow log: print commit SHAs and statuses only, no addresses.
# Never add `set -x` here.
set -euo pipefail

sha="${1:-}"
run_migrations="${2:-}"

# The document checks the SHA too; the script does not rely on it.
if ! [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "The first argument must be a 40-character commit sha" >&2
  exit 1
fi
if [ "$run_migrations" != "yes" ] && [ "$run_migrations" != "no" ]; then
  echo "The second argument must be yes or no" >&2
  exit 1
fi

# REGION and ECR_REPOSITORY_URL.
# shellcheck source=/dev/null
source /opt/cragmatch/host-settings

API_DIR=/srv/cragmatch/api
CURRENT="$API_DIR/current-image"
PREVIOUS="$API_DIR/previous-image"
image="$ECR_REPOSITORY_URL:$sha"

# Polls /health on the host (not through CloudFront) until the database answers, or gives up.
wait_healthy() {
  local deadline=$((SECONDS + $1)) body
  while [ "$SECONDS" -lt "$deadline" ]; do
    # A variable and not a pipe into grep -q: grep exits early and pipefail would turn curl's
    # broken pipe into a failure.
    body="$(curl -fsS --max-time 5 http://127.0.0.1/health 2> /dev/null || true)"
    if [[ "$body" == *'"database":"connected"'* ]]; then
      return 0
    fi
    sleep 3
  done
  return 1
}

# Written beside the target and moved into place, so a reader never sees half a line.
write_image_file() {
  local target="$1" line="$2" tmp
  tmp="$(mktemp "$target.XXXXXX")"
  printf '%s\n' "$line" > "$tmp"
  chmod 644 "$tmp"
  mv "$tmp" "$target"
}

echo "== directories"
install -d -m 0755 "$API_DIR"
# The Hugging Face cache belongs to the image's user (uid 10001).
install -d -m 0755 -o 10001 -g 10001 /srv/cragmatch/hf

echo "== pull"
/opt/cragmatch/pull-api-image.sh "$image"

echo "== environment"
/opt/cragmatch/render-api-environment.sh

if [ "$run_migrations" = "yes" ]; then
  # Before the restart: the old container keeps serving while this runs, so a failed migration
  # leaves the old version live and the deploy red. Each migration must therefore work with the
  # code before it. Postgres DDL is transactional, so a failure leaves no half-applied schema.
  echo "== migrations"
  if ! docker run --rm --network cragmatch --env-file /etc/cragmatch/api-environment \
    -v /srv/cragmatch/pgtls/server.crt:/tls/server.crt:ro "$image" alembic upgrade head; then
    echo "Migration failed: the previous version keeps serving" >&2
    exit 1
  fi
else
  echo "== migrations skipped"
fi

echo "== restart"
old_line=""
if [ -f "$CURRENT" ]; then
  old_line="$(cat "$CURRENT")"
fi
write_image_file "$CURRENT" "API_IMAGE=$image"
systemctl restart cragmatch-api

echo "== health"
healthy=no
if wait_healthy 120; then
  # The second call builds the trip planner, which creates or checks the planner's tables now, with
  # no other transaction open (PostgresSaver.setup() waits for open transactions).
  if curl -fsS --max-time 60 http://127.0.0.1/planner/graph > /dev/null; then
    healthy=yes
  fi
fi

if [ "$healthy" = "no" ]; then
  echo "The new version is not healthy; last log lines:" >&2
  # Only the container's stderr (tracebacks, startup errors): access lines are on stdout and carry
  # client addresses, which must not reach the public workflow log.
  { docker logs --tail 80 api 2>&1 > /dev/null; } >&2 || true
  if [ -n "$old_line" ]; then
    write_image_file "$CURRENT" "$old_line"
    systemctl restart cragmatch-api
    wait_healthy 120 || echo "The previous version is not healthy either" >&2
    echo "Returned to ${old_line##*:}; the migration was not undone" >&2
  else
    # Nothing to return to: stay quiet instead of crash-looping until someone fixes it.
    rm -f "$CURRENT"
    systemctl stop cragmatch-api
    echo "There was no previous version; the API is stopped" >&2
  fi
  exit 1
fi

echo "== finish"
if [ -n "$old_line" ]; then
  write_image_file "$PREVIOUS" "$old_line"
fi
# Only API images that no container uses; a rollback pulls the image again from ECR if needed.
docker image prune -af --filter label=cragmatch.component=api > /dev/null
echo "Live: $sha"
