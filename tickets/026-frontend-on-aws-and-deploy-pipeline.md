# 026: Deploy on AWS, part 3: the web app online and the deploy pipeline

**Status:** Ready
**Size:** L (infrastructure code, a build-time setting, a workflow; touches the web build and CORS wiring). Small compared with 025.
**Mode:** delivery for the Terraform, the workflow and the runbook; the user checks the live site.
**Raw request:** "7 cloud deployment (to be reworked)." (ticket 013). Requirements of 2026-10-14: AWS, resource-efficient (about 0 to 10 EUR a month), all infrastructure as Terraform in the repo, no click-ops except the account and secrets, friends only via share codes. This replaces the frontend half of the old Render ticket 020.
**Part of:** Stage 7 in execution order: 018 CI, 019 and 020 trip planner screen, 021 production config and container, 022 daily spending cap, 023 repeatable data load, 024 AWS foundation, 025 backend on AWS, 026 (this).
**Depends on:** 025 (the live API address), 021 (the build-time API address in `web/`), 018 (CI as the deploy gate), 019 and 020 (the planner screens, so the live app is complete).

## Decisions already made by the user (2026-10-14)
- AWS, all as Terraform, no click-ops except the account and secrets. About 0 to 10 EUR a month overall.
- Friends via share codes, no login, not public.

## User story
As a group of friends, I want to open CragMatch at a stable HTTPS address on my phone and open a shared group link, so
that we can plan the trip without anyone running anything on a laptop. As the owner, I want a push to `main` to deploy
after the checks pass, so that a release is one merge.

## What exists today
(Checked against the code on 2026-10-14.)
- Nothing is deployed. `web/` is a Vite app (`npm run build` = `tsc -b && vite build`). The API address is hard-coded in
  `web/src/api/client.ts` until ticket 021 makes it a build-time setting.
- The share link is `?group=CODE` on the root path of the site (ticket 017). So a refresh never asks the host for an unknown
  path, but a mistyped path should still open the app (earlier plan; the 017 ticket also keeps the code in the URL).
- The API allows only the origin listed in its CORS setting (ticket 021). The live site's address must be that setting, and
  the site's build needs the API's address. Each depends on the other's address, so the order of creation matters.
- The frontend bundle must contain no key. Vite only exposes `VITE_` variables, so nothing else reaches it.
- Ticket 018's CI has three checks. Ticket 020 adds `web: npm test` to the ESLint job. There is no deploy workflow yet.
- If the backend sleeps when idle (ticket 025's choice), the first request is slow. The earlier plan found a risk: what a
  browser's cross-origin request receives while a platform wakes the server may be a page without the CORS headers, so the
  app would show "Can't reach the server" instead of waiting. This depends on the platform, so it is not known for AWS.

## Acceptance criteria
1. Given the deployed site, when anyone opens its public HTTPS address on a phone, then the app loads and a filter search
   returns sectors from the cloud database.
2. Given a group created on the live site, when its share link `?group=CODE` is opened on another phone on mobile data, then
   the group opens. Given a refresh, then the group is still there, with no "not found" from the host. Given a mistyped path,
   then the app opens rather than an error page from the host.
3. Given a new build of the web app, when it is published, then visitors get the new version without a manual cache step, and
   an old asset never breaks a new page (for example, a visitor with the previous version open).
4. Given the built site, then it contains no API key or password. The only deploy-time value it carries is the API address.
5. Given the live site's address, then the backend allows exactly that origin. Given another website's page, then the browser
   may not read the API's answers. (Ticket 025's criterion 8, now checked end to end.)
6. Given the live site, then the planner screens, the group search, the stays panel and both AI searches work as they do locally.
7. Given a push to `main` (if the OIDC question in ticket 024 is yes), when the checks of ticket 018 and 020 pass, then a workflow
   builds `web/` with the live API address, publishes it and makes visitors see it, using short-lived AWS credentials. Given a
   failed check, then nothing is published. Given the workflow, then it holds no AWS key and no API key.
8. Given a push that changes only the frontend, or only the backend, then only the needed part is deployed, or both are, and the
   runbook says which (simple and predictable is acceptable).
