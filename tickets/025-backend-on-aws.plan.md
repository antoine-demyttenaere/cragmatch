# Plan for 025: Deploy on AWS, part 2: the backend running in the cloud

**Ticket:** `tickets/025-backend-on-aws.md`
**Approach:** The backend image (ticket 021) is built for arm64 on GitHub's native arm runner, pushed to a
private ECR repository with immutable commit-SHA tags, and run as a second systemd unit next to Postgres on
024's `t4g.small` host. The host's only inbound rule opens port 80 to CloudFront's origin-facing prefix list,
and a **separate API CloudFront distribution** (default `*.cloudfront.net` certificate, caching disabled, all
viewer headers forwarded) gives the stable HTTPS address. A `Deploy` workflow, gated on ticket 018's `CI`
workflow through `workflow_run`, builds and pushes the image. It then sends one custom SSM document. That
document only runs `/opt/cragmatch/deploy-api.sh <sha>` on the host, which pulls the image, runs
`alembic upgrade head` as a one-off container while the old version still serves, restarts the unit, checks
`/health`, warms the planner tables, and returns to the previous image if the new one is unhealthy.

Assumed delivered first, as their plans describe: 017 to 024. In particular 021's image (`fastapi run`, one
worker, `PORT` 8000, `HF_HOME=/home/cragmatch/.cache/huggingface`, uid 10001, CMD replaceable), 022's cap
(`daily_spend`, `CRAGMATCH_CLAUDE_DAILY_CAP_USD` 1.00 and `CRAGMATCH_VOYAGE_DAILY_CAP_USD` 0.50 by default),
023's `load_data`, and 024's `infra/` (host, Docker network `cragmatch`, `db:5432` TLS-only, Elastic IP,
`cragmatch-github-deploy` role with no permissions, runbook sections 1 to 13). **No application code
changes.** One new backend test file pins the client-address behaviour that the deployment relies on.

## Up front: cost against the 0 to 10 EUR target (AC 13)
Prices are for eu-west-1 in USD, fetched on 2026-10-14. EUR is at 024's ECB rate (1 EUR = 1.1188 USD).

