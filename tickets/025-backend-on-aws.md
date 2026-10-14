# 025: Deploy on AWS, part 2: the backend running in the cloud

**Status:** Ready
**Size:** L (infrastructure code, a deploy workflow and a data load; small or no app code)
**Mode:** delivery for the Terraform, the workflow and the runbook. Entering the Anthropic and Voyage keys and running the first data load are the user's own steps, written in the runbook.
**Raw request:** "7 cloud deployment (to be reworked)." (ticket 013). Requirements of 2026-10-14: AWS, resource-efficient (about 0 to 10 EUR a month), all infrastructure as Terraform in the repo, no click-ops except creating the account and entering secrets, friends only via share codes. This replaces the backend half of the old Render ticket 020.
**Part of:** Stage 7 in execution order: 018 CI, 019 and 020 trip planner screen, 021 production config and container, 022 daily spending cap, 023 repeatable data load, 024 AWS foundation, 025 (this), 026 frontend on AWS and the deploy pipeline.
**Depends on:** 021 (image and settings), 022 (spending cap, before the paid endpoints are public), 023 (data load), 024 (network, database, state, GitHub identity). 015 (planner paused runs in Postgres) is already delivered.

## Decisions already made by the user (2026-10-14)
- AWS, all as Terraform, no click-ops except the account and secrets.
- About 0 to 10 EUR a month in total; Claude and Voyage usage is outside that and bounded by the cap.
- Friends via share codes, no login, not public. Paid endpoints keep their rate limits, plus the daily cap.

## User story
As a group of friends, I want the CragMatch API running on the internet at a stable HTTPS address, so that
we can use the app from our phones without anyone running it on a laptop.

## What exists today
(Checked against the code on 2026-10-14. "Earlier plan" means found by the tech lead on 2026-10-13 and not
re-checked.)
- Nothing is deployed. The image (ticket 021), the cap (022), the data scripts (023) and the foundation
  (024) are the previous tickets.
- Rate limits: slowapi, kept in memory, per client address (`get_remote_address`), 10 per minute on
  `/search/natural` and `/search/similar` (`routers/search.py`, `core/rate_limit.py`). Behind a proxy or
  load balancer the address the server sees may be the proxy's, so every friend would share one limit. The
  earlier plan found that uvicorn trusts forwarded headers only from the addresses it is told to trust
  (`FORWARDED_ALLOW_IPS`, default localhost), so this needs deployment configuration, not code. How the
  chosen AWS entry point forwards the client address is not yet checked.
- The limits live in the process, so only **one backend instance** is correct. Scaling out would need a
  shared store (a new ticket).
- Migrations: `uv run alembic upgrade head`, by hand. The migration that adds the daily cap (022) must run
  before the new version takes traffic.
- The planner's checkpoint tables are created by the library's `setup()` on the first planner request of each
  process, not by Alembic. `setup()` waits for open transactions (CLAUDE.md trap).
