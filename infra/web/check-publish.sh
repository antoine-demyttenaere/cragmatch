#!/usr/bin/env bash
# Checks publish-web.sh with a stub `aws` that keeps the bucket in a temp folder. It needs no network
# and no AWS account. Run by CI (Terraform workflow) and by hand:
#   bash infra/web/check-publish.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
publish="$here/publish-web.sh"

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

bucket=check-bucket-not-real
distribution=EXXXXXXXXXXXXX
api_url=https://api-check.example.test
sha_a="$(printf 'a%.0s' {1..40})"
sha_b="$(printf 'b%.0s' {1..40})"
sha_c="$(printf 'c%.0s' {1..40})"

current_case=""

fail() {
  echo "FAILED: $current_case: $1" >&2
  exit 1
}

pass() {
  echo "ok: $current_case"
}

# --- the stub -------------------------------------------------------------------------------------
# It implements exactly the calls publish-web.sh makes, appends each call to calls.log, and fails on
# purpose when FAKE_AWS_FAIL (a regex) matches the call.
stub_dir="$root/stub"
mkdir -p "$stub_dir"
cat > "$stub_dir/aws" << 'STUB'
#!/usr/bin/env bash
set -euo pipefail
fake="$FAKE_ROOT"
echo "$*" >> "$fake/calls.log"
if [ -n "${FAKE_AWS_FAIL:-}" ] && [[ "$*" =~ $FAKE_AWS_FAIL ]]; then
  echo "stub aws: failing on purpose" >&2
  exit 255
fi

service="$1"
command="$2"
shift 2
positional=()
cache=""
ctype=""
prefix=""
no_overwrite=no
while [ "$#" -gt 0 ]; do
  case "$1" in
    --cache-control) cache="$2"; shift 2 ;;
    --content-type) ctype="$2"; shift 2 ;;
    --prefix) prefix="$2"; shift 2 ;;
    --bucket | --query | --output | --paths | --distribution-id | --id) shift 2 ;;
    --no-overwrite) no_overwrite=yes; shift ;;
    --only-show-errors) shift ;;
    *) positional+=("$1"); shift ;;
  esac
done

# s3://bucket/some/key -> some/key
key_of() { echo "${1#s3://*/}"; }

put() {
  local src="$1" key="$2"
  mkdir -p "$fake/bucket/$(dirname "$key")" "$fake/meta/$(dirname "$key")"
  cp "$src" "$fake/bucket/$key"
  echo "$cache" > "$fake/meta/$key.cache"
  echo "$ctype" > "$fake/meta/$key.type"
}

case "$service $command" in
  "s3 ls")
    [ -f "$fake/bucket/$(key_of "${positional[0]}")" ]
    ;;
  "s3 cp")
    src="${positional[0]}"
    dst="${positional[1]}"
    if [[ "$src" == s3://* ]]; then
      cat "$fake/bucket/$(key_of "$src")"
    else
      put "$src" "$(key_of "$dst")"
    fi
    ;;
  "s3 sync")
    src="${positional[0]}"
    base="$(key_of "${positional[1]}")"
    while IFS= read -r file; do
      rel="${file#"$src"/}"
      if [ "$no_overwrite" = yes ] && [ -f "$fake/bucket/$base/$rel" ]; then
        continue
      fi
      put "$file" "$base/$rel"
      echo "$base/$rel" >> "$fake/uploads.log"
    done < <(find "$src" -type f)
    ;;
  "s3 rm")
    key="$(key_of "${positional[0]}")"
    rm -f "$fake/bucket/$key" "$fake/meta/$key.cache" "$fake/meta/$key.type"
    ;;
  "s3api list-objects-v2")
    keys="$(cd "$fake/bucket" && find "$prefix" -type f 2> /dev/null | tr '\n' '\t' || true)"
    if [ -z "$keys" ]; then
      echo "None"
    else
      echo "$keys"
    fi
    ;;
  "cloudfront create-invalidation")
    echo "INVALIDATION1"
    ;;
  "cloudfront wait")
    ;;
  *)
    echo "stub aws: unexpected call: $service $command" >&2
    exit 99
    ;;
esac
STUB
chmod +x "$stub_dir/aws"

export FAKE_ROOT="$root/fake"
export PATH="$stub_dir:$PATH"

# --- helpers --------------------------------------------------------------------------------------
reset_bucket() {
  rm -rf "$FAKE_ROOT"
  mkdir -p "$FAKE_ROOT/bucket" "$FAKE_ROOT/meta"
  : > "$FAKE_ROOT/calls.log"
  : > "$FAKE_ROOT/uploads.log"
}

