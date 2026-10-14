# Plan for 026: Deploy on AWS, part 3: the web app online and the deploy pipeline

**Ticket:** `tickets/026-frontend-on-aws-and-deploy-pipeline.md`
**Approach:** `web/dist` is served from a **private S3 bucket behind a second CloudFront distribution**,
`aws_cloudfront_distribution.web`. It uses origin access control, the default `*.cloudfront.net` certificate,
HTTPS only, the SPA fallback to `/index.html` as a custom error response, the managed `CachingOptimized`
policy and our own security headers. Terraform creates the site and the API's allowed origin in **one
apply**, because neither distribution depends on the other's settings. A new `web` job in 025's `Deploy`
workflow (`needs: backend`) builds `web/` with `VITE_API_URL` read from `/cragmatch/deploy/api_url`, and
`infra/web/publish-web.sh` publishes it in a fixed order:
1. check that the bundle holds no key;
2. upload the new hashed assets without overwriting or deleting anything;
3. upload `index.html` with `no-cache`;
4. invalidate `/*` and wait for it;
5. record the release;
6. only then prune the assets that neither the new release nor the one before it uses.

Assumed delivered first, as their plans describe: 017 to 025. In particular:
- 021: `web/src/api/client.ts` reads `import.meta.env.VITE_API_URL`, and `CRAGMATCH_CORS_ORIGINS` is a
  comma list;
- 024: `infra/`, its toolchain, `jsonencode` policies, mocked `terraform test`, tflint's `Project` tag rule,
  the `Terraform` workflow, and the deploy role `cragmatch-github-deploy` trusted only for `main`;
- 025: `aws_cloudfront_distribution.api`, `/cragmatch/deploy/api_url`, the `Deploy` workflow with job
  `backend`, `ReadDeployParameters` on `/cragmatch/deploy/*`, and runbook sections 1 to 23.

**No application code changes** (`backend/app`, `web/src`, `ci.yml` untouched).

**Alternatives considered:**
- *S3 website endpoint:* HTTP only, and the bucket must be public, which 024's account-level public access
  block forbids. Out.
- *Amplify Hosting:* 0.15 USD per GB served and 0.01 USD per build minute in eu-west-1 (price list
  2026-09-11), with no free allowance. It also adds a second build pipeline and its own CDN beside GitHub
  Actions. CloudFront plus S3 costs 0 within the free allowance and keeps the cache rules in our Terraform.
  Out.
- *SPA fallback as a CloudFront Function* (it rewrites paths without an extension to `/index.html`): more
  precise, because a missing asset would stay a real 403. But it is JavaScript to write and test, and it
  runs on every request (2 M a month free, then 0.10 USD per million). The share link is `/?group=CODE` on
  the root (017), so the fallback only serves mistyped paths. The pruning rule below keeps missing assets
  rare. Custom error responses are pure Terraform and testable offline. Chosen.
- *One distribution for the site and the API:* 025 already decided against it (the prefix would need
  stripping, and the two lifecycles would mix). Kept as two.
- *`aws s3 sync --delete`:* it removes the previous release's assets in the same step that uploads the new
  ones. A visitor whose open page later loads an old font subset or chunk would get `index.html` instead
  (AC 3). Out. Replaced by "keep the current and the previous release, prune older".
- *Assets expired by an S3 lifecycle rule (age):* every deploy re-uploads nothing (we use `--no-overwrite`),
  so age says nothing about use. A long-lived release would lose its own assets. Out.
- *Two-stage apply, or a fixed origin, to break the address cycle:* not needed. In Terraform the cycle does
  not exist: the API settings parameter depends on the web distribution, and the web CSP depends on the API
  distribution. Neither distribution depends on a parameter. So one apply knows both addresses.
- *Deploy only what changed (path filters per job):* the ticket's default is "both every time". It is
  simpler and predictable, and a backend run with an unchanged image is fast (layer cache). Kept simple
  (AC 8).

## Up front: decisions with costs and sources
Prices are in USD for eu-west-1, fetched on **2026-10-14**. EUR is at 024's ECB rate (1 EUR = 1.1188 USD).