- The vibe search needs a tokenizer that Voyage's client downloads from huggingface.co on first use, so the
  backend needs outbound HTTPS to that host as well as to Voyage and Anthropic, and a writable home
  directory (earlier plan; the latter is in ticket 021's image).
- Connections per process: about 35 at most (see ticket 024), plus Alembic and a data load running at the
  same time.
- The data load (ticket 023) is a command run against a database URL. `seed_notes` must run before
  `index_sectors_langchain` (1 Voyage request; the free tier allows 3 a minute). `import_stays` calls the
  public Overpass API and keeps a cache in `backend/.cache/overpass/` on the laptop. A database in a private
  network cannot be reached from a laptop without some access path; this is a decision for the tech lead.
- `/docs` is public by default and the site is unlisted, not protected.

## Acceptance criteria
1. Given the deployed backend, when anyone calls `GET /health` on its public HTTPS address, then it answers
   `database: connected`.
2. Given a fresh cloud database, when the backend is deployed, then migrations have been applied before the new
   version takes traffic, and the `postgis` and `vector` extensions are present (ticket 024's rule).
3. Given a deploy that ships a new migration, then the schema is updated with no manual step. Given a migration
   that fails, then the old version keeps serving, or the deploy is marked failed (not a half-migrated live app).
4. Given the one-off data load, when the documented steps are followed against the cloud database, then the cloud has
   the same kinds of data as local, with `seed_notes` before `index_sectors_langchain`, and the Voyage limit of
   3 requests a minute respected. Given the load runs a second time, then nothing is duplicated (ticket 023).
5. Given the deployed backend, then the database is not reachable from the public internet, and the backend reaches it
   from inside the network over TLS.
6. Given the secrets (database password, Anthropic key, Voyage key), then they live only in the cloud's secret store: not
   in the repository, the image, the Terraform state where avoidable, the build logs or the plan output. The user
   enters the two API keys by hand once.
7. Given a vibe search and a natural-language search on the live API, then they work end to end with the real Claude and
   Voyage keys, and the spend is counted by the daily cap (ticket 022). The first vibe search after a restart works
   even though it downloads the tokenizer.
8. Given a browser on the live site (ticket 026), when it calls the API, then the call works because the live site's
   address is the allowed origin. Given another website's page, then the browser may not read the API's answers.
9. Given a trip planner run waiting for approval, when the backend restarts or is redeployed, then answering the run
   continues where it stopped (ticket 015's criterion, now in the cloud). Given a redeploy, then groups, members and
   planner runs are still there.
10. Given the rate limit, when one friend makes 11 natural-language searches within a minute, then the 11th gets 429.
    Given a second friend on another network at the same time, then they are not blocked by the first one's requests.
    (Use natural search for the check: vibe searches would hit Voyage's own 3 a minute limit first.)
11. Given the backend, then exactly **one** instance runs, set in the infrastructure code, and the runbook says that
    scaling out needs a shared rate-limit store.
12. Given a push to `main` (if the OIDC question in ticket 024 is yes), when the checks of ticket 018 pass, then a
    workflow builds the image, pushes it and deploys the backend using short-lived credentials, and reports failure
    when the deploy fails. Given a failed check, then nothing is deployed. Given the workflow, then it holds no AWS key.
13. Given the cost, then the runbook's cost table for this ticket adds to the figure in ticket 024 and the total of
    backend, database and network is within about 0 to 10 EUR a month (or the plan says clearly why not, and what the
    user can cut). A billing alert from ticket 024 stays in place.
14. Edge case: given the backend has been idle and the compute option scales to zero or sleeps (if the tech lead picks
    one that does), when the first request arrives, then the app shows its loading state and succeeds after the wake-up
    instead of a broken page; the plan says what the longest wake-up is and how the climber sees it. If the chosen
    option never sleeps, say so.
15. Edge case: given the logs, then each request shows the real client address (not the load balancer's), and the
    runbook says where to read the logs.
16. Given a rollback is needed, then the runbook says how to return to the previous image, and that a rollback does not
    undo a migration.

## Scope
**In:**
- The backend's registry for its image, the service that runs it, one instance, its network placement, its public HTTPS
  entry point, its settings and secrets, all as Terraform.
- Migrations at deploy time and the planner's table set-up.
- The client address for the rate limits.
- How the one-off data load reaches the cloud database, with the documented steps.
- The deploy workflow for the backend (if the OIDC question is yes), using ticket 018's checks as the gate.
- Runbook: first deploy, redeploy, load the data, read logs, roll back, change keys and caps, destroy.

**Out:**
- The frontend hosting and its workflow: ticket 026.
- A custom domain, login, public access, per-user quotas: share codes stay the only access.
- Several instances and a shared rate-limit store: one instance instead.
- Monitoring and alerts beyond the logs and the billing alert.
- Cleaning up old planner runs (015 deferred it): a handful of groups, not worth it yet. Tell me if the database size is
  tight.
- Hiding `/docs` or asking search engines not to index: not now (the site is unlisted; the rate limits and the daily cap
  bound the cost).

## Open questions
- [non-blocking] Do deploys run from GitHub Actions with OIDC (no long-lived AWS keys)? (suggested default: yes, as asked
  in ticket 024. If no, deploys are run from the laptop and criterion 12 is dropped.)
- [non-blocking] Is a slow first request after idle acceptable? (suggested default: yes, up to about a minute, if the app
  shows a loading state. If not acceptable, the cost limit probably has to move; the plan says by how much.)
- [non-blocking] How is the data loaded: from the laptop through a temporary access path, or from a one-off task inside
  the network, or by a dump? (suggested default: the tech lead decides. The scripts of ticket 023 are the supported way;
  a dump is not, because it carries extension schemas and test data. Keep `import_stays` on the laptop if Overpass
  refuses cloud addresses.)
- [non-blocking] Should the first deploy wait for ticket 022's cap? (suggested default: yes, never put the paid
  endpoints on the internet without the cap.)

## Notes for the tech lead
- **You choose the AWS services.** Options to compare for running the backend container, against the 0 to 10 EUR target,
  the single-instance rule and the memory the app needs: a container service with a load balancer (check the load
  balancer's fixed monthly price); a container service with a direct public address; a small virtual machine running the
  container; a function-style option (check cold start, the memory limit and the app's import time). Say what each costs
  a month and how it handles TLS, the client address, logs and migrations. A fixed-price component can by itself use the
  whole budget, so the cheapest viable option may differ from the most usual one.
- Migrations at deploy time: compare a one-off task run before the new version, a step at container start, and a deploy
  workflow step. The requirement is criterion 3, not a method. Remember that migrations then run while the previous
  version may still serve, so each must work with the code before it.
- Client address: check what the entry point sends and what uvicorn will trust. A wrong choice makes criterion 10 fail
  silently (everyone shares one limit), or lets a client spoof its address; say which trade-off you accept and why.
- Memory: before choosing, measure the container (the earlier plan suggested checking memory during a vibe search, a
  natural search and a planner run; a small instance has little room for LangChain and LangGraph).
- `setup()` for the planner tables needs rights to build indexes concurrently, and must not run while a request holds
  an open transaction (CLAUDE.md). Decide where it runs.
- Secrets: Terraform should create the empty secret slots, and the user enters the two API keys by hand. Check what the
  state contains.
- Tests: the existing suite is unchanged. If you add configuration tests (for example that the infrastructure files set
  one instance), they read files and make no network calls. Terraform changes are checked with `fmt`, `validate`, `plan`
  and manual checks on the account.
- Never print or commit `backend/.env`; no real keys or account ids in the runbook.
- Definition of done: new files in the README structure; a manual check of every criterion on the live API, written
  down, since the test suite cannot see the cloud.