| What 025 adds | USD a month | Why |
|---|---|---|
| ECR storage | about 0.05 typical, 0.20 at most | 0.10 per GB-month. Lifecycle keeps 5 tagged images and expires untagged ones after 1 day. Images that share the dependency layer cost little more than one; the worst case is 5 images with different dependency layers at about 0.4 GB each. |
| ECR pulls to the host | 0 | Same-region transfer from ECR to EC2 is free. Pushes are inbound, also free. |
| API CloudFront distribution | 0 | Pay-as-you-go always-free allowance: 1 TB out and 10 M requests a month (024's source), shared with 026's site. A few friends use well under 1 GB and 100,000 requests. |
| Host to CloudFront (origin fetches) | 0 | "$0.00 per GB data transfer out of EU (Ireland) to CloudFront" (price list). |
| Host to Claude, Voyage, huggingface.co | 0 | Within the 100 GB a month global free tier for data out, then 0.09 per GB. |
| CloudWatch Logs `/cragmatch/api` (14 days) | 0 | 5 GB a month free (ingestion and storage). Beyond that 0.57 per GB ingested and 0.03 per GB-month stored, which is about 0.03 at 50 MB a month. |
| SSM document, Run Command, 3 Standard parameters | 0 | Free (024's source). |
| GitHub Actions on `ubuntu-24.04-arm` | 0 | The repository is **public** (checked with `gh repo view`), and standard runners are free for public repositories. |
| **025 in total** | **about 0.05 to 0.25** | **about 0.05 to 0.22 EUR** |

**Effect on the Stage 7 total:** none at the precision of 024's table, which already counted "025 adds
about 0.10 to 0.20". So the totals stay at **about 4.8 EUR a month until 2026-12-31** (T4g free trial) and
**about 16.8 EUR from 2027-01-01** unless the user takes one of 024's cuts. 025 adds no fixed-price part:
no load balancer, no NAT, no extra public IPv4, no Secrets Manager. 024's budget and its alerts stay as they
are. One interaction to know about: 024's **cut 2** (stopping the host about 16 hours a day) turns the API
off for those hours. CloudFront then answers 502/504 and the web app shows its offline state; there is no
wake-up (see AC 14).

**Sources (fetched 2026-10-14):**
- AWS Price List API, `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<offer>/current/eu-west-1/index.json`:
  - `AmazonECR`, published 2026-09-11: "$0.10 per GB-month of data storage";
  - `AmazonCloudWatch`, published 2026-10-07: "$0.57 per GB custom log data ingested in Standard log class",
    "$0.03 per GB-mo of log storage";
  - `AWSDataTransfer`, published 2026-09-16: "$0.00 per GB data transfer out of EU (Ireland) to CloudFront",
    and "$0.000 per GB under the monthly global free tier".
- `https://aws.amazon.com/ecr/pricing/`: transfer between ECR and EC2 in the same Region is free. It also
  says new ECR customers get 500 MB a month free for one year. That may not apply to accounts made under
  the credits-based free tier of 2025 and later (024), so the table does not count on it.
- `https://aws.amazon.com/cloudwatch/pricing/`: free tier "5 GB Data (ingestion, archive storage, and data
  scanned by Logs Insights queries)".
- `https://docs.github.com/en/actions/reference/runners/github-hosted-runners`: `ubuntu-24.04-arm` (4 vCPU,
  16 GB) for public repositories.
- CloudFront behaviour, from the Developer Guide:
  - `RequestAndResponseBehaviorCustomOrigin.html`: the viewer's IP is appended to the end of
    `X-Forwarded-For`, and a viewer's own `X-Forwarded-Proto` is removed;
  - `add-origin-custom-headers.html`: the list of headers CloudFront can't add, which does not include
    `X-Forwarded-Proto`;
  - `HTTPStatusCodes.html`: "If you're using the CachingDisabled managed cache policy, CloudFront won't cache
    these status codes";
  - `cloudfront-limits.html`: response timeout 1 to 120 seconds without a quota request;
  - `using-https-cloudfront-to-custom-origin.html`: no self-signed origin certificates, Mozilla's CA list
    only;
  - `using-managed-cache-policies.html`, `using-managed-origin-request-policies.html`: `CachingDisabled`
    (`4135ea2d-...`) and `AllViewer` (`216adef6-...`);
  - `LocationsOfEdgeServers.html`: the origin-facing managed prefix list.
- IAM Service Reference (`https://servicereference.us-east-1.amazonaws.com/v1/{ssm,ecr}/...json`):
  - `ssm:SendCommand` takes `document` and `instance` resources;
  - `ssm:GetCommandInvocation` and `ecr:GetAuthorizationToken` take none (so `*`);
  - ECR push and pull actions take the `repository` resource.
- Action versions (GitHub releases API): `actions/checkout` v7.0.1, `aws-actions/configure-aws-credentials`
  v6.3.0, `aws-actions/amazon-ecr-login` v2.1.7, `docker/setup-buildx-action` v4.4.1,
  `docker/build-push-action` v7.4.0.

## Decisions
- **Registry: ECR** private repository `cragmatch-api`:
  - `IMMUTABLE` tags, so a tag (the full 40-character commit SHA) always means the same image;
  - basic scan on push (free);
  - `force_delete = true`, because every image can be rebuilt from git and `destroy` must not get stuck;
  - lifecycle: rule 1 expires untagged images after 1 day; rule 2 (`tagStatus = any`) keeps the newest 5.
    Five tags give four steps of rollback.
  - Not Docker Hub or GHCR: a public registry would publish the image, and a private GHCR pull needs a
    long-lived token on the host. ECR uses the host's role.
- **Compute:** 024's host. A systemd unit `cragmatch-api.service` runs one container named `api` with
  021's CMD (`--workers 1`). One host, one unit and one container name mean **exactly one instance**. There
  is no count to set, and Docker refuses a second container called `api` (AC 11). The host never sleeps.
- **Entry point: a separate API distribution** `aws_cloudfront_distribution.api` (decided here; 026 builds
  `aws_cloudfront_distribution.web` beside it):
  - **origin:** `aws_eip.host.public_dns`, which stays the same when the host is replaced. `http-only` on
    port 80, `origin_read_timeout = 60` (Claude answers can take tens of seconds; the default is 30), and
    `origin_keepalive_timeout = 4`. That stays below uvicorn's 5 s keep-alive, so CloudFront closes idle
    connections first and never reuses one that uvicorn has just closed (otherwise sporadic 502s).
  - **custom origin header** `X-Forwarded-Proto: https`. Every request reaching the origin was HTTPS at the
    viewer (see the viewer policy below), and CloudFront strips a viewer's own copy. So uvicorn sets the
    scheme to `https`, and FastAPI's slash redirects (`/crags` to `/crags/`) point at
    `https://<distribution>/...`.
  - **default behaviour:**
    - all seven methods, cached methods GET and HEAD, `compress = false`;
    - managed cache policy `Managed-CachingDisabled`. It caches nothing, not even error codes (CloudFront
      docs), so a 503 during a deploy is never served stale;
    - managed origin request policy `Managed-AllViewer`. It forwards every header, query and cookie,
      including `Origin` for CORS. It also forwards the viewer's `Host`, so redirects keep the public name
      instead of leaking the origin's EC2 name;
    - `viewer_protocol_policy = "redirect-to-https"`.
  - **certificate:** the default `*.cloudfront.net` one.
  - **`is_ipv6_enabled = false`:** viewers come in over IPv4, so a client cannot dodge its per-IP limit
    by cycling through the many addresses of an IPv6 /64. IPv6-only phones still reach it through their
    carrier's NAT64.
  - **`price_class = "PriceClass_100"`** (Europe and North America), and no logging.
  - *Alternative:* one distribution with the site and `/api/*` paths. The API serves `/search`, `/groups`
    and so on at the root, so that needs a CloudFront Function to strip the prefix, or one behaviour per
    router. It also mixes the API's lifecycle into 026's. Two distributions cost nothing extra, and the
    ticket already expects CORS between two origins (AC 8). Out.
- **TLS: at CloudFront for viewers, plain HTTP from CloudFront to the host, TLS from the backend to
  Postgres.**
  - HTTPS to the origin would need a certificate from a public CA for the origin's name. CloudFront refuses
    self-signed ones (docs above).
  - The only name we have is AWS's `ec2-...compute.amazonaws.com`, which is not our domain. A custom domain
    is out of scope.
  - ACM certificates cannot be installed on an EC2 instance unless exported, and exporting needs our own
    domain too. A CloudFront VPC origin needs a private subnet, and a private subnet needs the 35 USD NAT
    (024).
  - What travels unencrypted between CloudFront and the host: search text, group names, member names and
    grades. There are no passwords and no logins. Written in the runbook as a trade-off; the upgrade path is
    a custom domain.
  - Postgres: `PGSSLMODE=verify-full` with `PGSSLROOTCERT=/tls/server.crt`, which is 024's self-signed cert
    for `db`, mounted read-only (AC 5).
- **Origin lock:** the security group's only inbound rule is TCP 80 from the managed prefix list
  `com.amazonaws.global.cloudfront.origin-facing`.
  - Another AWS customer's distribution could still point at the host. It would get the same API with the
    same per-viewer limits and the same daily cap, because CloudFront always appends the real viewer
    address.
  - A secret origin header checked by the app would close that, but it is app code, so it is a follow-up
    if ever needed (Risks).
- **Client address (AC 10, 15): uvicorn's own proxy-header handling, trusting exactly CloudFront's ranges.**
  - `FORWARDED_ALLOW_IPS` is the comma-joined CIDRs of that same prefix list, rendered by Terraform from
    `data.aws_ec2_managed_prefix_list`.
  - Checked in the locked uvicorn 0.53.0 (`middleware/proxy_headers.py`): with a list, it walks
    `X-Forwarded-For` **from the right** and takes the first address that is not trusted. That is the
    viewer address CloudFront appended. With `*` it takes the **leftmost** entry, which the viewer controls:
    a forged `X-Forwarded-For: 1.2.3.4` would give every request a new rate-limit bucket. So `*` is never
    used.
  - The access log and `get_remote_address` both read the address uvicorn sets, so the logs show the real
    client too.
  - *Alternative:* `CloudFront-Viewer-Address` through an origin request policy, plus a custom
    `key_func` and a middleware so the logs agree. That is app code for the same result. Out.
  - *Trade-off accepted:* if AWS adds a range before the next `terraform apply`, requests from it are keyed
    by the edge address. Several viewers then share one bucket, which fails safe: the limit gets stricter,
    never spoofable. The runbook says that `apply` refreshes the list.
- **Migrations: a one-off container on the host before the restart**, inside `deploy-api.sh`:
  `docker run --rm --network cragmatch ... <image> alembic upgrade head`. The old container keeps serving
  meanwhile.
  - If it fails, the script exits 1 before the restart, so the old version stays live and the deploy is red
    (AC 3). Postgres DDL is transactional, so a failed migration leaves no half-applied schema.
  - *Alternatives:* migrating at container start runs it on every restart and inside the health window. A
    workflow step would need the database reachable from GitHub. Both out.
  - **A rollback must skip migrations:** an older image's Alembic does not know a newer revision and fails
    with "Can't locate revision". The SSM document therefore has `runMigrations` (`yes` or `no`).
- **Planner tables:** after `/health` is good, the deploy calls `GET /planner/graph` on the host. That runs
  `get_trip_planner()`, so `PostgresSaver.setup()` runs at deploy time, before friends' traffic, with no
  other process holding a transaction (the CLAUDE.md trap). The database user is a superuser (024), so the
  concurrent index builds are allowed. Every later process start repeats the check, which is cheap (015).
- **Secrets and settings** (AC 6). All of them live in SSM Parameter Store under `/cragmatch/`:
  - `/cragmatch/api/anthropic_api_key` and `/cragmatch/api/voyage_api_key`: SecureString **slots** made by
    Terraform with `value_wo = "unset"` and `value_wo_version = 1`. They are write-only, so neither the
    placeholder nor the user's real key is ever in the plan or the state. The user overwrites them once in
    the console.
    - *Alternative:* `ignore_changes = [value]`. Out, because refresh would read the real key back into the
      state.
  - `/cragmatch/api/settings`: a Standard **String** (not secret), `KEY=value` lines rendered by Terraform:
    the four non-secret database parts, `PGSSLMODE`, `PGSSLROOTCERT`, `FORWARDED_ALLOW_IPS`,
    `CRAGMATCH_CORS_ORIGINS` and the two daily caps. A precondition keeps it under the 4 KB Standard limit.
  - `/cragmatch/deploy/host_instance_id` and `/cragmatch/deploy/api_url`: Strings the workflow reads. Both
    change by themselves when the host is replaced, so there is no GitHub variable to keep in step.
  - On the host, `render-api-environment.sh` (the unit's `ExecStartPre`, and step 3 of a deploy) writes
    `/etc/cragmatch/api-environment` (root, 0600). It is never named `*.env`, because the hook blocks that.
    If a key slot still says `unset`, it fails with the runbook step to follow.
  - Containers get no AWS credentials (IMDSv2 hop limit 1, 024). The host passes them everything through
    `--env-file`.
- **Deploy transport: a custom SSM Command document** `cragmatch-deploy-api` instead of
  `AWS-RunShellScript`. Its parameters are `imageTag` (`allowedPattern ^[0-9a-f]{40}$`) and `runMigrations`
  (`yes`/`no`). It runs only `/opt/cragmatch/deploy-api.sh {{ imageTag }} {{ runMigrations }}`, with a
  900 s timeout. So the GitHub role can deploy a commit, but it cannot run arbitrary commands as root on
  the host.
- **What is live:** `/srv/cragmatch/api/current-image` and `previous-image` on the **data volume**, each
  one `API_IMAGE=<repo>:<sha>` line. The unit reads it as an `EnvironmentFile`. A replaced host therefore
  starts the last deployed image by itself, and the unit's `ConditionPathExists` keeps it quiet before the
  first deploy.
- **Logs: CloudWatch Logs** group `/cragmatch/api`, 14 days, through Docker's `awslogs` driver on the `api`
  container only.
  - The driver runs in the host's Docker daemon (hop limit 1 is fine), uses `mode=non-blocking` so a
    CloudWatch hiccup never blocks a request, and Docker's dual logging keeps `docker logs api` working.
  - Cost 0 within 5 GB (table).
  - *Alternative:* journald, as 024 set as the default driver. Also 0, but it needs an SSM session to read,
    and the logs are lost when the host is replaced. The migration container and Postgres stay on journald.
  - The runbook reads them with `aws logs tail /cragmatch/api --since 1h --follow` (AC 15).
- **Health check:**
  - on the host, `curl -fsS http://127.0.0.1/health` must contain `"database":"connected"` within 120 s,
    then `/planner/graph` must answer;
  - in the workflow, the same `/health` through the distribution, with retries. No Docker `HEALTHCHECK`
    (021).
  - Automatic return: if the new container is not healthy in time, the script writes `previous-image`
    back, restarts and exits 1. The deploy is red and the previous version serves again. The migration is
    not undone (AC 16).
- **Deploy workflow:** `.github/workflows/deploy.yml`, `name: Deploy`.
  - Trigger: `workflow_run` on `CI` (`types: [completed]`, `branches: [main]`), plus `workflow_dispatch`
    for redeploys and rollbacks of an **existing** image. A dispatch never builds, so only commits that
    passed CI on `main` are ever built.
  - Build on `ubuntu-24.04-arm` natively. Building under QEMU is slower and is only the fallback if that
    label ever goes away.
  - *Alternative:* a job in `ci.yml` with `needs: [tests, ruff, eslint]`, which 018 also allows. A separate
    file keeps `ci.yml` exactly as it is and gives the dispatch inputs a home. 026 adds its `web` job to the
    same file.
- **Public repository:** workflow logs are public. The workflow masks the host id and the API address
  (`::add-mask::`), and `configure-aws-credentials` masks the account id. The deploy script prints commit
  SHAs and statuses only. The site stays unlisted.

## Ticket check
Checked against the code on 2026-10-14 (`uv run pytest --collect-only -q`: **199 tests**; 262 expected once
017 to 024 are in, from their plans). No other test was run. No `terraform` command ran: `infra/` does not
exist yet (024 is not delivered), and nothing touched AWS.
- **Correct:**
  - The limits are `10/minute` on `/search/natural` and `/search/similar`, keyed by `get_remote_address`
    (`core/rate_limit.py`).
  - `fastapi run` turns proxy headers on and leaves `forwarded_allow_ips` to uvicorn's `FORWARDED_ALLOW_IPS`
    (`fastapi_cli/cli.py`, `uvicorn/config.py:363`, default `127.0.0.1,::1`).
  - `/health` runs `SELECT 1`. The planner calls no paid API and has no rate limit (`routers/planner.py`).
  - `setup()` runs on the first planner request of each process (`get_trip_planner`, `lru_cache`).
  - Every locked package has a Linux arm64 or pure-Python wheel: 115 packages checked in `uv.lock`, none
    missing. `psycopg[binary]` brings its own libpq, which reads `PGSSLMODE` and `PGSSLROOTCERT`.
- **Wrong or missing in the ticket, and what is true:**
  - **AC 14 (wake-up):** dropped. The backend never sleeps (one always-on host, 024). The only "sleep" is
    024's optional cut 2, which is a planned outage and not a wake-up.
  - **AC 8:** the live site's address only exists in 026. 025 builds the allowed-origin slot
    (`var.cors_origins`, default `http://localhost:5173`, so a local `npm run dev` can use the cloud API).
    It proves that an unlisted origin is refused. 026 sets the value to its distribution's origin and checks
    it end to end.
  - **AC 15, "not the load balancer's":** there is no load balancer. The address to avoid is CloudFront's
    edge address.
  - **The ticket asks to "measure the container" before choosing:** the choice does not depend on the
    number. The host has 2 GiB plus 1 GiB swap, and ticket 021's hand-off gives the measured memory. This
    plan sets no hard memory limit, gives the API an OOM score of 500 so the kernel kills it before
    Postgres, and the runbook measures with `docker stats` (024's "Before 1 January 2027" section needs it).
  - **"Trusting forwarded headers" in the earlier plan:** the obvious `FORWARDED_ALLOW_IPS=*` is unsafe
    behind CloudFront. uvicorn then takes the leftmost `X-Forwarded-For` entry, which a client can forge
    (Decisions).
  - **Missing: rollbacks cannot run `alembic upgrade head`** with an older image (unknown revision). The
    plan adds `runMigrations=no`.
  - **The data load "from a private network":** the database is not in a private subnet. It is on the
    host's loopback and Docker network, in a public subnet with no inbound rule (024). The access path is
    SSM port forwarding from the laptop. `import_stays` stays on the laptop (Overpass and its cache).
  - **The repository is public** (`gh repo view`, 2026-10-14). Workflow logs are public, hence the masking.
    Also, 024's note that "GitHub environments need a paid plan" applies to private repositories only.
    Branch-only trust stays as 024 built it.
  - **Open questions:** OIDC yes (024 built it). A slow first request is moot (never sleeps). The data load
    goes from the laptop through port forwarding with 023's `load_data`. The first deploy waits for 022 by
    construction, because 022 is delivered before 025 and the manual check confirms `daily_spend` exists.
- **Still open from 022 (not this ticket):** the suggested `max_length` on the two query fields before the
  paid endpoints go public. It is the user's call. The cap bounds the cost either way.

## Delivery
One build, one review, one commit for the whole ticket (no increments). There is no migration and no app
code. Build order: Terraform, host files, Terraform tests, backend test, workflow, docs.

### 1. The backend image in ECR, running on the host behind an API CloudFront distribution, deployed from GitHub after CI, with logs, secrets, a data load path and a runbook
**Files:**

*Terraform, `infra/main/` (024's stack; policies as `jsonencode`, as in 024)*
- `variables.tf`, new variables, each with a description:
  - `cors_origins` (string, default `"http://localhost:5173"`). Validation: every comma-separated part
    matches `^https?://[A-Za-z0-9.-]+(:[0-9]+)?$`, which rules out `*`, paths and a trailing `/`. The comment
    says 026 sets it to the site's origin.
  - `claude_daily_cap_usd` (number, default 1.00) and `voyage_daily_cap_usd` (number, default 0.50), each
    with validation `>= 0`. The comment says these are 022's defaults, and 0 switches that provider off.
- `terraform.tfvars.example`: the three, commented out, with their defaults.
- `registry.tf` (new):
  - `aws_ecr_repository.api` (`cragmatch-api`, `IMMUTABLE`, `scan_on_push = true`, `force_delete = true`,
    each with a why-comment);
  - `aws_ecr_lifecycle_policy.api` with the two rules above. The comment says why 5: rollback depth against
    0.10 USD per GB-month.
- `api.tf` (new):
  - `data "aws_ec2_managed_prefix_list" "cloudfront"` (name
    `com.amazonaws.global.cloudfront.origin-facing`).
  - `aws_vpc_security_group_ingress_rule.cloudfront_http`: TCP 80 to 80 from that prefix list, on 024's host
    security group. The comment says it is the only inbound rule, and that the list weighs about 55 of the 60
    rules a group allows.
  - `locals`:
    - `api_settings`, a map:
      - `CRAGMATCH_POSTGRES_USER`, `_DB` (024's values), `_HOST = "db"`, `_PORT = "5432"`;
      - `PGSSLMODE = "verify-full"`, `PGSSLROOTCERT = "/tls/server.crt"`;
      - `FORWARDED_ALLOW_IPS = join(",", sort([for e in ...entries : e.cidr]))`;
      - `CRAGMATCH_CORS_ORIGINS = var.cors_origins`;
      - the two caps as `format("%.2f", ...)`.
    - `api_settings_text`, the lines `KEY=value` joined with `"\n"` (map order is sorted, so it is
      deterministic).
    - Comments: why each trust or TLS value exists, why `*` must never be used, and that the password and
      keys are deliberately not here.
  - `aws_ssm_parameter.api_settings`: `/cragmatch/api/settings`, `String`, `Standard`, value
    `local.api_settings_text`, plus a `lifecycle { precondition }` that the length is at most 4096, with an
    error message naming the Standard limit.
  - `aws_ssm_parameter.anthropic_api_key` and `.voyage_api_key`: `/cragmatch/api/anthropic_api_key` and
    `/cragmatch/api/voyage_api_key`, `SecureString`, `value_wo = "unset"`, `value_wo_version = 1`. The
    comment says the user types the real key in the console; never bump the version (it would write `unset`
    back); write-only keeps both values out of the plan and the state.
  - `aws_cloudwatch_log_group.api`: `/cragmatch/api`, `retention_in_days = 14`.
  - Host role additions, as **separate** inline policies on `host_role_name`, so 024's
    `host_role_reads_only_cragmatch_parameters` stays true:
    - `cragmatch-host-ecr-pull`: `ecr:GetAuthorizationToken` on `*`; `ecr:BatchGetImage`,
      `ecr:GetDownloadUrlForLayer` and `ecr:BatchCheckLayerAvailability` on the repository ARN;
    - `cragmatch-host-api-logs`: `logs:CreateLogStream` and `logs:PutLogEvents` on the group's streams. The
      developer checks the provider's `arn` format for the log group (with or without `:*`).
  - `aws_ssm_parameter.deploy_host_instance_id` (`/cragmatch/deploy/host_instance_id`, `String`,
    `aws_instance.host.id`) and `.deploy_api_url` (`/cragmatch/deploy/api_url`, `String`,
    `"https://${aws_cloudfront_distribution.api.domain_name}"`, no trailing slash).
- `cdn.tf` (new):
  - `data "aws_cloudfront_cache_policy" "caching_disabled"` (name `Managed-CachingDisabled`) and
    `data "aws_cloudfront_origin_request_policy" "all_viewer"` (name `Managed-AllViewer`);
  - `aws_cloudfront_distribution.api` exactly as in Decisions:
    - origin id `host`, `custom_origin_config` with `http_port = 80`, `https_port = 443`,
      `origin_protocol_policy = "http-only"`, `origin_ssl_protocols = ["TLSv1.2"]`,
      `origin_read_timeout = 60`, `origin_keepalive_timeout = 4`;
    - `custom_header { name = "X-Forwarded-Proto", value = "https" }`;
    - `restrictions { geo_restriction { restriction_type = "none" } }`;
    - `comment = "CragMatch API"`.
    One why-comment per non-default setting. A block comment says that 026's site is a **separate**
    distribution and must not add behaviours here.
- `deploy.tf` (new):
  - `aws_ssm_document.deploy_api`: `cragmatch-deploy-api`, `Command`, `JSON`, schema 2.2. Content:
    - parameters `imageTag` (pattern above) and `runMigrations` (`allowedValues` `["yes", "no"]`, default
      `yes`);
    - one `aws:runShellScript` step with `timeoutSeconds` 900, running only
      `/opt/cragmatch/deploy-api.sh {{ imageTag }} {{ runMigrations }}`.
  - `aws_iam_role_policy.github_deploy_backend` (`cragmatch-deploy-backend`) on 024's
    `cragmatch-github-deploy` role, with five statements:
    1. `EcrLogin`: `ecr:GetAuthorizationToken` on `*`.
    2. `PushApiImage`: `BatchCheckLayerAvailability`, `BatchGetImage`, `CompleteLayerUpload`,
       `DescribeImages`, `GetDownloadUrlForLayer`, `InitiateLayerUpload`, `PutImage`, `UploadLayerPart` on
       the repository ARN only.
    3. `RunDeployDocument`: `ssm:SendCommand` on exactly the instance ARN and the document ARN.
    4. `ReadCommandResult`: `ssm:GetCommandInvocation` on `*` (it supports no resource).
    5. `ReadDeployParameters`: `ssm:GetParameter` on `parameter/cragmatch/deploy/*`.
    The comment says 026 adds its own separate policy for S3 and the invalidation.
- `host.tf` (edit):
  - `host-settings` gains `ECR_REPOSITORY_URL`, `API_SETTINGS_PARAMETER`, `ANTHROPIC_KEY_PARAMETER`,
    `VOYAGE_KEY_PARAMETER` and `API_LOG_GROUP`. These are names, not values.
  - `write_files` gains the four host files below with `permissions` 0755 (scripts) or 0644 (unit).
  - The comment notes that changing any file under `host/` changes `user_data` and so **replaces the host**
    on apply: a few minutes down, data kept (024's drill). If the 16 KB limit is reached, switch to
    `user_data_base64 = base64gzip(local.user_data)`, which cloud-init reads.
- `outputs.tf`: `api_url`, `api_distribution_id`, `api_distribution_domain`, `ecr_repository_url`,
  `deploy_document_name`, `api_log_group`. None is sensitive.

*Host files, `infra/main/host/` (bash, `set -euo pipefail`, shellcheck-clean, never `set -x`, one why-comment
per step)*
- `cragmatch-api.service` (new):
  - `[Unit]`:
    - `Requires=docker.service cragmatch-db.service`, with `After=` the same plus `network-online.target`
      and `Wants=network-online.target`. The comment says a database restart restarts the API, so no pool
      keeps dead connections.
    - `RequiresMountsFor=/srv/cragmatch`.
    - `ConditionPathExists=/srv/cragmatch/api/current-image`, so the unit stays quiet until the first
      deploy.
  - `[Service]`:
    - `EnvironmentFile=/opt/cragmatch/host-settings` and `EnvironmentFile=/srv/cragmatch/api/current-image`;
    - `ExecStartPre=/opt/cragmatch/render-api-environment.sh`;
    - `ExecStartPre=/opt/cragmatch/pull-api-image.sh ${API_IMAGE}`;
    - `ExecStartPre=-/usr/bin/docker rm -f api`;
    - `ExecStart=/usr/bin/docker run --rm --name api --network cragmatch -p 80:8000
      --env-file /etc/cragmatch/api-environment -v /srv/cragmatch/pgtls/server.crt:/tls/server.crt:ro
      -v /srv/cragmatch/hf:/home/cragmatch/.cache/huggingface --oom-score-adj 500 --log-driver awslogs
      --log-opt awslogs-region=${REGION} --log-opt awslogs-group=${API_LOG_GROUP} --log-opt mode=non-blocking
      --log-opt max-buffer-size=4m ${API_IMAGE}`. Nothing follows the image, so 021's CMD with one worker
      applies.
    - `ExecStop=/usr/bin/docker stop -t 20 api`, `TimeoutStopSec=40`, `Restart=always`, `RestartSec=5`.
  - The comment says the HF cache is on the data volume, so the tokenizer is downloaded once, ever (AC 7).
- `render-api-environment.sh` (new):
  - Source `host-settings`. Read the four parameters with `aws ssm get-parameter --with-decryption --query
    Parameter.Value --output text`: settings, db password, both keys.
  - If a key is `unset` or empty, exit 1 with "Enter <name> in Parameter Store first (infra/RUNBOOK.md,
    Backend: first deploy)".
  - Under `umask 077`, write a temp file in `/etc/cragmatch`: the settings text, then
    `CRAGMATCH_POSTGRES_PASSWORD=`, `CRAGMATCH_ANTHROPIC_API_KEY=` and `CRAGMATCH_VOYAGE_API_KEY=` lines.
    Then `mv` it to `api-environment`. It prints only "API environment written".
- `pull-api-image.sh <image>` (new): if `docker image inspect` finds the image, stop. Otherwise
  `aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin
  "${ECR_REPOSITORY_URL%%/*}"`, then `docker pull`. The comment says why it exists: a replaced host has no
  images, and the unit pulls the last deployed one by itself.
- `deploy-api.sh <sha> <yes|no>` (new). It checks both arguments again (pattern and set) and prints a
  `== step` line for each step:
  1. `install -d` `/srv/cragmatch/api` (root, 0755) and `/srv/cragmatch/hf` (owner 10001, the image's
     user).
  2. `pull-api-image.sh "$ECR_REPOSITORY_URL:$sha"`.
  3. `render-api-environment.sh`.
  4. If migrations are on: `docker run --rm --network cragmatch --env-file /etc/cragmatch/api-environment
     -v /srv/cragmatch/pgtls/server.crt:/tls/server.crt:ro <image> alembic upgrade head`. On failure print
     "Migration failed: the previous version keeps serving" and exit 1. The comment says why it comes before
     the restart (AC 3), and that each migration must work with the code before it.
  5. Save the old `current-image` as a variable, then write the new one atomically (temp file plus `mv`).
  6. `systemctl restart cragmatch-api`.
  7. Wait up to 120 s for `curl -fsS http://127.0.0.1/health` to contain `"database":"connected"`, then
     `curl -fsS http://127.0.0.1/planner/graph`. The comment says the second call creates or checks the
     planner's tables now, with no other transaction open.
  8. On failure: `docker logs --tail 80 api`, which never contains secrets (021's `hide_input_in_errors`).
     Then, if there was an old image, write it back, restart, wait for health (best effort), print
     "Returned to <old sha>; the migration was not undone", and **exit 1** either way.
  9. On success: write `previous-image`, run `docker image prune -af --filter label=cragmatch.component=api`
     (only API images that no container uses), and print "Live: <sha>".
- `host-setup.sh` (edit, 024's script), a new last step. It runs `install -d` for both directories, installs
  `cragmatch-api.service`, runs `systemctl daemon-reload` and `systemctl enable cragmatch-api`, then
  `systemctl start cragmatch-api`. Before the first deploy the condition skips the start.
- `/srv/cragmatch/pgtls/server.crt`: the developer checks that 024's `openssl` step leaves it world-readable
  (0644), because the API runs as uid 10001. Only the key is 0600.

*Terraform tests*
- `infra/main/tests/backend.tftest.hcl` (new): `mock_provider "aws"` with the shared `override_data`, the
  same `variables {}` placeholders as 024, and `command = apply` where computed values are read. The
  overrides are:
  - the prefix list: `id = "pl-4fa04526"`, entries `130.176.0.0/18` and `15.158.0.0/16`;
  - the two CloudFront policies: ids `4135ea2d-6df8-44a3-9df3-4b5a84be39ad` and
    `216adef6-5c7f-47e4-b989-5492eafa07d3`.
  Add the same `override_data` to `foundation.tftest.hcl`'s mock provider (or move both into a
  `tests/mocks/aws.tfmock.hcl` used through `source`), so its 19 runs keep passing. If 024's
  `host_allows_https_out_only` asserts that no ingress rule exists, narrow it to egress: the one ingress
  rule is asserted here.

*Backend test (no app change)*
- `backend/tests/test_client_address.py` (new), described under Tests.

*Workflow (`ci.yml` and `terraform.yml` untouched)*
- `.github/workflows/deploy.yml` (new), `name: Deploy`:
  - `on`: `workflow_run` (`workflows: [CI]`, `types: [completed]`, `branches: [main]`) and
    `workflow_dispatch` with inputs `image_tag` (required, a 40-character SHA already in ECR) and
    `skip_migrations` (boolean, default false; true for a rollback).
  - `permissions: contents: read` at the top. `concurrency: { group: deploy, cancel-in-progress: false }`,
    which 026's job shares.
  - Job `backend`, name `Deploy backend`, `runs-on: ubuntu-24.04-arm`, `timeout-minutes: 30`, job
    permissions `contents: read` and `id-token: write`.
  - Its `if` is `github.event_name == 'workflow_dispatch' || (github.event.workflow_run.conclusion ==
    'success' && github.event.workflow_run.event == 'push' && github.event.workflow_run.head_repository.full_name
    == github.repository)`. The comment says why: only a green CI on a push to this repository's `main`,
    never a pull request run or a fork's branch named `main` (AC 12).
  - Steps:
    1. **Pick the tag:** the input or `github.event.workflow_run.head_sha`, checked against
       `^[0-9a-f]{40}$`. For `workflow_run`, compare it with `git ls-remote origin refs/heads/main`; if
       `main` has moved on, end with a notice "a newer commit is on main; its own run deploys it", so a
       slow, older CI run never deploys over a newer one.
    2. Checkout at that SHA (`actions/checkout@v7`, `workflow_run` only).
    3. `aws-actions/configure-aws-credentials@v6` with `role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}`,
       `aws-region: ${{ vars.AWS_REGION }}` and `mask-aws-account-id: true`.
    4. Read `/cragmatch/deploy/host_instance_id` and `/cragmatch/deploy/api_url` and `::add-mask::` both
       (the logs are public). Put them in step outputs.
    5. `aws-actions/amazon-ecr-login@v2`.
    6. `aws ecr describe-images --repository-name cragmatch-api --image-ids imageTag=$TAG` decides "exists".
       A dispatch with a missing tag fails here with a clear message.
    7. Only if missing (so only on `workflow_run`):
       - `docker/setup-buildx-action@v4`;
       - `docker/build-push-action@v7` with `context: backend`, `platforms: linux/arm64`, `push: true`,
         `provenance: false`, `sbom: false` (one manifest per tag, nothing untagged for the lifecycle to
         count), `labels: cragmatch.component=api`, the tag, `cache-from: type=gha` and
         `cache-to: type=gha,mode=max`.
       A re-run of the same SHA skips the build, because tags are immutable.
    8. `aws ssm send-command --document-name cragmatch-deploy-api --instance-ids $HOST --parameters
       imageTag=$TAG,runMigrations=<yes|no> --timeout-seconds 600 --query Command.CommandId --output text`.
       Then `aws ssm wait command-executed` (its non-zero exit is caught). Then always print
       `get-command-invocation`'s `Status`, `StandardOutputContent` and `StandardErrorContent`. Fail unless
       the status is `Success` (AC 3, 12).
    9. **Through CloudFront:** `curl -fsS --retry 6 --retry-delay 5 --retry-all-errors "$API_URL/health"`
       must contain `"database":"connected"` (AC 1).
  - No `secrets.` anywhere, and no AWS key. Actions are at the majors above.

*Docs*
- `infra/RUNBOOK.md`, new sections after 024's, PowerShell, run by the user:
  14. **Backend: what it adds:**
      - the request path in one line (phone, CloudFront HTTPS, host port 80 for CloudFront only, the `api`
        container, `db` over TLS);
      - the TLS trade-off;
      - "exactly one instance; scaling out needs a shared rate-limit store (a new ticket)";
      - "never sleeps; cut 2 means planned downtime";
      - the cost rows above with their sources and date.
  15. **First deploy (order matters):**
      1. Apply this commit's Terraform from the working copy **before pushing it**. The host is replaced
         once (data kept), and the distribution takes 5 to 15 minutes.
      2. Enter both keys in the console: Systems Manager, Parameter Store, `/cragmatch/api/anthropic_api_key`,
         Edit, paste, Save; the same for Voyage. Never on a command line. A CLI variant uses
         `Read-Host -AsSecureString`.
      3. Push. In Actions, `CI` and then `Deploy` go green. Or run `Deploy` by hand after the first build.
      4. Run `Invoke-RestMethod ((terraform output -raw api_url) + "/health")`.
      5. Run the data load (section 16).
  16. **Load the data (once, safe to repeat):**
      - Window 1: `aws ssm start-session --target (terraform output -raw host_instance_id) --document-name
        AWS-StartPortForwardingSession --parameters portNumber=5432,localPortNumber=15432`. Shorthand
        syntax, so PowerShell 5.1 has no quotes to mangle.
      - Window 2, in `backend/`:
        - `$p = aws ssm get-parameter --name /cragmatch/db/password --with-decryption --query
          Parameter.Value --output text`;
        - `$env:CRAGMATCH_POSTGRES_URL = "postgresql://cragmatch:$p@127.0.0.1:15432/cragmatch?sslmode=require"`;
        - `Remove-Variable p`;
        - `uv run python -m app.scripts.load_data`. Check that the first line shows
          `127.0.0.1:15432/cragmatch`, then answer `y`. It makes 1 Voyage request with the laptop's key, and
          `import_stays` runs on the laptop's Overpass cache.
        - `Remove-Item Env:CRAGMATCH_POSTGRES_URL`, then close the window.
      - **Never run pytest in that window.** Wait a minute before a vibe search (Voyage allows 3 a minute).
        A second run prints "0 added".
  17. **Redeploy and what is live:**
      - a push to `main` deploys after `CI`;
      - `aws ecr describe-images --repository-name cragmatch-api --query "sort_by(imageDetails,&imagePushedAt)[-5:].imageTags"`
        lists the last five;
      - the `Deploy` run's output says "Live: <sha>";
      - on the host, `cat /srv/cragmatch/api/current-image`.
  18. **Logs:**
      - `aws logs tail /cragmatch/api --since 1h --follow`. Each access line starts with the client's
        address;
      - the deploy output is in the `Deploy` run (public, masked; it never shows secrets);
      - the migration and Postgres logs: `journalctl -u cragmatch-db` and `docker logs api` in a session;
      - the boot log: `/var/log/cloud-init-output.log`.
  19. **Roll back:**
      - Actions, `Deploy`, "Run workflow" from `main` with `image_tag` = the previous SHA and
        `skip_migrations` ticked;
      - or from the laptop: `aws ssm send-command --document-name cragmatch-deploy-api --instance-ids <id>
        --parameters imageTag=<sha>,runMigrations=no`;
      - **a rollback never undoes a migration.** Rule: migrations only add (columns nullable or with
        defaults, no renames or drops in the same release), so the previous image still works;
      - an unhealthy deploy returns by itself.
  20. **Change keys, caps, CORS:**
      - keys: overwrite in Parameter Store, then `sudo systemctl restart cragmatch-api` in a session (or run
        `Deploy` by hand with the live SHA);
      - caps and CORS: edit `terraform.tfvars`, apply, then restart the same way;
      - the prefix list: `terraform apply` refreshes `FORWARDED_ALLOW_IPS`, then restart.
  21. **Memory:** `docker stats --no-stream` after a vibe search, a natural search and a planner run. The
      numbers feed 024's "Before 1 January 2027" choice.
  22. **Destroy, backend part:**
      - `terraform destroy` also removes the distribution (disabling it takes minutes), the repository with
        its images, the log group and both key parameters (re-enter them after a re-create);
      - what stays: 024's list.
  23. **Checks of 025:** the "Check by hand" list below, as commands.
- `README.md`:
  - Project structure:
    - `infra/main/` line gains "ECR, API CloudFront distribution, deploy document";
    - `infra/main/host/` gains "API unit, deploy, pull and environment scripts";
    - a `.github/workflows/deploy.yml` line ("after CI on main: build the arm64 API image, push to ECR,
      deploy through SSM");
    - `backend/tests/` does not list test files (convention, as 023 found).
  - The "Deploying to AWS" section (024) gains two lines: pushes to `main` deploy the backend after `CI`
    passes, and rollbacks and logs are in the runbook.
- `CLAUDE.md`: **not edited by the developer.** Suggest these in the hand-off:
  - Traps:
    - "the deployed API trusts X-Forwarded-For only from CloudFront's ranges (FORWARDED_ALLOW_IPS); never
      set it to `*`";
    - "migrations must work with the previous release: a rollback skips them";
    - "workflow logs are public: mask hosts and addresses".
  - Commands: `aws logs tail /cragmatch/api --follow`.

**Reuses:**
- 021's image as it is: CMD with one worker, `PORT` default, `HF_HOME`, uid 10001, CMD replaced by
  `alembic upgrade head`.
- 021's settings contract: the five `CRAGMATCH_POSTGRES_*` parts, `CRAGMATCH_CORS_ORIGINS`, libpq's
  `PGSSLMODE` and `PGSSLROOTCERT`.
- 022's cap settings and their defaults.
- 023's `load_data` and its target label and confirmation.
- 024's host, network, Elastic IP, TLS cert for `db`, `host-settings`, `host-setup.sh` pattern, systemd
  style, `/cragmatch/*` parameters, deploy role, repository variables `AWS_DEPLOY_ROLE_ARN` and
  `AWS_REGION`, the `Terraform` workflow (fmt, validate, test, tflint, shellcheck over `infra/main/host/*.sh`)
  and its runbook.
- 018's job names and the rule "add a workflow, don't edit `ci.yml`".
- uvicorn's `ProxyHeadersMiddleware` and `FORWARDED_ALLOW_IPS` instead of app code.
- AWS-managed pieces: CloudFront managed policies, the managed prefix list, the SSM Command document and
  port forwarding, CloudWatch Logs through Docker's driver.
- In tests: the `client` fixture's dependency overrides, `test_natural_api.py`'s fake chain and
  `monkeypatch.setattr(limiter, "enabled", True)` with `limiter.reset()`.

**Tests:**

*`backend/tests/test_client_address.py` (new, 4 tests).*
- Setup:
  - A helper builds `TestClient(ProxyHeadersMiddleware(app, trusted_hosts="198.18.0.0/15"),
    client=(peer, 50000))`. That is the same wrapping uvicorn applies under `fastapi run` with
    `FORWARDED_ALLOW_IPS`; the module docstring says so and names 025.
  - The tests depend on the `client` fixture for its dependency overrides, and swap
    `natural_search.get_parse_chain` for a fake as `test_natural_api.py` does. They use whatever 022 added
    to keep the spend on the test database (read `tests/conftest.py` at build time).
  - The limiter is switched on and reset per test. No network.
- `test_behind_cloudfront_each_viewer_has_its_own_limit`: peer `198.18.0.10`. Ten natural searches with
  `X-Forwarded-For: 203.0.113.7` give 200, the eleventh gives 429. Then one with `198.51.100.9` gives 200
  (AC 10).
- `test_a_forged_forwarded_for_does_not_escape_the_limit`: after ten from `203.0.113.7`, a request with
  `X-Forwarded-For: 192.0.2.1, 203.0.113.7` gives 429. That is what CloudFront forwards when the viewer sends
  its own header (AC 10).
- `test_a_caller_outside_cloudfront_cannot_choose_its_address`: peer `192.0.2.50` (not trusted). Eleven
  requests, each with a different `X-Forwarded-For`, end with 429 (AC 5, AC 10).
- `test_redirects_keep_the_public_https_address`: peer trusted, `base_url="http://d111.cloudfront.net"`,
  header `X-Forwarded-Proto: https`. `GET /crags` without following redirects gives 307 with
  `location == "https://d111.cloudfront.net/crags/"` (the custom origin header plus `Managed-AllViewer`).

*`infra/main/tests/backend.tftest.hcl` (new, 15 runs, offline, mocked AWS).*
- `registry_keeps_immutable_tags_and_the_last_five_images`: the name is `cragmatch-api`, `IMMUTABLE`, scan
  on push. The decoded lifecycle has rule 1 (untagged, `sinceImagePushed` 1 day, expire) and rule 2 (`any`,
  `imageCountMoreThan` 5) (AC 13, 16).
- `only_cloudfront_reaches_the_api_port`: the ingress rule is TCP 80 to 80 with `prefix_list_id ==
  "pl-4fa04526"` and no `cidr_ipv4`, on the host security group (AC 5).
- `api_distribution_passes_every_request_to_the_host`, asserting:
  - one origin, whose domain is the Elastic IP's DNS, `http-only`, port 80, read timeout 60, keep-alive 4,
    and the `X-Forwarded-Proto` header;
  - the default behaviour: 7 methods, the CachingDisabled and AllViewer ids, `redirect-to-https`;
  - the default certificate, IPv6 off, `PriceClass_100`
  (AC 1, 10, 15).
- `trusted_proxies_are_exactly_the_cloudfront_ranges`: the settings text contains
  `FORWARDED_ALLOW_IPS=130.176.0.0/18,15.158.0.0/16` (sorted the same way) and no `*` (AC 10, 15).
- `api_settings_use_the_database_over_verified_tls_and_hold_no_secret`: it contains
  `CRAGMATCH_POSTGRES_HOST=db`, `PGSSLMODE=verify-full`, `PGSSLROOTCERT=/tls/server.crt`,
  `CRAGMATCH_CORS_ORIGINS=http://localhost:5173`, `CRAGMATCH_CLAUDE_DAILY_CAP_USD=1.00` and
  `CRAGMATCH_VOYAGE_DAILY_CAP_USD=0.50`, and none of `PASSWORD`, `API_KEY` or `sk-` (AC 5, 6, 7, 8).
- `api_settings_fit_a_standard_parameter`: with 60 overridden entries of the form `130.176.255.0/24`, the
  apply succeeds, the type is `String`, the tier `Standard`, and the length is at most 4096 (AC 10).
- `api_key_slots_are_write_only_secure_strings`: both names, `SecureString`, `value_wo_version == 1`, and
  both `value` and `value_wo` are null after the mocked apply (AC 6).
- `cors_origins_must_be_plain_origins`: `cors_origins = "*"` fails `var.cors_origins` (AC 8).
- `daily_caps_cannot_be_negative`: `claude_daily_cap_usd = -1` fails its variable (AC 7).
- `host_can_pull_the_image_and_write_api_logs_only`: the two new host policies' only actions and resources
  are the ones listed above (AC 6, 15).
- `api_logs_are_kept_two_weeks`: the group is `/cragmatch/api` with 14 days (AC 13, 15).
- `deploy_role_pushes_one_repository_and_sends_one_document`, on the decoded policy:
  - only the five statements;
  - `SendCommand`'s resources are exactly the instance ARN and the document ARN;
  - no `AWS-RunShellScript`, no `iam:`, no `"Action": "*"`;
  - the parameter read is limited to `/cragmatch/deploy/*`
  (AC 12).
- `deploy_document_runs_only_the_deploy_script_with_a_commit_sha`: the decoded content has the `imageTag`
  pattern `^[0-9a-f]{40}$`, `runMigrations` allowed `yes` and `no` with default `yes`, one step whose
  command is exactly the script line, and a timeout of 900 (AC 3, 12, 16).
- `deploy_parameters_name_the_host_and_the_api_url`: the host id parameter equals the instance id, and the
  URL parameter equals `"https://" + domain_name` with no trailing slash. The `api_url` output is the same
  (AC 1, 12).
- `user_data_installs_one_api_unit_and_holds_no_secret`, on `local.user_data`:
  - it contains the exact text of `file("host/cragmatch-api.service")`, `deploy-api.sh`,
    `render-api-environment.sh` and `pull-api-image.sh`;
  - the unit contains `--name api`, `-p 80:8000`, `--network cragmatch`, `--log-driver awslogs`,
    `RequiresMountsFor=/srv/cragmatch` and `ConditionPathExists=/srv/cragmatch/api/current-image`, and
    ends its `ExecStart` with `${API_IMAGE}`;
  - user_data contains no `POSTGRES_PASSWORD=`, `API_KEY=` or `sk-ant`, and is under 16384 bytes
  (AC 6, 11).

*Not Terraform, but checks:* shellcheck over the four new scripts, through 024's workflow glob; tflint
`aws_resource_missing_tags` on the new resources.

**Expected suite:**
- Backend: **266 passed** (262 before this ticket plus 4 in `test_client_address.py`; if the count before
  differs, that count plus 4). `uv run ruff check .` is clean. No frontend change, so no npm check.
- Terraform: `infra/bootstrap` **8 passed** (unchanged), `infra/main` **34 passed** (024's 19 plus 15).
- `terraform fmt -check -recursive infra`, both `validate` runs, tflint and shellcheck all report 0
  problems.

**Check by hand.**

*A. Developer and reviewer, no AWS:*
1. `terraform fmt -check -recursive infra`. Then in `infra/main`: `terraform init -backend=false`,
   `terraform validate` and `terraform test` (34 passed). `infra/bootstrap` still gives 8.
2. Run shellcheck on `infra/main/host/*.sh` if it is installed (CI runs it anyway).
3. From `backend/`:
   `uv run python -c "import yaml; d = yaml.safe_load(open('../.github/workflows/deploy.yml')); print(d['name'], list(d['jobs']), d['jobs']['backend']['runs-on'])"`
   prints `Deploy ['backend'] ubuntu-24.04-arm`. (PyYAML reads `on` as `True`; that is fine.)
4. Greps:
   - `git grep -n "secrets\." .github` finds nothing;
   - `git grep -nE "[0-9]{12}" -- infra .github` finds only `123456789012`;
   - `git grep -n "FORWARDED_ALLOW_IPS=\*\|FORWARDED_ALLOW_IPS: \*" -- infra .github` finds nothing;
   - `git grep -n "set -x" -- infra/main/host` finds nothing.
5. `git diff --stat` shows nothing under `backend/app`, `web/`, `backend/Dockerfile`,
   `.github/workflows/ci.yml` or `.github/workflows/terraform.yml`.
6. `uv run pytest tests/test_client_address.py -x`, then the full suite, 266 passed.
7. Optional, with Docker Desktop: `docker buildx build --platform linux/arm64 backend` builds under
   emulation. The arm runner does it natively.

*B. The user, on the account (runbook section 23):*
1. **AC 1:** `Invoke-RestMethod <api_url>/health` gives `status ok`, `database connected`.
   `Invoke-WebRequest http://<domain>/health -MaximumRedirection 0` gives 301 to `https`.
2. **AC 2:** the first `Deploy` run's output shows `== migrations` with Alembic's "Running upgrade" lines
   before `== restart`. In a session:
   - `sudo docker exec db psql -U cragmatch -d cragmatch -c "select extname from pg_extension"` lists
     `postgis` and `vector`;
   - `\dt` lists `daily_spend` (022) and the planner's checkpoint tables (the warm-up).
3. **AC 3, 12:**
   - a push to `main` gives a green `CI`, then a green `Deploy`;
   - `Deploy` dispatched with `image_tag` = 40 zeros fails at "exists" and changes nothing;
   - set the Voyage slot back to `unset` in the console and dispatch `Deploy` with the live SHA. It goes red
     at the environment step, and `/health` keeps answering (the old container was never stopped). Restore
     the key and dispatch again: green;
   - a throwaway commit on `main` with an unused import (Ruff red) leaves `Deploy` skipped. Revert it, and
     the revert deploys;
   - `gh secret list` is empty.
4. **AC 4:** run section 16. Then in a session, `select count(*)` gives:
   - `crags` 5;
   - `sectors` 13;
   - `langchain_pg_embedding` 13;
   - `stays` more than 5.
   A second `load_data --yes` reports "0 added" everywhere.
5. **AC 5:**
   - `Test-NetConnection <host_public_ip> -Port 80` and `-Port 5432` both give `False`;
   - `aws ec2 describe-security-groups` shows the one prefix-list rule;
   - in a session, `sudo docker exec db psql -U cragmatch -d cragmatch -c "select bool_and(ssl), count(*)
     from pg_stat_ssl join pg_stat_activity using (pid) where client_addr is not null"` gives `t`.
6. **AC 6:**
   - load each key into `$k` without printing it (as in 024's B2); `(terraform state pull) -match
     [regex]::Escape($k)` gives `False`; `Remove-Variable k`;
   - `terraform plan` shows the slots as write-only;
   - `docker history --no-trunc` of the ECR image shows no secret;
   - the `Deploy` logs show no key, no host id and no API domain (masked).
7. **AC 7:**
   - on the deployed API's `/docs`, one natural search and one vibe search answer 200 with reasons;
   - in a session, `select * from daily_spend` shows both providers counted today;
   - `sudo ls /srv/cragmatch/hf/hub` shows the Voyage tokenizer;
   - `sudo systemctl restart cragmatch-api`, then another vibe search works (a minute later, because of
     Voyage's limit).
8. **AC 8 (025's half):**
   - preflight with `Origin: http://localhost:5173` returns that origin in
     `access-control-allow-origin`; with `Origin: https://evil.example` the header is missing;
   - `npm run dev` in `web/` with `$env:VITE_API_URL = <api_url>` searches the cloud data;
   - 026 checks the live site's origin.
9. **AC 9:** start a planner run on a test group through `/docs` and leave it waiting. Then `sudo systemctl
   restart cragmatch-api`, and the answer continues it. Dispatch `Deploy` with the live SHA: the group, its
   members and the run are still there.
10. **AC 10:**
    - from the laptop, eleven `POST /search/natural` with the body `{"query": "x"}` in a loop give ten
      answers and then 429. Costs about 2 US cents, counted by the cap;
    - at once, the same search from a phone on mobile data, through `/docs`, gives 200;
    - from the laptop with `-Headers @{ "X-Forwarded-For" = "192.0.2.1" }`: still 429.
11. **AC 11:**
    - `terraform state list` holds one `aws_instance` and no autoscaling group;
    - `sudo docker ps` shows one `api`;
    - `docker exec api ps aux` shows one server process.
12. **AC 13:** read section 14's table. In Billing, the month shows no ELB, NAT or Secrets Manager line, and
    the budget from 024 is unchanged.
13. **AC 14:** no schedule or scaling exists (`terraform state list`); the runbook says "never sleeps".
14. **AC 15:** `aws logs tail /cragmatch/api --since 10m` shows the laptop's address, the same as
    `Invoke-RestMethod https://checkip.amazonaws.com`, and not a `130.176.x` or `15.158.x` edge address.
15. **AC 16:** read section 19, then run it with the previous SHA and `skip_migrations`. "Live: <previous>"
    appears and `/health` is fine. Deploy the newest SHA again.

**Commit:** `Ticket 025: backend on AWS, arm64 API image built after CI on main and pushed to ECR with immutable SHA tags, deployed through a custom SSM document that pulls, migrates while the old version serves, restarts, checks health, warms the planner tables and returns to the previous image when unhealthy, API CloudFront distribution with caching off and HTTPS for viewers, port 80 open only to the CloudFront prefix list, client address from X-Forwarded-For trusted only from CloudFront ranges, Postgres over verify-full TLS, write-only key slots and settings in Parameter Store, logs in CloudWatch, offline terraform tests and client address tests, runbook for first deploy, data load, logs, rollback and destroy`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `backend.tftest.hcl::api_distribution_passes_every_request_to_the_host`, `::deploy_parameters_name_the_host_and_the_api_url`; workflow step 9; manual B1 |
| 2 | `deploy-api.sh` order (review); manual B2 (migration log before restart, extensions, `daily_spend`, planner tables) |
| 3 | `::deploy_document_runs_only_the_deploy_script_with_a_commit_sha`; `deploy-api.sh` steps 4 and 8 (review); manual B3 (red deploy, old version keeps serving) |
| 4 | Runbook section 16 with 023's `load_data` (tested in 023); manual B4 |
| 5 | `::only_cloudfront_reaches_the_api_port`, `::api_settings_use_the_database_over_verified_tls_and_hold_no_secret`; `test_client_address.py::test_a_caller_outside_cloudfront_cannot_choose_its_address`; manual B5 |
| 6 | `::api_key_slots_are_write_only_secure_strings`, `::api_settings_use_the_database_over_verified_tls_and_hold_no_secret`, `::user_data_installs_one_api_unit_and_holds_no_secret`, `::host_can_pull_the_image_and_write_api_logs_only`; manual B6 |
| 7 | `::api_settings_use_the_database_over_verified_tls_and_hold_no_secret` (caps reach the app), `::daily_caps_cannot_be_negative`; manual B7 (real searches, spend counted, tokenizer cached, restart) |
| 8 | `::cors_origins_must_be_plain_origins`, `::api_settings_use_the_database_over_verified_tls_and_hold_no_secret`; manual B8; the live site's origin in 026 |
| 9 | Manual B9 (restart and redeploy keep the paused run and the data) |
| 10 | `test_client_address.py::test_behind_cloudfront_each_viewer_has_its_own_limit`, `::test_a_forged_forwarded_for_does_not_escape_the_limit`, `::test_a_caller_outside_cloudfront_cannot_choose_its_address`; `::trusted_proxies_are_exactly_the_cloudfront_ranges`, `::api_settings_fit_a_standard_parameter`; manual B10 |
| 11 | `::user_data_installs_one_api_unit_and_holds_no_secret` (one unit, one container name, 021's CMD untouched); runbook section 14; manual B11 |
| 12 | `::deploy_role_pushes_one_repository_and_sends_one_document`, `::deploy_document_runs_only_the_deploy_script_with_a_commit_sha`; the workflow's `if` and steps (review); manual B3 |
| 13 | Cost section of this plan and runbook section 14; `::registry_keeps_immutable_tags_and_the_last_five_images`, `::api_logs_are_kept_two_weeks`; manual B12 |
| 14 | Dropped: never sleeps (Ticket check); manual B13 |
| 15 | `::api_distribution_passes_every_request_to_the_host`, `::trusted_proxies_are_exactly_the_cloudfront_ranges`, `::api_logs_are_kept_two_weeks`; `test_client_address.py::test_behind_cloudfront_each_viewer_has_its_own_limit`; runbook section 18; manual B14 |
| 16 | `::deploy_document_runs_only_the_deploy_script_with_a_commit_sha` (`runMigrations`), `::registry_keeps_immutable_tags_and_the_last_five_images`; runbook section 19; manual B15 |

Every criterion is covered. AC 2, 4, 7 and 9 can only be shown on the account. AC 8 is finished in 026. The
automatic return after an unhealthy start (`deploy-api.sh` step 8) is shown by review only, because
provoking it on purpose needs a broken image.

## Risks
- **The first apply replaces the host** (new `user_data`). Expect a few minutes of downtime; the data is
  kept (024's drill). Every later change under `infra/main/host/` does the same, and the runbook says so.
- **Migration discipline:** migrations run while the old version serves, and rollbacks skip them. A
  dropping or renaming migration would break the old version, or the rollback. Mitigation: the
  expand-then-contract rule in the runbook and the suggested CLAUDE.md trap.
- **Deploy downtime:** `systemctl restart` stops the old container before the new one starts, so there are
  about 10 to 30 s of 502/504 per deploy (start-up time from 021's hand-off). The web app shows its offline
  state. Blue-green on one host would need a proxy; not worth it for friends.
- **Prefix list drift:** a new CloudFront range passes the security group (AWS updates the list) but is not
  trusted until the next `apply`. Its viewers then share the edge's limit, which is stricter, not
  spoofable. The plan output shows the settings change.
- **Other CloudFront distributions can reach the origin:** they cannot forge addresses (CloudFront appends
  the real one), and the cap bounds the cost. The follow-up is a secret origin header checked by a small
  middleware (app code, a new ticket).
- **Unencrypted CloudFront-to-host hop:** accepted and written down. It carries no credentials. The upgrade
  path is a custom domain plus a public certificate.
- **The 4 KB Standard parameter limit:** about 55 CIDRs take about 1 KB. The precondition fails the plan
  clearly if it ever grows past 4 KB.
- **The 16 KB user_data limit:** 024 plus 025 come close. The test fails first, and the fix is
  `base64gzip`.
- **Memory on 2 GiB:** there is no hard limit until it is measured. OOM score 500 makes the kernel pick the
  API over Postgres, and `Restart=always` brings it back. The runbook's `docker stats` step gives the
  number for 024's cut 1.
- **CPU credits** (`standard`, 024): a long burst throttles to the baseline instead of billing. Builds run
  on GitHub, not on the host.
- **Public workflow logs:** masking covers the host id, the API URL and the account id. The deploy script
  prints no addresses. The reviewer reads every `echo` in the scripts.
- **`workflow_run` subtleties:** it only fires for the copy on the default branch. The `if` excludes
  pull-request runs and forks. The `ls-remote` guard stops an older run from deploying over a newer one,
  and the `deploy` concurrency group runs one at a time.
- **Docker's userland proxy:** for outside traffic, Docker DNATs and keeps the source address. If a future
  Docker served it through `docker-proxy`, the peer would be the bridge gateway, which is not trusted, so
  everyone would share one limit. Manual checks B10 and B14 would show it.
- **External services:**
  - Voyage free tier (3 a minute): the data load makes 1 request and the checks 2, a minute apart;
  - Claude: B10 costs about 2 cents, counted by the cap;
  - Overpass: only from the laptop;
  - huggingface.co: once per data volume.
- **Behaviour that must stay unchanged:**
  - `backend/app`, `backend/Dockerfile`, `web/`, `ci.yml` (name, jobs, checks) and `terraform.yml` are
    untouched;
  - local development and every existing test as before;
  - 024's resources keep their tests, except the narrowing noted for the ingress assertion.
- **No migration in this ticket:** nothing to downgrade. The deploy only applies the existing ones (022's
  `daily_spend` included).
- **Size:** about 19 files (11 new: 4 Terraform, 4 host files, 2 test files, 1 workflow; 8 edited, mostly 024 files and docs) plus 19 tests and a
  long runbook. It is one coherent path: an API without the deploy, or a deploy without the API, cannot be
  checked on its own. **One delivery is fine.** If the review finds it too big, split the **ticket**:
  - 025a: ECR, host unit, CloudFront, settings and logs, with a deploy by `aws ssm send-command` from the
    laptop;
  - 025b: the `Deploy` workflow and the deploy role's policy.

## What 026 builds on (seams)
- **API address:** the output `api_url` and the parameter `/cragmatch/deploy/api_url`, for example
  `https://d111.cloudfront.net` with no trailing slash. The deploy role can already read it, so 026's
  `web` job builds with `VITE_API_URL` from it and masks it.
- **CORS:** change `CRAGMATCH_CORS_ORIGINS` in `local.api_settings` from `var.cors_origins` to
  `"https://${aws_cloudfront_distribution.web.domain_name}"`. Keeping `http://localhost:5173` as well is
  026's choice; the variable's validation pattern applies.
  - There is no cycle: the web distribution never depends on the API.
  - Order: `terraform apply` creates the site and updates `/cragmatch/api/settings`. The backend reads it at
    its next start, which is the next backend deploy, or `sudo systemctl restart cragmatch-api`.
  - Update `::api_settings_use_the_database_over_verified_tls_and_hold_no_secret` to the new value.
- **Distributions:** `aws_cloudfront_distribution.api` stays API-only. 026 creates
  `aws_cloudfront_distribution.web` (private S3 with OAC, SPA fallback, its own cache policy). Both share
  the account's free allowance. The API's `CachingDisabled` means the API needs no invalidation.
- **Workflow:** `.github/workflows/deploy.yml`, `name: Deploy`. Its trigger and gate are fixed:
  `workflow_run` on `CI` for `main`, `push` and `success`, plus `workflow_dispatch`. Concurrency group
  `deploy`. Job id `backend` and name `Deploy backend` are kept.
  - 026 adds job `web` (`needs: backend` is the simple, predictable order for its AC 8) with its own
    `permissions: { contents: read, id-token: write }`, the same `if`, and the same tag guard.
  - CI already includes 020's `web: npm test` step in the `eslint` job, so the gate covers it.
- **Deploy role:** 025's inline policy `cragmatch-deploy-backend` is not edited. 026 adds a separate inline
  policy (S3 `PutObject`, `DeleteObject` and `ListBucket` on the site bucket; `cloudfront:CreateInvalidation`
  on the web distribution's ARN) and its own test.
- **Never sleeps:** 026 AC 12 is dropped. The app's existing offline and 503 states cover the
  deploy-restart gap of about 10 to 30 seconds.
- **Public logs:** mask the site's domain too.
- **Costs:** 026 adds its row to runbook section 14's table (024 estimated about 0.01 USD).
- **Runbook:** 026's sections come after 23. Its destroy section adds the site bucket.

## Out of scope (copied from the ticket)
- The frontend hosting and its workflow: ticket 026.
- A custom domain, login, public access, per-user quotas: share codes stay the only access.
- Several instances and a shared rate-limit store: one instance instead.
- Monitoring and alerts beyond the logs and the billing alert.
- Cleaning up old planner runs (015 deferred it).
- Hiding `/docs` or asking search engines not to index: not now.
