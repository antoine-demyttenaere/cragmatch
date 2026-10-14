# 024: Deploy on AWS, part 1: the foundation as Terraform

**Status:** Ready
**Size:** L (new infrastructure code, no app code, no migration). Called L by judgment, not by the size rules: it sets up the whole cloud account and carries a billing risk. The repo changes are only Terraform and docs.
**Mode:** delivery for the Terraform files, a runbook and the checks. Creating the AWS account and entering secrets stay the user's own steps, written down in the runbook.
**Raw request:** "7 cloud deployment (to be reworked)." (ticket 013). On 2026-10-14 the user chose: AWS (it is what they most want to learn), resource-efficient (the earlier budget was about 0 to 10 EUR a month), everything as Terraform in the repo with state stored remotely, no click-ops except creating the account and entering secrets, friends only via share codes. This replaces the old Render ticket 020.
**Part of:** Stage 7 in execution order: 018 CI, 019 and 020 trip planner screen, 021 production config and container, 022 daily spending cap, 023 repeatable data load, 024 (this), 025 backend on AWS, 026 frontend on AWS and the deploy pipeline.
**Depends on:** nothing in the app. Ticket 021 (the container and settings) is needed by 025, not here.

## Decisions already made by the user (2026-10-14)
- The platform is AWS.
- Everything is Terraform in the repository, with the state stored remotely. The only manual steps are
  creating the account and entering secrets.
- Budget target: about 0 to 10 EUR a month, as before. Claude and Voyage costs are outside it and are
  bounded by the daily cap of ticket 022.
- Users: friends via share codes. No login, not public.

## User story
As the owner of CragMatch, I want the AWS account's base set up from code (remote state, a billing
alert, a network and a Postgres with the extensions CragMatch needs), so that every later piece is
reviewable, repeatable and cheap, and I learn AWS by reading and running real Terraform.

## What exists today
(Checked against the repository on 2026-10-14.)
- Nothing is deployed. There is no Terraform, no deploy configuration, no `.github/` folder (ticket
  018 adds the CI) and no backend Dockerfile (ticket 021 adds it).
- Database locally: `postgres.Dockerfile` is `postgis/postgis:17-3.5` plus pgvector, Postgres 17.
- Extensions: `vector` is created by the migration `178caab75ad8` (`CREATE EXTENSION IF NOT EXISTS
  vector`). **No migration creates `postgis`**: locally it comes with the image. I found no code,
  model or migration that uses PostGIS (distances use `haversine_km()` in Python; the only mention is
  a comment in `alembic/env.py`). The user still requires both extensions, so they stay a requirement.
  The tech lead should know PostGIS is unused today, and that relaxing it could widen the choice of
  database options.
- Migrations are run by hand (`uv run alembic upgrade head`). `alembic/env.py` compares only our own
  tables.
- The planner's checkpoint tables are created by the library's `setup()` on the first planner request
  of each process, not by Alembic (`routers/planner.py`, `agent/checkpointer.py`). `setup()` builds
  indexes concurrently and waits for open transactions, so the database user needs the rights to do
  that.
- Connections per backend process (earlier plan, from the code): the app engine (SQLAlchemy defaults,
  up to 5 plus 10 extra, `core/database.py`), the vector store's own engine (the same defaults), and the
  planner's pool of up to 5 (`POOL_MAX_SIZE` in `agent/checkpointer.py`). That is about 35 at most
  per process, plus Alembic and any script run at the same time. A small managed database has a connection
  limit that the choice must respect.
- I do not know what the user's AWS account gets for free or in credits. AWS's free-tier rules have
  changed over the years, so the tech lead must check the current rules rather than rely on memory.

## Acceptance criteria
1. Given a fresh AWS account with an administrator identity, when the documented bootstrap is
   followed, then the remote state storage exists, with versioning and locking, and every later Terraform
   run in the repo uses it. The bootstrap is the only part that needs the state to be created before it
   can be stored; the runbook says how it is done and kept.
2. Given the Terraform in the repo, when `terraform validate` and `terraform plan` run, then they
   succeed, a second plan after an apply shows no changes, and the plan names no secret value in its output.
3. Given the account, then a billing alert exists as Terraform: it emails the owner when the forecast
   or actual monthly cost passes a threshold (suggested default below). The email address is a variable,
   not hard-coded.
4. Given the foundation applied, then a network exists in one region, laid out so the database is not
   reachable from the public internet. The region is stated and the reason is written (suggested
   default below).
5. Given the foundation applied, then a Postgres 17 database exists, reachable from the network and from
   the later backend service, with encryption at rest and TLS in transit, with automatic backups for at
   least a few days.
6. Given the database, then both `postgis` and `vector` are available in it. Given a fresh database, then
   after the later migrations both are created, with no manual step. (The creation may be a migration or
   an infrastructure step; the tech lead says which, and the other extensions stay untouched.)