# make_dist <name> <sha> <asset names...>: a tiny build. The asset content is its own name, which is
# what a content hash promises. index.html names the API address and the release, so the check can
# tell which release a page belongs to.
make_dist() {
  local name="$1" release="$2"
  shift 2
  local dir="$root/dist-$name"
  rm -rf "$dir"
  mkdir -p "$dir/assets"
  echo "<html><body>$api_url release=$release</body></html>" > "$dir/index.html"
  local asset
  for asset in "$@"; do
    echo "$asset" > "$dir/assets/$asset"
  done
  echo "$dir"
}

# publish <dist> <sha>: runs the script; its output is kept in out.txt, its exit status in $status.
status=0
publish() {
  : > "$FAKE_ROOT/calls.log"
  : > "$FAKE_ROOT/uploads.log"
  status=0
  bash "$publish" "$1" "$bucket" "$distribution" "$2" "$api_url" > "$root/out.txt" 2>&1 || status=$?
}

calls() { cat "$FAKE_ROOT/calls.log"; }
exists() { [ -f "$FAKE_ROOT/bucket/$1" ]; }
first_line() { head -n 1 "$FAKE_ROOT/bucket/$1"; }
line_of() { grep -n -E "$1" "$FAKE_ROOT/calls.log" | head -n 1 | cut -d: -f1; }

# --- cases ----------------------------------------------------------------------------------------
case_first_release() {
  current_case=first_release_uploads_with_the_right_cache_rules
  reset_bucket
  local dist
  dist="$(make_dist a "$sha_a" app-AAA.js app-AAA.css)"
  publish "$dist" "$sha_a"
  [ "$status" -eq 0 ] || fail "the first publish failed: $(cat "$root/out.txt")"

  [ "$(cat "$FAKE_ROOT/meta/assets/app-AAA.js.cache")" = "public, max-age=31536000, immutable" ] \
    || fail "assets must be cached a year and immutable"
  [ "$(cat "$FAKE_ROOT/meta/index.html.cache")" = "no-cache" ] || fail "index.html must be no-cache"
  [ "$(cat "$FAKE_ROOT/meta/index.html.type")" = "text/html; charset=utf-8" ] || fail "index.html needs a text/html type"
  [ "$(first_line release/current.txt)" = "commit $sha_a" ] || fail "current.txt must name the commit"
  grep -qx "assets/app-AAA.js" "$FAKE_ROOT/bucket/release/current.txt" || fail "current.txt must list the js asset"
  grep -qx "assets/app-AAA.css" "$FAKE_ROOT/bucket/release/current.txt" || fail "current.txt must list the css asset"
  ! exists release/previous.txt || fail "a first release has no previous.txt"
  [ "$(calls | grep -c '^cloudfront create-invalidation')" -eq 1 ] || fail "exactly one invalidation"
  calls | grep -q -- '--paths /\*' || fail "the invalidation must be /*"
  [ "$(calls | grep -c '^cloudfront wait invalidation-completed')" -eq 1 ] || fail "the invalidation must be waited for"
  ! calls | grep -q '^s3 rm' || fail "nothing may be deleted by a first release"
  ! grep -qE "$bucket|$distribution|api-check" "$root/out.txt" || fail "the output must not print the bucket, the distribution or the URL"
  grep -q "Live web: $sha_a" "$root/out.txt" || fail "the script must end with Live web"
  pass
}

case_upload_order() {
  current_case=upload_order_never_shows_a_page_before_its_files
  reset_bucket
  publish "$(make_dist a "$sha_a" a1.js shared.woff2)" "$sha_a"
  publish "$(make_dist b "$sha_b" b1.js)" "$sha_b"
  publish "$(make_dist c "$sha_c" c1.js shared.woff2)" "$sha_c"
  [ "$status" -eq 0 ] || fail "the third publish failed"

  local sync page inv wait record rm
  sync="$(line_of '^s3 sync ')"
  page="$(line_of '^s3 cp .*/index\.html s3://')"
  inv="$(line_of '^cloudfront create-invalidation')"
  wait="$(line_of '^cloudfront wait')"
  record="$(line_of '^s3 cp .* s3://[^ ]*/release/current\.txt')"
  rm="$(line_of '^s3 rm ')"
  [ -n "$sync" ] && [ -n "$page" ] && [ -n "$inv" ] && [ -n "$wait" ] && [ -n "$record" ] && [ -n "$rm" ] \
    || fail "a call is missing from the log (sync=$sync page=$page inv=$inv wait=$wait record=$record rm=$rm)"
  [ "$sync" -lt "$page" ] || fail "assets must be uploaded before index.html"
  [ "$page" -lt "$inv" ] || fail "index.html must be uploaded before the invalidation"
  [ "$inv" -lt "$wait" ] || fail "the wait must follow the invalidation"
  [ "$wait" -lt "$record" ] || fail "the release is recorded after the invalidation finished"
  [ "$record" -lt "$rm" ] || fail "nothing is deleted before the release is recorded"
  pass
}

