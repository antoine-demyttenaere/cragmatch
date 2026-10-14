# 022: Stage 7, part 3: daily spending cap on Claude and Voyage

**Status:** Ready
**Size:** L (needs a migration: the amount spent today must survive a restart; backend only)
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "7 cloud deployment (to be reworked)." (ticket 013, split on 2026-10-13; renumbered on 2026-10-14. This is the second half of the old ticket 019.)
**Part of:** Stage 7 in execution order: 018 CI, 019 and 020 trip planner screen, 021 production config and container, 022 (this), 023 to 026 deploy on AWS.
**Depends on:** 021 (settings with defaults). Must be delivered before ticket 025 puts the paid endpoints on the internet.

## Decisions already made by the user
- Paid endpoints keep their rate limits, **and** the user wants a daily spending cap on Claude and
  Voyage (2026-10-13).
- Defaults proposed by the earlier plan and not contradicted by the user: Claude USD 1.00 a day,
  Voyage USD 0.50 a day, the day ending at midnight in Europe/Madrid, and an HTTP 503 when the cap is
  reached. They are listed below as suggested defaults for the user to confirm.

## User story
As the owner of CragMatch, I want a daily cap on what Claude and Voyage can cost, so that I can run
the app on the internet without a surprise bill.

## What exists today
(Checked against the code on 2026-10-14. "Earlier plan" means found by the tech lead on 2026-10-13
and not re-checked.)
- Paid calls: Claude is called by `/search/natural` (`services/natural_search.py`, parse chain) and
  `/search/similar` (`services/similar_search.py`, reasons chain). Voyage is called by
  `/search/similar` (embedding the query) and by the script `index_sectors_langchain`. Both
  endpoints are limited to 10 per minute per IP (`routers/search.py`, slowapi, in memory). The trip
  planner calls no paid API.
- Claude's token use is only **logged** (`services/llm.py` `log_tokens()`, via `UsageLogger` in
  `rag/llm.py`). Nothing is stored or summed, so no daily total exists.
- **Voyage's usage cannot be read back.** The LangChain embeddings client keeps only the vectors
  and throws the API's token count away (earlier plan, from the library code). A cap on Voyage has to
  count calls, not tokens, unless the tech lead finds a better way.
- Settings (`app/core/config.py`) have no limits or prices. Ticket 021 adds settings with defaults.
- There is no table for spending. The chains are cached and shared between threads, so per-request
  counting cannot live on a shared object (earlier plan).
- The web app shows a 503 from a search as a notice with the server's message, so a cap message needs
  no frontend change (earlier plan, `SearchPage`).
- Time zones: `tzdata` is only in `uv.lock` for Windows. A Linux image may not know
  `Europe/Madrid` (earlier plan).

## Acceptance criteria
1. Given a daily cap on Claude and one on Voyage, when the estimated spend of a provider for today
   reaches its cap, then the endpoints that need that provider answer with a clear error that says the
   daily limit is reached and to try tomorrow (not "too many requests per minute"), and no more paid
   calls are made until the next day.
2. Given the cap is reached, then the endpoints that need no paid API keep working: filter search,
   groups, members, stays and the trip planner.
3. Given a provider's cap is reached but the other's is not, then an endpoint that needs only the
   other provider keeps working (`/search/natural` needs Claude only; `/search/similar` needs both).
4. Given the cap is not reached, when a paid endpoint is called, then it answers as today and the
   amount counted for today goes up.
5. Given the server is restarted or the container is replaced during the day, then the amount
   already counted for today is not forgotten.
6. Given a new day starts (in the chosen time zone), then the counters start again from zero.
7. Edge case: given the cap is reached, when a request is rejected, then it makes no Claude or Voyage
   call at all (a test with the providers mocked sees zero calls), and `/search/similar` makes no
   Voyage call even when only Claude's cap is reached.
8. Edge case: given a cap set to 0, then that provider is switched off from the first request.
9. Edge case: given Claude answered but its answer was unusable, then the tokens it used are still
   counted. Given a Voyage call that failed, then it is not counted.