7. Given the database credentials, then they are generated or entered once, stored in the cloud's secret
   store, and never written in the repo, the plan output or the logs. The runbook states where the
   Anthropic and Voyage keys will be entered by hand (ticket 025).
8. Given the stack, then the runbook has a cost table: each billed item, its approximate monthly price
   from AWS's own pricing pages at the time of writing, the total in EUR, and what the free tier or
   credits would cover. It states the assumption about the account.
9. Given the foundation, then the way to destroy it is documented, including what stays (state storage,
   backups) and what is lost (the data), so the project can be torn down to stop all charges.
10. Given the tags, then every resource carries a project tag, so the AWS billing view can show what
    CragMatch costs.
11. Given an identity for GitHub Actions deploys, if the question below is answered yes, then it is created
    as Terraform with a trust limited to this repository and to the branch or environment named, using
    short-lived credentials, with no long-lived AWS keys stored in GitHub.
12. Edge case: given a second `terraform apply` with no code change, then nothing changes. Given a
    developer who runs it from a new machine, then the runbook says what they need (credentials, the
    state location) and no local state file is needed.
13. Edge case: given the estimated monthly cost of the whole Stage 7 (this ticket plus 025 and 026) is above
    10 EUR for the cheapest option the tech lead finds, then the plan says so up front and proposes how to
    cut it, instead of building it.

## Scope
**In:**
- A Terraform folder in the repo with remote state, a bootstrap procedure for that state, a billing alert,
  a network, a Postgres database with both extensions available, secrets handling and tags.
- The identity for GitHub Actions deploys (if the question below is answered yes).
- A runbook (README or a `docs`-style file): account set-up, bootstrap, apply, destroy, cost table.
- Variables for everything account-specific (region, email, repository name), with no real value
  committed.

**Out:**
- The backend service, its image registry and its secrets: ticket 025.
- The frontend hosting, the pipeline workflows and the CORS wiring: ticket 026.
- A custom domain: the platform's own HTTPS address is enough for friends.
- Monitoring dashboards and alarms beyond the billing alert; multi-region; high availability.
- Application changes: none here.

## Open questions
- [non-blocking] Does the AWS account have free tier or credits? (suggested default: assume none and
  budget for the 0 to 10 EUR a month from real prices; if the account has credits, the tech lead notes how
  long they cover.)
- [non-blocking] What billing alert threshold? (suggested default: alert at about 5 EUR and at 10 EUR on
  forecast and on actual spend.)
- [non-blocking] Which region? (suggested default: a European region close to Barcelona, chosen by the
  tech lead for price and service availability; write why.)
- [non-blocking] Do deploys run from GitHub Actions using OIDC, with no long-lived AWS keys, as part of
  this? (suggested default: yes. Tickets 025 and 026 then deploy from the workflow. If no, deploys are run
  by hand from the laptop and the identity is skipped.)
- [non-blocking] How is the remote state bootstrapped? (suggested default: a tiny separate Terraform step
  with local state, run once, that creates the state storage and is then documented; or a documented
  script. The user wants no click-ops, so no console steps.)
- [non-blocking] Are the database's automatic backups enough, or should the owner also keep a periodic
  export? (suggested default: automatic backups with a short retention are enough; crags, notes and
  stays can be reloaded by ticket 023, only groups, members and planner runs would be lost.)

## Notes for the tech lead
- **You choose the AWS services. Do not treat the lists below as decisions.** Options to compare for the
  database: a managed Postgres service (check whether it offers both `postgis` and `vector`, and the
  Postgres major version, 17 locally); a serverless-style managed Postgres, if it scales to zero or has a
  low minimum cost; Postgres running in a small container or VM with the repo's own image (cheapest, but
  you own backups and upgrades). Compare them against the 0 to 10 EUR target and say what each costs a
  month, including storage, backups and any fixed network cost. For the network, check the cost of what the
  private parts need to reach the internet (Claude, Voyage, a tokenizer host): some options carry a fixed
  hourly price that could break the budget on their own.
- Before choosing, check the real limits: memory the backend will need (the app imports LangChain and
  LangGraph), connection limits against the numbers above, and what the free tier or credits cover today.
  Write what you found, with the source and date.
- The user's earlier notes still apply: write that scaling the backend beyond one instance needs a shared
  rate-limit store (ticket 025 keeps one instance); never print or commit `backend/.env`; no real
  keys, passwords or account ids in the repo or the runbook, only variable names.
- Remote state: storage and locking are yours to choose. State must not contain secrets that can be
  avoided; say what it does contain.
- The planner's `setup()` needs rights to create indexes concurrently, so check the application database
  user is not too restricted.
- Backend tests are unaffected. Terraform has no pytest suite: the checks are `terraform fmt`,
  `validate`, `plan` and manual checks on the account. If you want a Terraform lint or format check in CI
  (ticket 018), say so in the plan, since it changes that workflow.
- Definition of done: new files and folders in the README structure; a manual check of every criterion
  written down, since the test suite cannot see the cloud.