case_previous_release_survives() {
  current_case=previous_release_assets_survive_and_older_ones_go
  reset_bucket
  publish "$(make_dist a "$sha_a" a1.js shared.woff2)" "$sha_a"
  publish "$(make_dist b "$sha_b" b1.js)" "$sha_b"
  exists assets/a1.js || fail "A's assets must survive while B is current (A is the previous release)"
  publish "$(make_dist c "$sha_c" c1.js shared.woff2)" "$sha_c"
  [ "$status" -eq 0 ] || fail "publishing C failed"

  exists assets/b1.js || fail "B's asset (the previous release) must exist"
  exists assets/c1.js || fail "C's asset must exist"
  ! exists assets/a1.js || fail "A's own asset must be gone"
  exists assets/shared.woff2 || fail "an asset shared by A and C must stay"
  [ "$(first_line release/previous.txt)" = "commit $sha_b" ] || fail "previous.txt must be B"
  pass
}

case_rerun() {
  current_case=rerun_of_the_same_commit_changes_nothing
  reset_bucket
  publish "$(make_dist a "$sha_a" a1.js)" "$sha_a"
  publish "$(make_dist b "$sha_b" b1.js)" "$sha_b"
  publish "$(make_dist c "$sha_c" c1.js)" "$sha_c"
  publish "$(make_dist c "$sha_c" c1.js)" "$sha_c"
  [ "$status" -eq 0 ] || fail "the re-run failed"

  [ ! -s "$FAKE_ROOT/uploads.log" ] || fail "a re-run must upload no asset"
  ! calls | grep -q '^s3 rm' || fail "a re-run must delete nothing"
  [ "$(first_line release/previous.txt)" = "commit $sha_b" ] || fail "previous.txt must stay B"
  [ "$(first_line release/current.txt)" = "commit $sha_c" ] || fail "current.txt must stay C"
  pass
}

case_bundle_check() {
  current_case=a_bundle_with_a_key_or_without_the_api_address_is_not_published
  reset_bucket
  local dist
  dist="$(make_dist key "$sha_a" app.js)"
  echo 'const k = "sk-ant-x";' >> "$dist/assets/app.js"
  publish "$dist" "$sha_a"
  [ "$status" -ne 0 ] || fail "a bundle with a key was published"
  grep -q "Bundle check failed" "$root/out.txt" || fail "the key case must say Bundle check failed"
  [ ! -s "$FAKE_ROOT/calls.log" ] || fail "the key case must not call aws"

  dist="$(make_dist noapi "$sha_a" app.js)"
  echo "<html><body>no address here</body></html>" > "$dist/index.html"
  publish "$dist" "$sha_a"
  [ "$status" -ne 0 ] || fail "a bundle without the API address was published"
  grep -q "Bundle check failed" "$root/out.txt" || fail "the missing address case must say Bundle check failed"
  [ ! -s "$FAKE_ROOT/calls.log" ] || fail "the missing address case must not call aws"
  pass
}

case_failed_upload() {
  current_case=a_failed_upload_leaves_the_previous_version_live
  reset_bucket
  publish "$(make_dist a "$sha_a" a1.js)" "$sha_a"
  publish "$(make_dist b "$sha_b" b1.js)" "$sha_b"
  local before
  before="$(cat "$FAKE_ROOT/bucket/index.html")"

  FAKE_AWS_FAIL='^s3 cp .*/index\.html s3://' publish "$(make_dist c "$sha_c" c1.js)" "$sha_c"
  [ "$status" -ne 0 ] || fail "the publish must fail when the page upload fails"
  [ "$(cat "$FAKE_ROOT/bucket/index.html")" = "$before" ] || fail "index.html must still be B's"
  grep -q "release=$sha_b" "$FAKE_ROOT/bucket/index.html" || fail "index.html must belong to B"
  [ "$(first_line release/current.txt)" = "commit $sha_b" ] || fail "current.txt must still be B"
  ! calls | grep -q '^s3 rm' || fail "nothing may be deleted after a failure"
  ! calls | grep -q '^cloudfront' || fail "no invalidation after a failed upload"
  pass
}

case_first_release
case_upload_order
case_previous_release_survives
case_rerun
case_bundle_check
case_failed_upload