### Cost delta (AC 11)
| What 026 adds | USD a month | Why |
|---|---|---|
| S3 Standard storage for the site | about 0.00003 | 0.023 per GB-month. Two releases of `dist/` are about 0.7 MB (today's build is 0.32 MB; dagre from 020 adds some tens of kB). |
| S3 PUT and LIST from deploys | about 0.002 | 0.005 per 1,000. About 15 requests per deploy, 30 deploys a month. DELETE is free. |
| S3 GET from CloudFront | about 0.002 | 0.004 per 10,000. `index.html` is `no-cache`, so each page view revalidates once at the origin. Assets are cached for a year. Estimate: 5,000 a month. |
| S3 to CloudFront transfer | 0 | "$0.00 per GB data transfer out of EU (Ireland) to CloudFront". |
| CloudFront transfer and requests | 0 | Free each month: "First 1 TB of data transfer" and "First 10 Million HTTP/S requests". These are shared with 025's API, and friends use well under 1 GB and 100,000 requests. |
| Invalidations | 0 | "first 1,000 URLs / month" free, then 0.005 per path. One `/*` path per deploy, about 30 a month. |
| OAC, response headers policy, managed cache policy | 0 | No billed dimension for them in the CloudFront price list. Its families are Request, Data Transfer, Serverless, Fee (invalidations, static IPs, custom-domain SSL) and RealTime logs. |
| GitHub Actions `web` job | 0 | Public repository, standard runner (025's source). |
| **026 in total** | **under 0.01** | **under 0.01 EUR** |

**Effect on the Stage 7 total: none at the precision of 024's table.** 024 had already counted "026 adds
about 0.01". The totals stay at **about 4.8 EUR a month until 2026-12-31** (the T4g trial) and **about
16.8 EUR from 2027-01-01**, unless the user takes one of 024's cuts. This is above the 0 to 10 EUR target
from 2027, for the reasons 024 gives, and 026 does not change that. 026 adds no fixed-price part: no
custom domain or certificate, no WAF, no CloudFront Function, no logging. 024's budget and alerts are not
touched. The row goes into runbook section 14.

### Cache policy and headers (AC 3)
- **Hashed assets** (`assets/*`; today's build has only hashed files there, see Ticket check):
  - S3 metadata `Cache-Control: public, max-age=31536000, immutable`.
  - The name changes whenever the content changes (Vite's content hash), so a year in browsers and at the
    edge is safe.
  - Uploaded with `aws s3 sync --no-overwrite`: the same name means the same bytes, so an existing object
    is never rewritten.
- **`index.html`:**
  - `Cache-Control: no-cache` and `Content-Type: text/html; charset=utf-8`;
  - browsers revalidate it on every load (ETag);
  - CloudFront honours `no-cache` but applies the policy's minimum TTL when it is above 0. Managed
    `CachingOptimized` has a minimum of 1 s, so the edge keeps it at most 1 second (Expiration doc).
  - So visitors get the new version without a manual step. The invalidation below makes "the job is green"
    mean "everyone sees it".
- **CloudFront cache policy:** managed `Managed-CachingOptimized` (`658327ea-f89d-4fab-a63d-7e88639e58f6`):
  - minimum 1 s, default 1 day, maximum 365 days;
  - no query strings or cookies in the key, so `/?group=X` and `/` share one cached `index.html`;
  - gzip and Brotli keys, with `compress = true`.
  - Reused rather than a custom policy (the same reasoning as 025's managed policies).
- **SPA fallback:** custom error responses for 403 and 404, both to `/index.html` with code 200 and
  `error_caching_min_ttl = 0`.
  - S3 answers **403**, not 404, for a missing key when the caller lacks `s3:ListBucket` (S3 GetObject
    API). CloudFront gets no `ListBucket`.
  - A cached error page lives for the larger of the error caching minimum TTL (10 s by default) and the
    origin's `max-age` (HTTPStatusCodes doc). 0 means a new `index.html` also reaches mistyped paths at once.
- **Retention:** each deploy keeps the assets of the **new and the previous release**, and prunes older ones
  only after the invalidation has finished.
  - A visitor with the previous version open can still load its lazily fetched files, such as a font
    subset (AC 3).
  - A visitor two releases behind could miss a font subset. The browser then uses the fallback font; the
    JS and CSS are already loaded.
- **Invalidation:** one path, `/*`, per deploy, then `aws cloudfront wait invalidation-completed`.
  - "A path that includes the * wildcard counts as one path" (invalidation pricing doc). That is 1 of the
    1,000 free paths a month.
  - `/*` also covers the root key and any cached fallback, so there is no doubt about which key the
    default root object uses.
  - Evicting the immutable assets costs one S3 GET per file per edge, which is nothing.

### Security headers (AC 5, 10)
- Our own `aws_cloudfront_response_headers_policy.web` (`cragmatch-web-security`), attached to the default
  behaviour.
  - The managed `SecurityHeadersPolicy` has no CSP, and its `X-Frame-Options` is `SAMEORIGIN`.
  - A response headers policy changes the responses CloudFront serves from the cache and the ones it
    forwards from the origin (response headers doc).
- `Strict-Transport-Security: max-age=31536000` (no `includeSubDomains`, because the parent is
  `cloudfront.net`; no preload), with override.
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`. The share
  link's `?group=CODE` then never leaves in a `Referer`, not even to Airbnb or Booking.
- `Content-Security-Policy`, built in a local from a list of directives:
  `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self';
  connect-src 'self' https://<API distribution domain>; object-src 'none'; base-uri 'self';
  form-action 'self'; frame-ancestors 'none'`.
  - It fits the build checked today: one module script and one stylesheet from `/assets`, the favicon as a
    `data:` SVG, fonts bundled by `@fontsource-variable`, and no inline `<script>`.
  - It also fits 016 to 020's rule "no inline `style=`".
  - `connect-src` is exactly the API's origin, so even injected script could not talk to another host.
- HTTP to HTTPS: `viewer_protocol_policy = "redirect-to-https"` (301). There is no custom domain, so the
  default certificate applies (its TLS floor is AWS's and cannot be raised without our own certificate;
  see Risks).

### First-time order (AC 13)
1. In `infra/main`, `terraform apply` from the working copy **before pushing** (the same rule as 025). It
   creates the bucket, the OAC, the web distribution (5 to 15 minutes), the deploy policy and three
   `/cragmatch/deploy/web_*` parameters. It also rewrites `/cragmatch/api/settings` with
   `CRAGMATCH_CORS_ORIGINS=https://<web domain>`.
   - The host is **not** replaced: settings are read at runtime, and `user_data` does not change.
2. Push. `CI` goes green, then `Deploy`:
   - `Deploy backend` re-renders the API environment and restarts the container (025's step 3 and 6), so
     the API now allows the site's origin;
   - then `Deploy web` builds and publishes.
3. Open `terraform output -raw web_url`.

There is no manual step besides the keys, which 025 already asked for. If the user applies without
pushing, "Run workflow" on `Deploy` with the live SHA does steps 2 and 3.

### Deploy role (AC 7)
- New inline policy `cragmatch-deploy-web` on `cragmatch-github-deploy`. 025's `cragmatch-deploy-backend` is
  not edited.
  1. `ListSite`: `s3:ListBucket` on the bucket ARN.
  2. `WriteSite`: `s3:PutObject`, `s3:DeleteObject` on `<bucket ARN>/*`.
  3. `ReadRelease`: `s3:GetObject` on `<bucket ARN>/release/*` only. The script reads the last release
     record; this is the only read it needs.
  4. `InvalidateSite`: `cloudfront:CreateInvalidation` and `cloudfront:GetInvalidation` on the web
     distribution's ARN. Both take the `distribution` resource (IAM service reference). `GetInvalidation`
     is what `wait invalidation-completed` calls.
- The parameters are read through 025's existing `ReadDeployParameters` (`/cragmatch/deploy/*`). No new SSM
  permission.

### Sources (all fetched 2026-10-14)
- AWS Price List API, `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<offer>/current/...`:
  - `AmazonCloudFront` (global, published 2026-10-03):
    - "First 1 TB of data transfer free each month under CloudFront free tier";
    - "First 10 Million HTTP/S requests free each month";
    - "$0.000 per URL - first 1,000 URLs / month", then "$0.005 per URL";
    - "$0 for First 2,000,000 CloudFront Function Executions", then "$0.10 per 1,000,000";
    - Europe "$0.0120 per 10,000 HTTPS Requests" beyond the free allowance.
  - `AmazonS3` eu-west-1 (published 2026-10-12): "$0.023 per GB - first 50 TB", "$0.005 per 1,000 PUT,
    COPY, POST, or LIST requests", "$0.004 per 10,000 GET and all other requests".
  - `AWSDataTransfer` eu-west-1 (published 2026-09-16): "$0.00 per GB data transfer out of EU (Ireland) to
    CloudFront".
  - `AWSAmplify` eu-west-1 (published 2026-09-11): "$0.15 per GB served", "$0.01 per build minute".
- CloudFront Developer Guide, `https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/`:
  - `PayingForInvalidation.html`: 1,000 free paths a month across all distributions; a `*` wildcard counts
    as one path;
  - `Expiration.html`: with `no-cache` and minimum TTL 0, "CloudFront and browsers respect the headers";
    with a minimum TTL above 0 the policy's minimum applies;
  - `using-managed-cache-policies.html`: `CachingOptimized` id and TTLs (1 s, 86,400 s, 31,536,000 s);
  - `using-managed-response-headers-policies.html`: `SecurityHeadersPolicy` has no CSP and uses
    `X-Frame-Options SAMEORIGIN`;
  - `modifying-response-headers.html`: the policy applies to cached and forwarded responses;
  - `HTTPStatusCodes.html`: a custom error page is cached for the larger of the error caching minimum TTL
    (10 s by default) and the origin's `max-age`;
  - `DefaultRootObject.html`: the root object applies to the root URL only, not to subdirectories (hence
    the error-response fallback);
  - `private-content-restricting-access-to-s3.html`: OAC bucket policy with the `cloudfront.amazonaws.com`
    principal and an `AWS:SourceArn` condition.
- `https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html`: without `s3:ListBucket`, a missing
  key gives "HTTP status code 403 Access Denied".
- `https://docs.aws.amazon.com/cli/latest/reference/s3/sync.html` (AWS CLI 2.38.0):
  - `--delete` removes destination files not in the source;
  - `--no-overwrite`: "only files not present at the destination will be transferred";
  - sync re-uploads when the size differs or the local file is newer;
  - `--cache-control` sets the metadata.
- AWS CLI `CHANGELOG.rst`: `--no-overwrite` was added in 2.33.0. The `ubuntu-24.04` runner image readme
  lists AWS CLI 2.37.9, Node.js 22 (we install 24) and shellcheck 0.9.0.
- IAM Service Reference (`servicereference.us-east-1.amazonaws.com/v1/{cloudfront,s3}/...json`):
  - `CreateInvalidation` and `GetInvalidation` take `distribution`;
  - `ListBucket` takes `bucket`;
  - `PutObject`, `DeleteObject` and `GetObject` take `object`.
- Action versions (GitHub releases API): `actions/setup-node` v7.1.0 (2026-10-08), `actions/checkout`
  v7.0.1, `aws-actions/configure-aws-credentials` v6.3.0.

## Ticket check
Checked against the code on 2026-10-14. `uv run pytest --collect-only -q` collected **199 tests**; it is 266
once 017 to 025 are in, from their plans. No other test ran. No `terraform` command ran, because `infra/`
does not exist yet (024 is not delivered), and nothing touched AWS. Terraform 1.15.8 is installed locally.

- **Correct:**
  - `web/` is Vite 8.3.4, and `npm run build` is `tsc -b && vite build`.
  - `web/src/api/client.ts:1` hardcodes `http://localhost:8000` today; 021 makes it `VITE_API_URL`.
  - `fetch(`${API_URL}${path}`)` needs the address without a trailing slash, which 025's parameter
    guarantees.
  - There is no `web/public/`, so nothing unhashed is copied into `dist/` except `index.html`.
  - Today's build is 0.32 MB:
    - `index.html`, one `index-*.js` and one `index-*.css`;
    - three hashed `woff2` font subsets, which the browser loads on demand by unicode range;
    - no inline script (`<script type="module" crossorigin src="/assets/...">`);
    - the favicon as a `data:` SVG.
  - Only `VITE_` variables reach the bundle.
  - The share link is `/?group=CODE`, built from origin plus pathname (017).
  - Node 24 is used locally (24.18) and in 018's CI.
- **Wrong or missing in the ticket, and what is true:**
  - **AC 12 (wake-up):** dropped. The backend never sleeps (024, 025). Deploy restarts last about 10 to 30
    s, and the app's existing offline and 503 states cover them. No `web/` change.
  - **AC 5 "exactly that origin":** this removes 025's default `http://localhost:5173` from the cloud API.
    So 025's variable `cors_origins` and its test `cors_origins_must_be_plain_origins` are removed, and
    `npm run dev` against the cloud API (025's manual B8) no longer works. Local development uses the local
    backend, as before.
  - **"Terraform is checked with fmt, validate, plan":** agents never run `plan` against AWS (024's rule).
    The developer runs `fmt`, `validate` and the mocked `test`; the user runs `plan` and `apply`.
  - **"A permission to request a short-lived identity token and nothing else":** the job also needs
    `contents: read` for the checkout. The job permissions are exactly those two.
  - **CI does not run `npm run build`:** 018's `ESLint` job runs `npm ci`, `npm run lint` and (020)
    `npm test`, but no `tsc -b`. A type error therefore passes `CI` and fails `Deploy web` **after**
    `Deploy backend` is live.
    - The previous web version stays live (AC 9), and the run is red.
    - Adding the build to `ci.yml` is outside this ticket (ci.yml untouched). The hand-off suggests a
      follow-up step `web: npm run build` in the `ESLint` job.
  - **AC 3 and S3 sync:** the obvious `aws s3 sync --delete` breaks AC 3 for visitors with the previous
    version open (Alternatives). The plan keeps two releases.
  - **AC 8:** both parts on every push, in the order backend then web (`needs: backend`).
  - **AC 13's "order of creation matters":** it does not, inside Terraform (see Approach). It matters only
    for the running API, which picks up the new origin at its next start. The first push's
    `Deploy backend` is that start.
  - **Open questions:**
    - OIDC: yes (024).
    - Both every time: yes.
    - The wait notice: moot (never sleeps).

## Delivery
One build, one review, one commit for the whole ticket (no increments). There is no migration and no app
code. Build order: Terraform, publish script and its check, Terraform tests, workflows, docs.

### 1. The web app on S3 behind its own CloudFront distribution, published after the backend by the Deploy workflow, with the API allowing exactly the site's origin
**Files:**

*Terraform, `infra/main/` (024's stack; policies as `jsonencode`; why-comments as in 024 and 025)*
- `web.tf` (new):
  - `aws_s3_bucket.web`:
    - named `cragmatch-web-${account_id}-${var.region}` (account from 024's `data.aws_caller_identity`; the
      same naming as the state bucket);
    - `force_destroy = true`. Comment: every object can be rebuilt from git, and `destroy` must not get
      stuck (as 025's ECR).
  - `aws_s3_bucket_public_access_block.web` (all four `true`), `aws_s3_bucket_ownership_controls.web`
    (`BucketOwnerEnforced`) and `aws_s3_bucket_server_side_encryption_configuration.web` (`AES256`).
    Comment: SSE-KMS would need a key policy for CloudFront; SSE-S3 needs nothing.
  - No versioning. Comment: a rollback is a rebuild from git (runbook), and old `index.html` versions
    would only cost.
  - `aws_cloudfront_origin_access_control.web`: `s3`, `always`, `sigv4`.
  - `aws_s3_bucket_policy.web`, with two statements:
    1. `Allow` `cloudfront.amazonaws.com` `s3:GetObject` on exactly `<arn>/index.html` and
       `<arn>/assets/*`, with `StringEquals` `AWS:SourceArn` = the web distribution's ARN;
    2. `Deny` `s3:*` when `aws:SecureTransport` is `false` (024's pattern).
    - Comment: `release/*` stays unreadable to visitors, and there is no `ListBucket`, so a missing key is
      a 403, which the fallback turns into the app.
  - `locals { web_csp = join("; ", [...]) }`, one directive per line, with a why-comment on `connect-src`
    and on `style-src 'self'` (no inline styles in `web/src`).
  - `aws_cloudfront_response_headers_policy.web` as in Decisions: `security_headers_config` with
    `strict_transport_security`, `content_type_options`, `frame_options`, `referrer_policy` and
    `content_security_policy`, all with `override = true`.
  - `data "aws_cloudfront_cache_policy" "caching_optimized"` (name `Managed-CachingOptimized`).
  - `aws_cloudfront_distribution.web`:
    - one origin `site`: `aws_s3_bucket.web.bucket_regional_domain_name` with the OAC. No OAI; the
      developer checks the provider's form for OAC without `s3_origin_config`.
    - `default_root_object = "index.html"`, `enabled = true`, `is_ipv6_enabled = true` (static files, no
      rate limit, so no reason to refuse IPv6, unlike 025's API), `http_version = "http2and3"`,
      `price_class = "PriceClass_100"`, `comment = "CragMatch web"`, no `aliases`, no logging;
    - default behaviour: `GET` and `HEAD` allowed and cached, `compress = true`,
      `viewer_protocol_policy = "redirect-to-https"`, the cache policy, the response headers policy, no
      origin request policy;
    - `custom_error_response` for 403 and for 404: `response_page_path = "/index.html"`,
      `response_code = 200`, `error_caching_min_ttl = 0`;
    - `viewer_certificate { cloudfront_default_certificate = true }`, `restrictions` none.
    - A block comment: separate from `aws_cloudfront_distribution.api` (025), which must stay API-only;
      cache rules for each file type are set by the publish script as object metadata.
  - `aws_ssm_parameter.deploy_web_bucket`, `.deploy_web_distribution_id` and `.deploy_web_url`
    (`/cragmatch/deploy/web_bucket`, `/cragmatch/deploy/web_distribution_id`, `/cragmatch/deploy/web_url` =
    `"https://${aws_cloudfront_distribution.web.domain_name}"`, no trailing slash), all `String`.
  - `aws_iam_role_policy.github_deploy_web` (`cragmatch-deploy-web`) with the four statements above.
    Comment: separate from 025's policy, so each ticket's test pins its own permissions.
- `api.tf` (025, edit): in `local.api_settings`, set
  `CRAGMATCH_CORS_ORIGINS = "https://${aws_cloudfront_distribution.web.domain_name}"`. The comment says:
  exactly the live site; no cycle; the API reads it at its next start, which is the next
  `Deploy backend`.
- `variables.tf` (025, edit): remove `cors_origins`.
- `terraform.tfvars.example` (025, edit): remove its line.
- `outputs.tf` (edit): `web_url`, `web_bucket`, `web_distribution_id`. None is sensitive.
- `tests/` mock overrides (wherever 025 put the shared `override_data`: `foundation.tftest.hcl` and
  `backend.tftest.hcl`, or `tests/mocks/aws.tfmock.hcl`): add `aws_cloudfront_cache_policy` with
  `id = "658327ea-f89d-4fab-a63d-7e88639e58f6"`, so every file still plans.

*Publish script, `infra/web/` (new folder; bash, `set -euo pipefail`, shellcheck-clean, never `set -x`)*
- `publish-web.sh <dist> <bucket> <distribution-id> <sha> <api-url>`. It prints `== step` lines and never
  prints the bucket, the distribution id or the URL.
  0. Check the arguments: the SHA matches `^[0-9a-f]{40}$`, `<dist>/index.html` and `<dist>/assets/` exist.
  1. **Bundle check (AC 4):**
     - `grep -rqF "$api_url" "$dist"` must find the API address (proof the build used it);
     - `grep -rqE "sk-ant-|CRAGMATCH_|BEGIN [A-Z ]*PRIVATE KEY" "$dist"` must find nothing;
     - no `*.map` file.
     - On failure, print "Bundle check failed: <which>" and exit 1 before any upload.
  2. **Last release:** if `aws s3 ls s3://B/release/current.txt` finds it, read it with `aws s3 cp ... -`
     into a temp file; otherwise treat this as the first release.
  3. **Assets:** `aws s3 sync "$dist/assets" s3://B/assets --no-overwrite --only-show-errors
     --cache-control "public, max-age=31536000, immutable"`.
  4. **Page:** `aws s3 cp "$dist/index.html" s3://B/index.html --cache-control no-cache --content-type
     "text/html; charset=utf-8" --only-show-errors`. Comment: only after every asset it names exists.
  5. **Invalidate:** `aws cloudfront create-invalidation --distribution-id D --paths "/*" --query
     Invalidation.Id --output text`, then `aws cloudfront wait invalidation-completed`.
  6. **Record the release:** the new `current.txt` is the line `commit <sha>`, then every
     `assets/<name>` in `dist/assets`, sorted.
     - If the old current's commit differs from `<sha>`, the old current becomes `previous.txt`.
     - If it is the same SHA (a re-run), keep the old `previous.txt`, so a re-run never shortens the
       history.
     - Upload both with `--cache-control no-cache`.
  7. **Prune:** list `assets/` with `aws s3api list-objects-v2 --bucket B --prefix assets/ --query
     "Contents[].Key" --output text`. `aws s3 rm` each key that is in neither `current.txt` nor
     `previous.txt`. Print the count only.
  8. Print `Live web: <sha>`.
  - Any failure exits non-zero. Before step 4, the old page is untouched; before step 7, nothing is
    deleted (AC 9).
- `check-publish.sh` (new, the behaviour check, in the pattern of 024's `check-db-image.sh`). It needs no
  network and no AWS.
  - It puts a stub `aws` first on `PATH`. The stub is written by the check into a temp dir and maps
    `s3://bucket/...` to a temp folder. It implements exactly the calls above (`s3 ls`, `s3 cp` from a
    file, to and from `-`, `s3 sync --no-overwrite`, `s3 rm`, `s3api list-objects-v2`,
    `cloudfront create-invalidation`, `cloudfront wait`). It appends each call with its arguments to
    `calls.log`, and fails on purpose when `FAKE_AWS_FAIL` matches the call.
  - It builds fake `dist/` folders (a tiny `index.html` naming the API URL, plus hashed asset names) and
    runs the cases below.
  - It prints `ok: <case>` for each and exits non-zero naming the first failed case; the temp dir is
    removed in an exit trap.

*Workflows*
- `.github/workflows/deploy.yml` (025, edit; trigger, `concurrency`, top `permissions` and job `backend`
  unchanged). New job `web`, name `Deploy web`:
  - `needs: backend`, and the **same `if`** as `backend`. Without `always()`, a failed or cancelled
    `backend` skips `web`. Comment: backend first, so the API allows the new origin before the site calls
    it.
  - `runs-on: ubuntu-24.04`, `timeout-minutes: 15`, `permissions: { contents: read, id-token: write }`.
  - Steps:
    1. **Pick the commit:** the same code as `backend`'s step 1. It takes the `image_tag` input or
       `github.event.workflow_run.head_sha`, checks the pattern, and runs the `git ls-remote` guard (`main`
       moved on gives a notice and `go=false`). Every later step has `if: steps.pick.outputs.go == 'true'`.
       Comment: on a dispatch, the input is the commit to deploy, for both parts.
    2. `actions/checkout@v7` with `ref` = that SHA, on both triggers, because a rollback rebuilds the old
       web.
    3. `actions/setup-node@v7`: `node-version: 24`, `cache: npm`,
       `cache-dependency-path: web/package-lock.json` (018's settings).
    4. `aws-actions/configure-aws-credentials@v6` exactly as in `backend`.
    5. **Read the deploy parameters:** `api_url`, `web_bucket`, `web_distribution_id` and `web_url` from
       `/cragmatch/deploy/`. `::add-mask::` each one **before** writing it to `$GITHUB_OUTPUT`. The bucket
       name holds the account id, and the logs are public.
    6. `web: npm ci` (`working-directory: web`).
    7. `web: npm run build` with `env: VITE_API_URL: ${{ steps.params.outputs.api_url }}`.
    8. **Publish:** `bash infra/web/publish-web.sh web/dist "$BUCKET" "$DIST_ID" "$SHA" "$API_URL"`, with
       the values passed through `env:`, not interpolated into the script text.
    9. **Check the live site** with `curl -fsS`, using `grep -q` and never printing headers:
       - `GET $WEB_URL/` contains `id="root"`, has `cache-control: no-cache`,
         `strict-transport-security` and `content-security-policy` (AC 1, 3, 10);
       - `$WEB_URL/?group=ABCD2345` and `$WEB_URL/no/such/page` both give 200 with `id="root"` (AC 2);
       - the first `/assets/*.js` named in that page has `immutable` and a `javascript` content type (AC 3;
         `nosniff` would block anything else);
       - `http://` + the host gives 301 to `https://` (AC 10);
       - a preflight `OPTIONS $API_URL/health` with `Origin: $WEB_URL` and
         `Access-Control-Request-Method: GET` returns `access-control-allow-origin` equal to `$WEB_URL`;
         with `Origin: https://evil.example` that header is absent (AC 5).
  - No `secrets.` anywhere, and no AWS key.
- `.github/workflows/terraform.yml` (024, edit; name, triggers and jobs kept):
  - the shellcheck step adds `infra/web/*.sh`;
  - a new step in job `terraform`, `Web publish script`, runs `bash infra/web/check-publish.sh`.
  - `paths: infra/**` already covers the folder. `ci.yml` is not touched.

*Docs*
- `infra/RUNBOOK.md`:
  - Section 14 gains the row "Web hosting (026): under 0.01 USD a month", with the table and sources above
    in short. The total lines stay at about 4.8 EUR until 2026-12-31 and about 16.8 EUR from 2027.
  - New sections after 23, in PowerShell:
  24. **Web: what it adds:**
      - the path (phone, CloudFront HTTPS, private bucket through OAC);
      - the cache rules (assets a year and immutable, `index.html` `no-cache`, `/*` invalidated per
        deploy);
      - two releases kept;
      - the security headers and the CSP;
      - the API allows only the site's origin, so `npm run dev` against the cloud API is refused (use the
        local backend).
  25. **Web: first deploy:** the three steps of "First-time order" above. If `terraform.tfvars` still has
      `cors_origins`, delete that line.
  26. **Redeploy and what is live:**
      - every green `CI` on `main` deploys backend, then web (AC 8: both, always);
      - the `Deploy` run ends with "Live web: <sha>";
      - `aws s3 cp ("s3://" + (terraform output -raw web_bucket) + "/release/current.txt") -` prints the
        live commit and its files; `previous.txt` the one before.
  27. **Roll back:**
      - "Run workflow" on `Deploy` with `image_tag` = the previous SHA and `skip_migrations` ticked. Both
        parts return to that commit: `Deploy web` rebuilds it with today's API address.
      - The previous release's assets are still in the bucket, so pages that are open keep working.
      - A web-only rollback is not offered (simple and predictable).
  28. **Destroy, web part:**
      - `terraform destroy` (section 22) also removes the bucket with its files (`force_destroy`), the web
        distribution (disabling takes minutes), its policies and the three parameters.
      - Removing only the web hosting is a code change (delete `web.tf`, point CORS elsewhere) followed by
        an apply. Never `-target`: it would also destroy `/cragmatch/api/settings`, which depends on the
        site.
  29. **Checks of 026:** the "Check by hand" list B below, as commands.
- `README.md`:
  - Structure:
    - `infra/main/` gains "web bucket and CloudFront distribution";
    - new line `infra/web/  publish script for web/dist (keeps two releases) and its offline check`;
    - the `deploy.yml` line ends "...then build web/ with the live API address, publish to S3 and
      invalidate CloudFront".
  - "Deploying to AWS": the site address is `terraform output -raw web_url`; every push to `main` deploys
    backend then web after `CI`.
- `CLAUDE.md`: **not edited.** Suggest in the hand-off:
  - Traps: "the cloud API allows only the site's origin (`CRAGMATCH_CORS_ORIGINS` from Terraform)"; "never
    `aws s3 sync --delete` the site: `publish-web.sh` keeps two releases".
  - Optionally a follow-up: `web: npm run build` in CI's `ESLint` job.

**Reuses:**
- 021's `VITE_API_URL` and `CRAGMATCH_CORS_ORIGINS`.
- 024's patterns: bucket naming, the private bucket, TLS-only policy, `jsonencode`, mocked tests,
  `Terraform` workflow, shellcheck and tflint, a bash `check-*.sh` run in CI, and the deploy role with
  repository variables.
- 025's pieces:
  - `api_url` parameter and `ReadDeployParameters`;
  - `Deploy` workflow trigger, `if`, SHA guard, concurrency group and dispatch inputs;
  - `current`/`previous` release files on the data volume, the model for `release/*.txt`;
  - masking;
  - runbook structure.
- 018's Node setup.
- AWS-managed pieces: OAC, the `CachingOptimized` policy, custom error responses, invalidations.

**Tests:**

*`infra/main/tests/web.tftest.hcl` (new, 8 runs, mocked AWS, `command = apply` where computed values are
read)*
- `site_bucket_is_private_and_encrypted`: the name is `cragmatch-web-123456789012-eu-west-1`, all four
  public-access flags are true, `BucketOwnerEnforced`, `AES256`, and `force_destroy` is true (AC 4, 10).
- `only_the_web_distribution_reads_only_the_site_files`, on the decoded bucket policy:
  - the `Allow` has the `cloudfront.amazonaws.com` principal and only `s3:GetObject`;
  - its resources are exactly `<arn>/index.html` and `<arn>/assets/*`;
  - `AWS:SourceArn` is the web distribution's ARN;
  - a `Deny` exists for `aws:SecureTransport` `false`
  (AC 4).
- `web_distribution_serves_the_bucket_over_https_only`, asserting:
  - one origin, which is the bucket's regional domain with the OAC id; the OAC is `s3`, `always`, `sigv4`;
  - `index.html` as root object;
  - methods `GET` and `HEAD`, `compress`, `redirect-to-https`, the `CachingOptimized` id and our headers
    policy id;
  - the default certificate, no `aliases`, `PriceClass_100`
  (AC 1, 3, 10).
- `unknown_paths_open_the_app`: exactly two custom error responses, 403 and 404, each to `/index.html`
  with 200 and TTL 0 (AC 2).
- `security_headers_pin_https_and_the_api`, asserting:
  - HSTS max-age 31536000, `nosniff`, `DENY`, `no-referrer`, each with override;
  - the CSP contains `script-src 'self'`, `frame-ancestors 'none'` and
    `connect-src 'self' https://${aws_cloudfront_distribution.api.domain_name}`;
  - it contains neither `unsafe-inline` nor `*`
  (AC 5, 10).
- `deploy_role_publishes_the_site_and_invalidates_it_only`, on the decoded `cragmatch-deploy-web`:
  - exactly the four statements with the actions and resources above;
  - no `iam:`, no `"*"` action or resource, and no other bucket or distribution
  (AC 7).
- `deploy_parameters_name_the_site`:
  - the three parameters equal the bucket id, the distribution id and `"https://" + domain_name`, with no
    trailing slash;
  - the `web_url` output is the same
  (AC 7, 13).
- `web_hosting_adds_no_paid_extras`: the state has no `aws_cloudfront_function`, no `aws_acm_certificate`,
  no `aws_wafv2_web_acl`, and `logging_config` is empty (AC 11).

*`infra/main/tests/backend.tftest.hcl` (025, edited):*
- `api_settings_use_the_database_over_verified_tls_and_hold_no_secret` now asserts
  `CRAGMATCH_CORS_ORIGINS=https://${aws_cloudfront_distribution.web.domain_name}` and no `localhost`
  (AC 5).
- `cors_origins_must_be_plain_origins` is **removed** with its variable.

*`infra/web/check-publish.sh` (new, 6 cases, offline)*
- `first_release_uploads_with_the_right_cache_rules`:
  - assets carry `public, max-age=31536000, immutable`;
  - `index.html` carries `no-cache` and `text/html`;
  - `current.txt` names the SHA and every asset, and there is no `previous.txt`;
  - one invalidation with `/*` was created and waited for;
  - nothing was deleted
  (AC 3).
- `upload_order_never_shows_a_page_before_its_files`: in `calls.log`, the `sync` of assets comes before
  the `cp` of `index.html`, that comes before `create-invalidation`, then `wait`, then the release record,
  then any `rm` (AC 3, 9).
- `previous_release_assets_survive_and_older_ones_go`: after releases A, B and C, the assets of B and C
  exist, A's alone are gone, and an asset shared by A and C stays (AC 3).
- `rerun_of_the_same_commit_changes_nothing`: running C again uploads no asset, deletes nothing and keeps
  `previous.txt` = B (AC 3, 8).
- `a_bundle_with_a_key_or_without_the_api_address_is_not_published`: two runs:
  - `sk-ant-x` in a JS file;
  - an `index.html` without the API URL.
  Each exits non-zero with "Bundle check failed", and `calls.log` is empty (AC 4).
- `a_failed_upload_leaves_the_previous_version_live`: with `FAKE_AWS_FAIL` on the `index.html` copy, the
  script exits non-zero, `index.html` and `current.txt` still belong to B, and nothing was deleted (AC 9).

*Checks, not tests:* shellcheck on both scripts, tflint `aws_resource_missing_tags` (bucket and
distribution get `Project` from `default_tags`; OAC, the headers policy and the bucket policy cannot be
tagged), and the workflow's step 9 on every deploy.

**Expected suite:**
- Backend: **266 passed**, unchanged (no backend file changes). `uv run ruff check .` is clean.
- Terraform:
  - `infra/main` **41 passed**: 34 before, minus `cors_origins_must_be_plain_origins`, plus 8 in
    `web.tftest.hcl`;
  - `infra/bootstrap` **8 passed**, unchanged.
- `bash infra/web/check-publish.sh`: **6 ok**, a new suite.
- `web/`: Vitest **28 passed**, unchanged. `npm run lint` gives 0 problems, and `npm run build` succeeds.
  No `web/` file changes.
- `terraform fmt -check -recursive infra`, both `validate` runs, tflint and shellcheck: 0 problems.

**Check by hand.**

*A. Developer and reviewer, no AWS:*
1. `terraform fmt -check -recursive infra`. In `infra/main`, `terraform init -backend=false`, `validate`
   and `test` (41). `infra/bootstrap` still gives 8.
2. `bash infra/web/check-publish.sh` (Git Bash on Windows, or CI) prints 6 `ok:` lines. Run shellcheck if
   it is installed.
3. In `web/`: `$env:VITE_API_URL = "https://d111.cloudfront.net"`, `npm run build`,
   `Remove-Item Env:VITE_API_URL`, then:
   - `Select-String -Path dist\assets\*.js -Pattern "d111.cloudfront.net"` finds it;
   - `Get-ChildItem dist -Recurse -Filter *.map` finds nothing;
   - `Get-ChildItem dist -Exclude assets` shows only `index.html`.
   Report whether `localhost:8000` is still in the bundle: the minifier may or may not fold 021's `||`
   fallback. Either is harmless; it is not a check failure. `npm test` gives 28 and `npm run lint` 0.
4. From `backend/`:
   `uv run python -c "import yaml; d = yaml.safe_load(open('../.github/workflows/deploy.yml')); j = d['jobs']; print(list(j), j['web']['needs'], j['web']['if'] == j['backend']['if'], j['web']['permissions'])"`
   prints `['backend', 'web'] backend True {'contents': 'read', 'id-token': 'write'}`.
5. Greps:
   - `git grep -n "secrets\." .github` finds nothing;
   - `git grep -nE "[0-9]{12}" -- infra .github` finds only `123456789012`;
   - `git grep -n -- "--delete" -- infra .github` finds nothing;
   - `git grep -n "set -x" -- infra/web` finds nothing.
6. `git diff --stat` shows nothing under `backend/`, `web/` or `.github/workflows/ci.yml`.

*B. The user, on the account (runbook section 29):*
1. **AC 13:** follow section 25. `terraform plan` before the apply shows:
   - only additions;
   - the change to `/cragmatch/api/settings`;
   - no replacement of `aws_instance.host`.
   After the push, `CI`, then `Deploy backend`, then `Deploy web` are green, with no other manual step.
2. **AC 1, 10:**
   - on a phone on mobile data, open `web_url`; a filter search returns sectors;
   - `Invoke-WebRequest ("http://" + <domain>) -MaximumRedirection 0` gives 301 to `https`.
3. **AC 2:** create a group on the laptop, then open its share link on another phone; it opens. Refresh:
   still there. Open `<web_url>/no/such/page`: the app, not an XML error.
4. **AC 3:**
   - keep a tab open, push a visible text change, and wait for `Deploy`;
   - the old tab still works (fonts and search), and a reload shows the change;
   - `curl.exe -sI <web_url>/` shows `cache-control: no-cache`; an asset shows `immutable`.
   - After three deploys, `aws s3 ls s3://<bucket>/assets/` shows only the files of the last two
     `release/*.txt`.
5. **AC 4:** download the live `index.html` and JS (`Invoke-WebRequest -OutFile`), then `Select-String`
   for `sk-ant`, `pa-` and `CRAGMATCH_`: nothing found. Only the API domain is a deploy-time value.
6. **AC 5:**
   - the browser's network tab shows `access-control-allow-origin: <web_url>` on API answers;
   - from a page on another origin (for example `about:blank` devtools console on `https://example.com`),
     `fetch("<api_url>/health")` fails with a CORS error.
   - `aws ssm get-parameter --name /cragmatch/api/settings` shows exactly one origin.
7. **AC 6:** on the live site:
   - start a planner run and answer it;
   - group search with the stays panel;
   - one natural search and one vibe search, a minute apart (Voyage limit);
   - the browser console shows **no CSP violation**.
8. **AC 7, 9:**
   - a throwaway commit with a Ruff error leaves `Deploy` skipped and the site unchanged;
   - `gh secret list` is empty;
   - the `Deploy` logs show `***` for the API address, the site, the bucket and the distribution id.
9. **AC 8:** a backend-only commit runs both jobs; section 26 says "both, always".
10. **AC 11:** next month's bill shows S3 and CloudFront at 0.00 or 0.01. 024's budget is unchanged.
11. **AC 14:** read sections 25 to 28.
    - Run section 27 with the previous SHA: `release/current.txt` shows it, and the site works.
    - Deploy the newest SHA again.

**Commit:** `Ticket 026: web app on AWS, private S3 bucket behind its own CloudFront distribution with origin access control, HTTPS only, SPA fallback to index.html, hashed assets cached a year and index.html no-cache, security headers with a CSP limited to the API, API CORS set to exactly the site origin, Deploy workflow gains a web job after the backend that builds web with the live API address and publishes through a script that checks the bundle, uploads assets before the page, invalidates once and keeps the previous release, least-privilege deploy policy, offline terraform tests and publish checks, runbook for first deploy, redeploy, rollback and destroy`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `web.tftest.hcl::web_distribution_serves_the_bucket_over_https_only`; workflow step 9; manual B2 |
| 2 | `::unknown_paths_open_the_app`; workflow step 9 (`?group=`, mistyped path); manual B3 |
| 3 | `check-publish.sh` cases 1 to 4; `::web_distribution_serves_the_bucket_over_https_only` (cache policy); workflow step 9 (headers); manual B4 |
| 4 | `check-publish.sh::a_bundle_with_a_key_or_without_the_api_address_is_not_published`; `::site_bucket_is_private_and_encrypted`, `::only_the_web_distribution_reads_only_the_site_files`; manual A3 and B5 |
| 5 | `backend.tftest.hcl::api_settings_use_the_database_over_verified_tls_and_hold_no_secret` (exactly the site origin); `::security_headers_pin_https_and_the_api`; workflow step 9 (allowed and refused preflight); manual B6 |
| 6 | Manual B7 (every screen, no CSP violation) |
| 7 | `::deploy_role_publishes_the_site_and_invalidates_it_only`, `::deploy_parameters_name_the_site`; the job's `needs`, `if` and permissions (manual A4, review); manual B8 |
| 8 | Runbook section 26; `check-publish.sh::rerun_of_the_same_commit_changes_nothing`; manual B9 |
| 9 | `check-publish.sh::a_failed_upload_leaves_the_previous_version_live`, `::upload_order_never_shows_a_page_before_its_files`; `needs: backend` (a red backend skips web); manual B8 |
| 10 | `::web_distribution_serves_the_bucket_over_https_only` (redirect, default certificate, no aliases), `::security_headers_pin_https_and_the_api` (HSTS); workflow step 9; manual B2 |
| 11 | "Cost delta" above and runbook section 14; `::web_hosting_adds_no_paid_extras`; 024's budget tests unchanged; manual B10 |
| 12 | Dropped: the backend never sleeps (Ticket check) |
| 13 | "First-time order" above and runbook section 25; `::deploy_parameters_name_the_site`; manual B1 |
| 14 | Runbook sections 25 to 28; manual B11 (rollback run) |

Every criterion is covered. AC 1, 2, 6 and 13 can only be fully shown on the live site. AC 6 has no
automated test because nothing in the app changes; the risk it guards against is the CSP, which manual B7
checks.

## Risks
- **CSP blocks something on the live site** (an inline style a library injects, a new external call): the
  app breaks only in the cloud, where `npm run dev` cannot show it.
  - Manual B7 reads the console.
  - The fix is one directive in `local.web_csp`, then an apply, with no redeploy.
  - Any future external call (maps, analytics) must add itself to `connect-src`. The runbook says so.
- **Headers on error responses:** the docs fetched do not say whether a response headers policy also
  applies to custom error responses. If `/no/such/page` lacks the CSP (step 9 would show it), it is still
  the same `index.html` loaded under the same origin. Accept it and note it.
- **Wrong `Content-Type` from `aws s3`:** the CLI guesses from the extension. With `nosniff`, a JS file not
  typed as JavaScript would be blocked. Step 9 asserts the JS type on every deploy. The fix is an explicit
  `--content-type` for `*.js` in the script.
- **`--no-overwrite` needs AWS CLI 2.33 or later:** the runner has 2.37.9. An older image would fail with
  "unknown option", red and before the page, so it fails safe. The fallback flag is `--size-only`.
- **Build errors after the backend is live** (CI does not run `tsc -b`): the web job fails and the previous
  web stays, but the backend is already the new commit. Mitigation: API changes stay additive (025's
  migration rule applies to endpoints too), plus the suggested CI follow-up.
- **The cloud API refuses localhost:** intended (AC 5). Developers use the local backend. It is written in
  runbook section 24.
- **Default certificate TLS floor:** with `*.cloudfront.net`, the security policy is AWS's and cannot be
  raised. A custom domain is the upgrade path, and it is out of scope.
- **Two releases of retention:** a visitor with a page open across two deploys may miss a lazily loaded
  font subset (fallback font, no breakage). The JS and CSS are already loaded. Accepted.
- **Rollback rebuilds:** an old commit is rebuilt with today's `package-lock.json` of that commit and
  today's API address. The hashes may differ from the original, but the assets are uploaded fresh, so
  nothing is missing.
- **Public logs:** the bucket name holds the account id. Every value from Parameter Store is masked
  before use, and the script prints no names. The reviewer reads every `echo`.
- **External services:** Voyage's 3 a minute during manual B7 (one vibe search, a minute apart). No test
  touches the network: the check stubs `aws`, and Terraform is mocked.
- **Behaviour that must stay unchanged:**
  - `backend/`, `web/`, `ci.yml`, 025's `backend` job and `cragmatch-deploy-backend`, and 024's budget;
  - the host is not replaced by this apply.
- **No migration:** nothing to downgrade. Destroying the web part is covered in section 28.
- **Size:** about 13 files:
  - 4 new: `web.tf`, `web.tftest.hcl` and the two scripts;
  - 9 edited: `api.tf`, `variables.tf`, the example, `outputs.tf`, the mocks, `backend.tftest.hcl`,
    `deploy.yml`, `terraform.yml`, plus the runbook and README.
  - 8 Terraform runs and 6 script cases. Smaller than 025, one coherent path, so **one delivery is fine.**
  - If the review finds it too big, split the **ticket**: 026a hosting plus CORS plus a manual publish
    with the script, and 026b the `web` job.

## Out of scope (copied from the ticket)
- The backend infrastructure: ticket 025. The foundation: ticket 024.
- A custom domain, login, public access: share codes stay the only access.
- A preview environment per pull request.
- Edge security features (web application firewall, bot rules): the daily cap and rate limits bound the
  cost, and the site is unlisted.
- Search engine hints and hiding `/docs`: not now.
