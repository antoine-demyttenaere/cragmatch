#!/usr/bin/env bash
# Publishes web/dist to the private site bucket, in an order that never shows a page before its files:
# new assets, then index.html, then one invalidation, then the release record, then pruning.
# Each deploy keeps the assets of the new and the previous release, so a visitor with the previous
# version open can still load its lazily fetched files. Never let sync delete files here.
#
# Usage: publish-web.sh <dist> <bucket> <distribution-id> <sha> <api-url>
#
# The Deploy logs are public: this script prints step names only, never the bucket, the distribution
# id or the URL.
set -euo pipefail

if [ "$#" -ne 5 ]; then
  echo "Usage: publish-web.sh <dist> <bucket> <distribution-id> <sha> <api-url>" >&2
  exit 2
fi
dist="$1"
bucket="$2"
distribution_id="$3"
sha="$4"
api_url="$5"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fail() {
  echo "FAILED: $1" >&2
  exit 1
}

# aws s3 ls exits 1 when nothing matches and 255 on a real error (permissions, network). Only the
# first means "not there"; treating an error as "first release" would shorten the history and prune
# files that are still live.
object_exists() {
  local status=0
  aws s3 ls "s3://$bucket/$1" > /dev/null 2>&1 || status=$?
  case "$status" in
    0) return 0 ;;
    1) return 1 ;;
    *) fail "could not look for $1 in the bucket" ;;
  esac
}

echo "== arguments"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "the commit must be a 40-character SHA"
[ -f "$dist/index.html" ] || fail "$dist/index.html does not exist"
[ -d "$dist/assets" ] || fail "$dist/assets does not exist"

echo "== bundle check"
if ! grep -rqF -- "$api_url" "$dist"; then
  echo "Bundle check failed: the API address is not in the build" >&2
  exit 1
fi
if grep -rqE "sk-ant-|CRAGMATCH_|BEGIN [A-Z ]*PRIVATE KEY" "$dist"; then
  echo "Bundle check failed: the build contains something that looks like a key" >&2
  exit 1
fi
if [ -n "$(find "$dist" -name '*.map' -print -quit)" ]; then
  echo "Bundle check failed: the build contains source maps" >&2
  exit 1
fi

echo "== last release"
old_current="$work/old-current.txt"
old_previous="$work/old-previous.txt"
: > "$old_current"
: > "$old_previous"
old_commit=""
if object_exists release/current.txt; then
  aws s3 cp "s3://$bucket/release/current.txt" - > "$old_current"
  old_commit="$(head -n 1 "$old_current" | cut -d ' ' -f 2)"
fi
if object_exists release/previous.txt; then
  aws s3 cp "s3://$bucket/release/previous.txt" - > "$old_previous"
fi

echo "== assets"
# Same name means same bytes (Vite hashes the content), so an existing object is never rewritten.
aws s3 sync "$dist/assets" "s3://$bucket/assets" --no-overwrite --only-show-errors \
  --cache-control "public, max-age=31536000, immutable"

echo "== page"
# Only after every asset it names exists.
aws s3 cp "$dist/index.html" "s3://$bucket/index.html" --cache-control no-cache \
  --content-type "text/html; charset=utf-8" --only-show-errors

echo "== invalidation"
invalidation_id="$(aws cloudfront create-invalidation --distribution-id "$distribution_id" \
  --paths "/*" --query Invalidation.Id --output text)"
aws cloudfront wait invalidation-completed --distribution-id "$distribution_id" --id "$invalidation_id"

echo "== release record"
new_current="$work/new-current.txt"
{
  printf 'commit %s\n' "$sha"
  (cd "$dist" && find assets -type f -print | LC_ALL=C sort)
} > "$new_current"

# The history to keep after this release. A re-run of the same commit keeps the old previous.txt, so
# a re-run never shortens the history.
keep_previous="$old_previous"
if [ -n "$old_commit" ] && [ "$old_commit" != "$sha" ]; then
  keep_previous="$old_current"
  aws s3 cp "$old_current" "s3://$bucket/release/previous.txt" --cache-control no-cache --only-show-errors
fi
aws s3 cp "$new_current" "s3://$bucket/release/current.txt" --cache-control no-cache --only-show-errors

echo "== prune"
# Only now, after the invalidation: nothing is deleted before the new version is live.
keep="$work/keep.txt"
{
  grep '^assets/' "$new_current" || true
  grep '^assets/' "$keep_previous" || true
} | LC_ALL=C sort -u > "$keep"

listed="$work/listed.txt"
aws s3api list-objects-v2 --bucket "$bucket" --prefix assets/ --query "Contents[].Key" \
  --output text | tr '\t' '\n' > "$listed"

removed=0
while IFS= read -r key; do
  # An empty bucket prints "None" with --output text.
  if [ -z "$key" ] || [ "$key" = "None" ]; then
    continue
  fi
  if ! grep -qxF -- "$key" "$keep"; then
    aws s3 rm "s3://$bucket/$key" --only-show-errors
    removed=$((removed + 1))
  fi
done < "$listed"
echo "Pruned $removed old asset(s)"

echo "Live web: $sha"
