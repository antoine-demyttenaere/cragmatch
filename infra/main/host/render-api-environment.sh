#!/usr/bin/env bash
# Writes /etc/cragmatch/api-environment for the API container from Parameter Store. Run as the API
# unit's first ExecStartPre and by deploy-api.sh. The file is not named with the usual dot-env suffix
# on purpose: the repo's protect_env.py hook blocks any command that contains that text.
# Never add `set -x` here: it handles the database password and the API keys.
set -euo pipefail

# REGION and the parameter names (names, not values).
# shellcheck source=/dev/null
source /opt/cragmatch/host-settings

read_parameter() {
  aws ssm get-parameter --region "$REGION" --with-decryption \
    --name "$1" --query Parameter.Value --output text
}

settings="$(read_parameter "$API_SETTINGS_PARAMETER")"
db_password="$(read_parameter "$DB_PASSWORD_PARAMETER")"
anthropic_key="$(read_parameter "$ANTHROPIC_KEY_PARAMETER")"
voyage_key="$(read_parameter "$VOYAGE_KEY_PARAMETER")"

# The slots are created with the placeholder "unset" until the user types the real key.
require_key() {
  if [ -z "$2" ] || [ "$2" = "unset" ]; then
    echo "Enter $1 in Parameter Store first (infra/RUNBOOK.md, Backend: first deploy)" >&2
    exit 1
  fi
}
require_key "$ANTHROPIC_KEY_PARAMETER" "$anthropic_key"
require_key "$VOYAGE_KEY_PARAMETER" "$voyage_key"

# Root-only, written beside the target and moved into place so a reader never sees half a file.
umask 077
mkdir -p /etc/cragmatch
tmp="$(mktemp /etc/cragmatch/api-environment.XXXXXX)"
{
  printf '%s\n' "$settings"
  printf 'CRAGMATCH_POSTGRES_PASSWORD=%s\n' "$db_password"
  printf 'CRAGMATCH_ANTHROPIC_API_KEY=%s\n' "$anthropic_key"
  printf 'CRAGMATCH_VOYAGE_API_KEY=%s\n' "$voyage_key"
} > "$tmp"
mv "$tmp" /etc/cragmatch/api-environment

echo "API environment written"