9. Given the deploy workflow, then a failed deploy shows red on GitHub and leaves the previous version live.
10. Given the site, then it is served over HTTPS only (HTTP redirects), at the address the platform gives, with no custom domain.
11. Given the cost, then the web hosting adds only a small amount to the totals in tickets 024 and 025, and the total of the
    whole Stage 7 stays within about 0 to 10 EUR a month (or the plan says clearly why not). The billing alert from ticket 024
    stays in place.
12. Edge case: given the backend is waking from sleep (if ticket 025's option sleeps), when a climber opens the site, then the app
    shows a waiting message and a search succeeds after the wake-up, instead of "Can't reach the server". If the backend never
    sleeps, state that and drop this criterion in the plan.
13. Edge case: given the first deploy, when the site's address and the API's address are not both known yet, then the runbook gives
    the order that works, with no manual step other than entering secrets.
14. Given the runbook, then it covers: first deploy, redeploy, how to read what is live, roll back to the previous web version, and
    how to destroy the web hosting.

## Scope
**In:**
- Static hosting for `web/` with HTTPS, the single-page fallback, and cache behaviour, all as Terraform.
- Building `web/` with the API address and publishing it.
- Connecting the live site's address to the backend's allowed origin, and the API address to the web build.
- The deploy workflow for the web app, and for the whole pipeline if tickets 025 and 026 share one (the user's question below).
- Waiting message for a sleeping backend, only if needed.
- Runbook additions.

**Out:**
- The backend infrastructure: ticket 025. The foundation: ticket 024.
- A custom domain, login, public access: share codes stay the only access.
- A preview environment per pull request.
- Edge security features (web application firewall, bot rules): the daily cap and rate limits bound the cost, and the site is
  unlisted.
- Search engine hints and hiding `/docs`: not now.

## Open questions
- [non-blocking] Does the deploy run from GitHub Actions with OIDC? (suggested default: yes, as set in tickets 024 and 025.)
- [non-blocking] Does a push deploy both backend and web every time, or only what changed? (suggested default: both every
  time, when the checks pass; simple and predictable. Skipping unchanged parts is an optimisation for later.)
- [non-blocking] If the backend sleeps when idle, how long a wait is acceptable before the app says something? (suggested
  default: show a "waking up the server" notice after about 3 seconds, and wait up to about two minutes before giving up.)

## Notes for the tech lead
- **You choose the AWS services.** Options to compare for static hosting: a bucket behind a content-delivery network (check the
  price after any free allowance, and how HTTPS works with the default address, because a custom domain is out of scope); a
  bucket website endpoint alone (HTTP only, so likely out); a static-hosting service in AWS. Check how the single-page fallback
  and cache control are expressed. The cheapest viable option wins as long as HTTPS holds.
- The circular address dependency (site needs API address, API needs site origin) can be solved in several ways: create the
  hosting first and read its address; use a fixed origin; apply in two stages. Pick one and document the order.
- Wake-up behaviour is a presentation matter in `web/` only if the chosen backend option sleeps. If the plan shows it is needed,
  keep it small and testable (a helper with a controllable clock), and run it with the Vitest setup from ticket 020. If not
  needed, say so.
- The pipeline: keep the checks of ticket 018 and 020 as the gate, one workflow or two. Add jobs rather than rewriting the CI
  workflow; do not change its three visible checks. The workflow needs permission to request a short-lived identity token and
  nothing else it does not use.
- Web build: `npm ci` and `npm run build` from `web/`, with the API address as a `VITE_` variable. The built files contain no key.
- No backend code change is expected here, except ensuring the CORS setting can name the site's origin (ticket 021 delivers
  the setting). If one turns out to be needed, say so in the plan, since it changes the size.
- Tests: the Vitest suite and `npm run lint` / `npm run build` must stay green. Terraform is checked with `fmt`, `validate`,
  `plan` and a manual check of every criterion on the live site, written down in the hand-off.
- Definition of done: new files in the README structure; runbook updated; the cost table in the runbook updated with the web hosting.