10. Given the per-minute rate limit and the daily cap are both exceeded, then the climber sees the
    daily-limit message (not 429) when the request got past the rate limit, and the per-minute 429
    still comes first when that limit is hit.
11. Given the caps, the prices behind the estimate and the time zone, then they can be changed in
    settings without a code change, and have defaults so tests and local development need no new
    variable.
12. Given the test suite, then it runs offline as today, with the providers mocked and a clock that
    tests can control.

## Scope
**In:**
- A daily cap per provider (Claude and Voyage), an estimate of the spend stored per day and
  provider, a check before every paid call and a count after it, in the services.
- A clear 503 message when a cap is reached, with its own wording.
- A migration for the stored amounts.
- Tests (providers mocked, clock controlled), README and CLAUDE.md lines for the new service.

**Out:**
- Per-user quotas, billing pages, spend alerts by email: one cap per provider is enough for friends
  only. (An AWS billing alert is ticket 024.)
- Counting the scripts (`index_sectors_langchain`, `rag_playground`): run by hand, not through the
  services.
- A meter in the UI: the server's message is shown as the error.
- Changing the per-IP rate limits.

## Open questions
- [non-blocking] What are the daily caps? (suggested default: USD 1.00 for Claude and USD 0.50 for
  Voyage, both changeable in settings. Both providers publish prices in USD, and for a ceiling 1 USD
  is close enough to 1 EUR. The user decides the real numbers.)
- [non-blocking] What does the cap count? (suggested default: an estimate. Claude from input and
  output tokens times prices in settings; Voyage as a fixed estimated price per call, deliberately
  high. The user should check the prices against the providers' current price lists. The aim is a
  ceiling, not an invoice.)
- [non-blocking] Where does the day start and end? (suggested default: midnight in Europe/Madrid,
  since the friends are in Spain.)
- [non-blocking] Which status does a reached cap use? (suggested default: 503 with a readable message,
  such as "Today's spending limit for the AI searches is reached. Try again tomorrow, or use the
  filter search." 429 stays for "too many per minute".)
- [non-blocking] Should only Claude's cap stop `/search/similar` from returning results without
  reasons, as it already does when Claude fails? (suggested default: no; check both caps first, so a
  rejected request makes no call at all, as criterion 7 says.)

## Notes for the tech lead
- This is the second half of the old ticket 019. The earlier plan sketched one design (a table with
  one row per day and provider, a service with a check before and a record after, a per-request
  token counter, an atomic increment). It is a suggestion; choose what you think is best.
- Keep routers HTTP-only: the cap check is a service, and it must run **before** the call it guards.
- New model: import it in `app/models/__init__.py` and add a reviewed Alembic migration (CLAUDE.md).
  `alembic/env.py` compares only our own tables. Remember the trap: tests use `create_all()`, so after
  delivering, the user runs `uv run alembic upgrade head` or the dev server says "UndefinedTable" on
  the first AI search. Ticket 025 must run migrations before the new version takes traffic.
- Reuse: `get_chat_model()`, `UsageLogger`, `log_tokens()` (`rag/llm.py`, `services/llm.py`);
  `get_embeddings()` / `store.embeddings.embed_query` (`rag/vectorstore.py`, `services/similar_search.py`).
  The chains are cached and shared between threads, so per-request counting should not live on a
  shared object.
- A check followed by a call can overshoot the cap by the requests already running. Accept it and say
  so; the stored increment itself should not lose spend.
- Slowapi endpoints keep `request: Request` and a body named `body`.
- Time zone data may need to become a direct dependency for a Linux image. Windows + OneDrive: stop the
  dev server before `uv add`.
- Tests: mock Claude and Voyage where the router/service uses them; test with the rate limiter on and
  off, and with a clock you control. Existing tests for the 503 "assistant unavailable" and "embedding
  service" paths and the reasons fallback must stay green.
- Definition of done: new files in the README structure; migration reviewed; CLAUDE.md "Reuse" line for
  the cap service.
