# Plan for 022: Stage 7, part 3: daily spending cap on Claude and Voyage

**Ticket:** `tickets/022-daily-spending-cap.md`
**Approach:** A new service, `services/spending.py`, keeps an estimated spend per day and provider
in a new `daily_spend` table (one row per day in `Europe/Madrid` and provider, added to with one
atomic upsert). `/search/natural` and `/search/similar` call `ensure_under_cap()` before any paid
call; `/search/similar` checks both providers before anything else. After each call they add the
cost with `record_spend()`. Claude's cost comes from the tokens that a per-request `TokenCounter`
callback sees, and Voyage's from the query's UTF-8 bytes (an upper bound on its tokens) times a
price per million tokens. A reached cap raises `DailyCapReached`, which the router turns into a 503
with its own message. Caps, prices and the time zone are settings with defaults.

Assumed delivered first, as their plans describe: 017 (only `web/` remains), 018
(`.github/workflows/ci.yml` with dummy settings), 019 and 020 (planner screen), and 021 (optional
`CRAGMATCH_POSTGRES_URL`, CORS origins, `env_ignore_empty=True`, `hide_input_in_errors=True`,
`tests/test_config.py` with its env-clearing fixture, `.env.example` listing every setting as
`KEY=""`, the README "Settings" table, `backend/Dockerfile` and the `prod` compose profile).

**Alternatives considered:**
- *Keep the day's spend in memory:* forgotten on a restart or a new container (AC 5), and
  different per process.
- *Voyage at a fixed price per call (the earlier plan and the ticket's suggestion):* that is only a
  ceiling if the query is short, and neither `NaturalSearchRequest.query` nor
  `SimilarSearchRequest.query` has a `max_length`. One long text would cost more than the fixed
  price. Counting the query's UTF-8 bytes is just as simple (`len(query.encode("utf-8"))`) and
  stays a ceiling for any length: each token of Voyage's tokenizer covers at least one byte, and
  for English text a token is about 4 bytes, so the estimate is roughly 4 times too high, which is
  the "deliberately high" the ticket asks for. Reading Voyage's real token count is not possible:
  `langchain_voyageai` 0.4.1 `_embed_regular` keeps only `.embeddings` from the API's answer, and
  calling the private `_client.tokenize` would tie us to library internals.
- *Collect Claude's tokens in `UsageLogger` or in a context variable:* the chains are cached with
  `lru_cache`, so one `UsageLogger` is shared by every request and thread; counts kept on it would
  mix requests. A `TokenCounter` created per request and passed in
  `invoke(..., config={"callbacks": [counter]})` is explicit. `merge_configs` appends it to the
  chain's own callbacks (checked in `langchain_core` 1.6.8, `runnables/config.py:459-468`, list
  plus list), so the token log line stays.
- *Read and write the spend through the request's session (the earlier plan, `db.commit()` in
  `record_spend`):* in `/search/similar` the commit after the reasons call would expire the
  `Sector` rows just loaded (`expire_on_commit` is on), so building the response would reload every
  sector and crag one by one. The check would also leave the request's session idle in a
  transaction during the Claude call, which `PostgresSaver.setup()` waits for (CLAUDE.md trap).
  Instead `spending.py` runs each read and each upsert on its own short connection from
  `db.get_bind()`: the same engine (the test engine in tests), its own transaction, closed at once.
- *A router dependency that checks the cap:* logic in the router, and the "check before the call"
  rule belongs next to the calls. The check lives in the services.
- *When only Claude's cap is reached, let `/search/similar` return results without reasons:* that
  makes a Voyage call and gives no clear error, against AC 7. Both caps are checked first (the
  ticket's suggested default).
- *`Numeric` for the amounts:* an estimate doesn't need exact decimals; `Float` (double precision)
  is enough and reads back as a Python `float`.

**Choices on the ticket's open questions (all suggested defaults kept, in settings):**
- Caps in USD: `CRAGMATCH_CLAUDE_DAILY_CAP_USD=0.1`, `CRAGMATCH_VOYAGE_DAILY_CAP_USD=0.05`. A cap of
  0 switches that provider off.
- What is counted:
  - Claude: input tokens times `CRAGMATCH_CLAUDE_INPUT_USD_PER_MTOK` (default 3.00) plus output
    tokens times `CRAGMATCH_CLAUDE_OUTPUT_USD_PER_MTOK` (default 15.00), per million tokens.
    Thinking tokens are part of `output_tokens`, so they are counted.
  - Voyage: query bytes times `CRAGMATCH_VOYAGE_USD_PER_MTOK` (default 0.06), per million.
- **Prices to verify (the user, before delivery):** the model is `claude-sonnet-5`
  (`app/services/llm.py:7`). 3.00 / 15.00 USD per million tokens is the published price of the
  Sonnet line up to Sonnet 4.5; I could not confirm Sonnet 5's price from the repo or offline.
  Check https://docs.claude.com/en/docs/about-claude/pricing (or https://www.anthropic.com/pricing)
  and, for `voyage-3.5`, https://docs.voyageai.com/docs/pricing (0.06 per million tokens at the
  time of the earlier plan). If a price differs, the developer uses the user's number as the
  default.
- Day: midnight in `Europe/Madrid`, setting `CRAGMATCH_SPENDING_TIMEZONE` (AC 11 asks for the time
  zone in settings; the earlier plan had it hardcoded).
- Status: 503, detail "Today's spending limit for the AI searches is reached. Try again tomorrow,
  or use the filter search." 429 stays for the per-minute limit.
- `/search/similar` checks both caps before any call.

## Ticket check
Checked against the code on 2026-10-14 (`uv run pytest --collect-only -q`: **199 tests**; the suite
was not run, because the test DB is shared right now).
- **Correct:** the paid calls in the app are exactly three:
  - Claude through the parse chain (`services/natural_search.py:34`, `get_parse_chain()` from
    `rag/query_parsing.py`);
  - Claude through the reasons chain (`services/similar_search.py:58`, `get_reasons_chain()` from
    `rag/reasons.py`);
  - Voyage through `store.embeddings.embed_query` (`services/similar_search.py:70`).
  `get_vector_store()` itself makes no Voyage call (it builds PGVector and runs its DDL). The
  scripts `index_sectors_langchain` and `rag_playground` also call them, and are out of scope.
- **Correct, checked further than the ticket:** the trip planner calls no paid API.
  `tests/test_agent_nodes.py::test_agent_package_imports_no_network_client` only parses the files in
  `app/agent/`, so it doesn't cover the code they call. A grep of `app/` for `get_chat_model`,
  `get_parse_chain`, `get_reasons_chain`, `get_vector_store`, `get_embeddings`, `app.rag`,
  `anthropic` and `voyageai` finds only the two search services, `rag/` itself and the two scripts.
  `services/trip_planner.py`, `group_search.py`, `groups.py`, `stays.py`, `group_matching.py` and
  `routers/planner.py` import none of them. So the cap covers every paid call the API makes. 019 and
  020 add no paid call either (019 plan, "External services").
- **Correct:** Claude's tokens are only logged (`UsageLogger.on_llm_end` in `rag/llm.py:33`, calling
  `log_tokens()` in `services/llm.py:10`). Both chains are `lru_cache`d with one `UsageLogger` each,
  so the handler is shared by every request.
- **Correct:** Voyage's token count is dropped by `langchain_voyageai` 0.4.1
  (`embeddings.py:205-220`, `_embed_regular` returns only `.embeddings`).
- **Correct:** `on_llm_end` fires before the structured-output parser runs (the chain is
  `prompt | model | parser`), so an unusable answer still reports its tokens (AC 9).
  `tests/test_rag_chain.py::FakeJsonModel` already builds that exact shape offline.
- **Correct:** `tzdata` is only in `uv.lock` with `marker = "sys_platform == 'win32'"`
  (`uv.lock:2010`, through psycopg). In 021's `python:3.12-slim` image `ZoneInfo("Europe/Madrid")`
  would depend on the OS time zone files, so `tzdata` becomes a direct dependency.
- **Correct:** `web/` shows a 503 from a search as a notice with the server's `detail`
  (`web/src/features/search/SearchPage.tsx:68-73`, `web/src/api/client.ts` `errorMessage()`), so no
  frontend change. The notice's title is "The assistant couldn't help with that", which fits well
  enough; the message says what happened.
- **Correct:** migration head is `dba2ced7e785` (add planner_runs), and plans 017 to 021 add no
  migration.
- **Missing from the ticket:** the search queries have no length limit, so a fixed Voyage price per
  call is not a ceiling (see Alternatives), and a single long natural-language query can overshoot
  the Claude cap by more than "a few cents" (see Risks).
- **Missing from the ticket:** writing the spend through the request's session would expire the
  loaded sectors in `/search/similar` and keep a transaction open during the paid call (see
  Alternatives). The plan uses a separate short connection.
- **Missing from the ticket:** a developer's `backend/.env` could set a cap (for example 0 to save
  money), which would turn every existing natural and similar test into a 503. A fixture pins the
  spending settings to their code defaults in every test.
- **Plan 023's count is out of date:** it assumes "021 about +13, 022 about +23". With the numbers
  below, the suite before 023 is 251, not 237.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. A daily cap on Claude and Voyage, stored per day and provider, checked before and counted after every paid call
**Files** (in build order: dependency, model and migration, backend, tests, docs):

*Dependency*
- `backend/pyproject.toml`, `backend/uv.lock`: `uv add tzdata`. **The user stops the dev server
  first** (by its exact PID; Windows + OneDrive locks `.venv`, CLAUDE.md trap). In the hand-off,
  say why it is direct now: the Madrid day in a Linux image. 021's Dockerfile needs no change
  (`uv sync --locked --no-dev` installs it).

*Model and migration*
- `backend/app/models/daily_spend.py` (new): `DailySpend`, table `daily_spend`:
  - `day: Mapped[date]` (`Date`, primary key);
  - `provider: Mapped[str]` (`String(20)`, primary key);
  - `amount_usd: Mapped[float]` (`Float`, `nullable=False`).
  One comment, why: one row per day and provider, so the total survives a restart, and a new day
  simply has no row yet.
- `backend/app/models/__init__.py`: import `DailySpend`, add it to `__all__`.
- `backend/alembic/versions/<rev>_add_daily_spend.py`: `uv run alembic revision --autogenerate -m
  "add daily_spend"`, `down_revision = "dba2ced7e785"`. Review it: only
  `op.create_table("daily_spend", ...)` with the composite primary key `(day, provider)`, and
  `downgrade()` drops the table. Nothing about `langchain_pg_*`, checkpoint or PostGIS tables. Then
  `uv run alembic upgrade head`, and once `downgrade -1` / `upgrade head` (the increment allows this
  on the dev DB).

*Settings*
- `backend/app/core/config.py` (as 021 left it; import `Field` from pydantic and `ZoneInfo`,
  `ZoneInfoNotFoundError` from `zoneinfo`). New fields, after the CORS setting, under one comment
  line: estimates for a ceiling, not an invoice; check the prices against the providers' price
  lists.
  - `claude_daily_cap_usd: float = Field(1.0, ge=0)`
  - `voyage_daily_cap_usd: float = Field(0.5, ge=0)`
  - `claude_input_usd_per_mtok: float = Field(3.0, ge=0)`
  - `claude_output_usd_per_mtok: float = Field(15.0, ge=0)`
  - `voyage_usd_per_mtok: float = Field(0.06, ge=0)`
  - `spending_timezone: str = "Europe/Madrid"`, plus `field_validator("spending_timezone")` that
    calls `ZoneInfo(value)` and turns `ZoneInfoNotFoundError` or `ValueError` into
    `ValueError("CRAGMATCH_SPENDING_TIMEZONE must be an IANA time zone, e.g. Europe/Madrid")`.
  Every new field has a default, so `.github/workflows/ci.yml` (018) and 021's tests need **no
  change**. With 021's `env_ignore_empty=True`, a blank value in `.env` means the default.
- `backend/.env.example` (Edit tool only; the hook blocks shell commands naming `.env`): a group
  "Daily spending cap (USD estimates; blank = default)" with the six `CRAGMATCH_` names as `KEY=""`,
  each with a comment line above giving its default and meaning ("0 switches Claude off",
  "IANA name, the day starts at midnight there").

*Spending cap*
- `backend/app/rag/llm.py`:
  - Move the "first generation's `usage_metadata`" lines of `UsageLogger.on_llm_end` into a private
    `_token_usage(response: LLMResult) -> dict | None`, which `UsageLogger` keeps using (behaviour
    unchanged).
  - Add `TokenCounter(BaseCallbackHandler)`: `input_tokens` and `output_tokens` start at 0;
    `on_llm_end` adds what `_token_usage` finds. Comment why: one instance per request, passed at
    `invoke`, because the chains are cached and shared between threads.
- `backend/app/services/spending.py` (new; no HTTP, no LangChain). Module docstring: every paid call
  is checked before (`ensure_under_cap`) and counted after (`record_spend`); a check followed by a
  call can overshoot the cap by the requests already running, which is accepted for an estimate;
  reads and writes use their own short connection, not the request's session (why, in one line).
  - `class Provider(StrEnum)`: `CLAUDE = "claude"`, `VOYAGE = "voyage"`.
  - `class DailyCapReached(Exception)`, with a `provider: Provider` attribute.
  - `utc_now() -> datetime`: `datetime.now(UTC)`. The one clock; tests replace it (AC 12).
  - `current_day(now: datetime | None = None) -> date`: `(now or utc_now())` converted with
    `ZoneInfo(settings.spending_timezone)`, then `.date()`. Settings are read at call time, so tests
    can change them.
  - `claude_cost(input_tokens: int, output_tokens: int) -> float` and
    `voyage_cost(text: str) -> float` (`len(text.encode("utf-8"))` times the price, over 1,000,000;
    comment why bytes: an upper bound on Voyage's tokens whatever the length). Pure.
  - `spent(db: Session, provider: Provider, day: date | None = None) -> float`: with
    `db.get_bind().connect()`, `scalar(select(DailySpend.amount_usd).where(...))`, or 0.0 when there
    is no row.
  - `ensure_under_cap(db: Session, *providers: Provider) -> None`: for each provider in order,
    raise `DailyCapReached(provider)` when `spent(...) >= cap` (cap from settings at call time). So
    a cap of 0 blocks from the first request (AC 8).
  - `record_spend(db: Session, provider: Provider, amount_usd: float) -> None`: nothing for an
    amount of 0 or less. Otherwise, in `db.get_bind().begin()`, a Postgres
    `insert(DailySpend).values(day=current_day(), provider=..., amount_usd=...)
    .on_conflict_do_update(index_elements=[DailySpend.day, DailySpend.provider],
    set_={"amount_usd": DailySpend.amount_usd + stmt.excluded.amount_usd})`. Comment why: one
    atomic statement, so two requests at the same moment both count.
- `backend/app/services/natural_search.py`:
  - `_parse(db, query)`: first `spending.ensure_under_cap(db, Provider.CLAUDE)`, **outside** the
    `try`, so the cap error is not turned into `AssistantUnavailableError`. Then
    `usage = TokenCounter()`, and inside the existing `try`,
    `get_parse_chain().invoke({"query": query}, config={"callbacks": [usage]})`. A `finally`
    records `spending.claude_cost(usage.input_tokens, usage.output_tokens)`. Comment why: the tokens
    are billed even when the answer then turns out unusable (AC 9).
  - `find_sectors_from_query` passes `db` to `_parse`. Docstring: Claude's cap is checked first.
- `backend/app/services/similar_search.py`:
  - `find_similar_sectors` starts with `spending.ensure_under_cap(db, Provider.VOYAGE,
    Provider.CLAUDE)`, before `get_vector_store()`. Comment why: the endpoint needs both, and a
    rejected request must make no call at all (AC 7).
  - After the `try`/`except` around `embed_query` (so only on success),
    `record_spend(db, Provider.VOYAGE, voyage_cost(query))`. A failed call is not counted (AC 9).
  - `_explain(db, query, docs)`: unchanged when there are no docs (no call, nothing counted).
    Otherwise a `TokenCounter` passed in the `invoke` config, and the Claude cost recorded in a
    `finally`, as in `_parse`. The existing fallback (log, return `{}`) stays.
- `backend/app/routers/search.py`: a module constant `DAILY_LIMIT_DETAIL` with the message above.
  Both endpoints add `except DailyCapReached as exc:` with
  `logger.warning("Daily spending cap reached for %s", exc.provider)` and
  `raise HTTPException(status_code=503, detail=DAILY_LIMIT_DETAIL)`. `request: Request` and `body`
  stay as they are (slowapi), and the decorators are unchanged, so the 429 still comes first.

*Test fixtures*
- `backend/conftest.py`:
  - autouse `pin_spending_settings(monkeypatch)`: sets each of the six spending fields on `settings`
    back to `Settings.model_fields[name].default`. Comment why: a cap in a developer's
    `backend/.env` must not change the results of the suite.
  - `set_clock(monkeypatch)`: returns a function that replaces `spending.utc_now` with a fixed
    aware `datetime` (AC 12).
  - `report_claude_usage`: returns a function `(config, input_tokens, output_tokens)` that calls
    `on_llm_end` on every handler in `config["callbacks"]` with an `LLMResult` whose `AIMessage`
    has `usage_metadata`, the way the real model does. A missing `config` fails the test, which is
    what we want: the service must pass its counter.

*Docs*
- `README.md`:
  - 021's "Settings" table: six new rows (name, default, one line each), plus one sentence: the
    caps are estimates in USD, and a reached cap answers 503 with its own message.
  - A short "Daily spending cap" paragraph under "Running locally": today's spend is in
    `daily_spend` (`docker compose exec db psql -U <user> -d <db> -c "select * from daily_spend"`),
    deleting today's row resets it, and after pulling this change run `uv run alembic upgrade
    head` (otherwise the first AI search fails with "UndefinedTable").
  - Project structure: `config.py` line adds "daily caps, prices and time zone";
    new lines `models/daily_spend.py` (DailySpend: estimated spend per day and provider) and
    `services/spending.py` (the daily cap: `ensure_under_cap()` before, `record_spend()` after every
    paid call); the `rag/llm.py` line adds "TokenCounter (one request's Claude tokens, for the cap)".
- `CLAUDE.md`, "Reuse before writing", one new line (ticket DoD): "Spending cap:
  `ensure_under_cap()` before and `record_spend()` after every Claude or Voyage call, with
  `claude_cost()` / `voyage_cost()` (`services/spending.py`); `TokenCounter` in `rag/llm.py` counts
  a request's Claude tokens." No other CLAUDE.md change.

**Reuses:** `get_parse_chain()`, `get_reasons_chain()`, `get_vector_store()` unchanged, and still
the seams the tests mock; the parsing in `UsageLogger.on_llm_end` (moved into `_token_usage`,
shared with `TokenCounter`); `log_tokens()` unchanged; `settings` and 021's config conventions
(`env_ignore_empty`, `hide_input_in_errors`, the `test_config.py` fixture and helper); the existing
503 pattern and `logger` in `routers/search.py`; `get_db`, `db_session` and `client`;
`FakeJsonModel` in `tests/test_rag_chain.py`; `apiRequest()` / `errorMessage()` / `isNoticeError` in
`web/` (no frontend change); the autogenerate-and-review flow for the migration.

**Tests:**

*`backend/tests/test_usage_logging.py`* (+1)
- `test_token_counter_adds_up_every_model_call`: two `on_llm_end` events (10/5, then 7/3) give 17
  in and 8 out; a message without usage adds nothing (AC 4).

*`backend/tests/test_rag_chain.py`* (+2), with the existing `FakeJsonModel`:
- `test_counter_given_at_invoke_sees_the_call_next_to_the_chain_logger`:
  `build_parse_chain(FakeJsonModel(CLEAR.model_dump_json())).invoke({"query": "q"},
  config={"callbacks": [counter]})`; the counter shows 10 in / 5 out, and the
  "Claude natural_search: 10 in / 5 out tokens" log line is still there (AC 4; proves the
  `merge_configs` assumption on the real chain shape).
- `test_counter_keeps_the_tokens_of_an_unusable_answer`: `FakeJsonModel("not json")` through
  `build_reasons_chain`; `invoke` raises `OutputParserException`, and the counter still shows
  10 / 5 (AC 9).

*`backend/tests/test_config.py`* (+4), with 021's env-clearing fixture and `Settings(_env_file=None)`:
- `test_spending_settings_have_defaults`: only the required settings; caps 1.0 and 0.5, prices
  3.0 / 15.0 / 0.06, time zone `Europe/Madrid` (AC 11).
- `test_spending_settings_come_from_the_environment`: `CRAGMATCH_CLAUDE_DAILY_CAP_USD=2.5`,
  `CRAGMATCH_VOYAGE_USD_PER_MTOK=0.1`, `CRAGMATCH_SPENDING_TIMEZONE=Europe/Lisbon` are read as given
  (AC 11).
- `test_bad_spending_settings_are_rejected[negative_cap]` and `[unknown_time_zone]`,
  parametrized: `CRAGMATCH_CLAUDE_DAILY_CAP_USD=-1` and `CRAGMATCH_SPENDING_TIMEZONE=Mars/Olympus`
  each give a `ValidationError` naming the field (AC 11).

*`backend/tests/test_spending.py`* (new, +13), with `db_session`, `set_clock` and `monkeypatch` on
`settings`:
- `test_claude_cost_uses_the_prices_in_settings`: with prices 3 and 15, one million in and one
  million out cost 18.0; 0 and 0 cost 0.0.
- `test_voyage_cost_counts_every_byte_of_the_text`: with price 1.0 per million, `"abcd"` costs
  4e-6 and `"é"` costs 2e-6 (two UTF-8 bytes).
- `test_day_follows_the_time_zone_in_settings`: with `Europe/Madrid`, 2026-10-13 21:59 UTC is the
  13th and 22:30 UTC is the 14th (summer time, UTC+2); 2026-12-31 23:30 UTC is 2027-01-01 (winter,
  UTC+1). With `Europe/London`, 2026-10-13 22:30 UTC is still the 13th (AC 6, 11).
- `test_nothing_spent_is_zero`: no row gives 0.0 for both providers.
- `test_spend_adds_up_per_day_and_provider`: Claude 0.2 then 0.3 gives 0.5 in one row; Voyage 0.1
  is read back on its own (AC 4).
- `test_zero_amount_writes_no_row`: `record_spend(..., 0.0)` leaves `daily_spend` empty.
- `test_a_new_day_starts_from_zero`: clock on the 13th, record 0.9 Claude; clock moved to the 14th:
  `spent` is 0.0 and `ensure_under_cap` passes with a cap of 0.5; the 13th still reads 0.9 (AC 6).
- `test_spend_survives_a_restart`: record, then `db_session.get_bind().dispose()` (every pooled
  connection closed) and a brand-new `Session(bind=...)` reads the same amount; nothing is kept in
  a Python object (AC 5).
- `test_records_at_the_same_time_lose_nothing`: 4 threads (`ThreadPoolExecutor`) each record 0.01
  twenty-five times; the total is `pytest.approx(1.0)` (the atomic upsert; ticket note).
- `test_under_the_cap_passes`: 0.99 spent of a 1.0 cap, `ensure_under_cap` returns.
- `test_reaching_the_cap_raises_for_that_provider`: exactly 1.0 of 1.0 raises `DailyCapReached`
  with `provider == Provider.CLAUDE`; `ensure_under_cap(db, VOYAGE, CLAUDE)` with only Claude over
  raises for Claude, and with only Voyage over raises for Voyage (AC 1, 3).
- `test_cap_of_zero_blocks_at_once`: cap 0, nothing spent, raises (AC 8).
- `test_free_endpoints_work_when_both_caps_are_reached`, with `client` and both caps set to 0: all
  succeed (AC 2):
  - `GET /sectors/search?min_grade=6a&max_grade=7a` answers 200;
  - `POST /groups/` answers 201, adding a member answers 201;
  - `GET /groups/{code}/search` answers 200;
  - `GET /sectors/{id}/stays` and `GET /groups/{code}/sectors/{id}/stays` answer 200;
  - `POST /groups/{code}/planner/runs` answers 201 (the fixture's in-memory planner).

*`backend/tests/test_natural_api.py`* (+6). `FakeParseChain.invoke(inputs, config=None)` gains an
optional `usage: tuple[int, int] | None = None`; when set, it calls `report_claude_usage(config,
*usage)` before raising or answering. The `chain` fixture passes the reporter in. Existing tests
are unchanged (usage stays `None`).
- `test_natural_counts_claude_spend`: usage (1000, 500); 200 as before, and
  `spending.spent(db_session, Provider.CLAUDE) == pytest.approx(claude_cost(1000, 500))` (AC 4).
- `test_natural_counts_the_tokens_of_an_unusable_answer`: usage reported, then
  `OutputParserException`; 503 "assistant is unavailable" as today, and the spend is counted
  (AC 9).
- `test_natural_rejects_at_the_daily_limit_without_calling_claude`: Claude spend recorded up to its
  cap; 503 with `DAILY_LIMIT_DETAIL` (it contains "spending limit" and "tomorrow"), and
  `chain.calls == []` (AC 1, 7).
- `test_natural_ignores_the_voyage_cap`: Voyage cap 0; 200 and the chain was called (AC 3).
- `test_natural_daily_limit_comes_after_the_rate_limit`: limiter on (monkeypatch `enabled`,
  `limiter.reset()`, as in `test_natural_is_rate_limited`), Claude cap 0; 11 requests give
  `[503] * 10 + [429]`, the first detail is `DAILY_LIMIT_DETAIL`, and `chain.calls == []` (AC 10).
- `test_natural_works_again_the_next_day`: clock on the 13th, spend at the cap, 503; clock moved to
  the 14th, 200 and the chain was called once (AC 6, 12).

*`backend/tests/test_similar_api.py`* (+6). `FakeStore` records `embed_calls` (the texts);
`FakeChain.invoke(inputs, config=None)` gets the same optional `usage` as above.
- `test_similar_counts_voyage_and_claude_spend`: one result, usage (800, 200), query `"quiet
  crag"`; 200, Voyage spend `== approx(voyage_cost("quiet crag"))` and Claude spend
  `== approx(claude_cost(800, 200))` (AC 4).
- `test_similar_with_no_matches_counts_only_voyage`: empty store; Voyage spend > 0, Claude 0.0
  (Claude was never called).
- `test_similar_does_not_count_a_failed_embedding`: `embed_error` set; 503 "embedding service" as
  today, and Voyage spend is 0.0 (AC 9).
- `test_similar_counts_the_tokens_when_the_reasons_fail`: usage reported, then the chain raises;
  200 with `reason` None as today, and the Claude spend is counted (AC 9).
- `test_similar_with_voyage_switched_off_makes_no_call`: Voyage cap 0; 503 with
  `DAILY_LIMIT_DETAIL`, and `store.embed_calls`, `store.search_calls`, `chain.calls` are all empty
  (AC 1, 7, 8).
- `test_similar_rejects_at_the_claude_limit_without_any_call`: Claude spend at its cap, Voyage
  under; the same 503, and no Voyage, store or Claude call (AC 3, 7).

**Expected suite:** **251 passed**: 199 collected today; before 022, +0 (017), +0 (018), +3 (019),
+0 (020, backend), +17 (021), so 219; and **32 new** here (1 usage logging, 2 rag chain, 4 config
counting the parametrized test twice, 13 spending, 6 natural, 6 similar). If the count before 022
differs, it is that count plus 32. `uv run ruff check .` is clean. No frontend change, so no
`npm` check is needed (the reviewer can still run `npm run lint` in `web/` to confirm nothing moved).

**Check by hand** (the user; Docker Desktop running):
1. Migration: `uv run alembic upgrade head`, then `uv run alembic downgrade -1` and
   `uv run alembic upgrade head` again; both succeed and `\d daily_spend` in psql shows the
   composite primary key.
2. Counting (AC 4): dev server and `npm run dev` in `web/`. One natural-language search, then
   `select * from daily_spend` shows today's Madrid date with a `claude` row above 0 (and the log
   shows "Claude natural_search: N in / M out tokens"). One vibe search adds a `voyage` row and
   raises the `claude` row.
3. Restart (AC 5): stop the dev server (exact PID), start it again; the same query gives the same
   totals.
4. The cap (AC 1, 2, 3, 7): set `CRAGMATCH_CLAUDE_DAILY_CAP_USD=0` in `backend/.env` (the user edits
   it) and restart. A natural search in `web/` shows the notice "Today's spending limit for the AI
   searches is reached. Try again tomorrow, or use the filter search."; the server log shows
   "Daily spending cap reached for claude" and no new "Claude natural_search" token line. A vibe
   search shows the same notice and the `voyage` row does not grow. The filter search, a group with
   its search and stays, and a planner run on the group screen all work. Then set the Claude cap
   back to blank and `CRAGMATCH_VOYAGE_DAILY_CAP_USD=0`: the natural search works again, the vibe
   search shows the notice. Blank both afterwards.
5. Container (021's profile): `docker compose --profile prod build api`, then
   `docker compose --profile prod run --rm api python -c "from app.services.spending import
   current_day; print(current_day())"` prints today's date in Madrid (tzdata in the Linux image),
   and `docker compose --profile prod run --rm api alembic upgrade head` reports the new head.

**Commit:** `Ticket 022: daily spending cap on Claude and Voyage, estimated spend stored per Madrid day and provider in daily_spend (atomic upsert, survives restarts), checked before and counted after every paid call in natural and similar search, Claude from per-request token counts and Voyage from query bytes, 503 with its own message when a cap is reached, caps, prices and time zone in settings with defaults, tzdata as a direct dependency, README and CLAUDE.md updated`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `test_natural_api.py::test_natural_rejects_at_the_daily_limit_without_calling_claude`; `test_similar_api.py::test_similar_with_voyage_switched_off_makes_no_call`; `test_spending.py::test_reaching_the_cap_raises_for_that_provider`; manual check 4 |
| 2 | `test_spending.py::test_free_endpoints_work_when_both_caps_are_reached`; manual check 4 |
| 3 | `test_natural_api.py::test_natural_ignores_the_voyage_cap`; `test_similar_api.py::test_similar_rejects_at_the_claude_limit_without_any_call`; `test_spending.py::test_reaching_the_cap_raises_for_that_provider`; manual check 4 |
| 4 | `test_natural_api.py::test_natural_counts_claude_spend`; `test_similar_api.py::test_similar_counts_voyage_and_claude_spend`, `::test_similar_with_no_matches_counts_only_voyage`; `test_spending.py::test_spend_adds_up_per_day_and_provider`; `test_usage_logging.py::test_token_counter_adds_up_every_model_call`; `test_rag_chain.py::test_counter_given_at_invoke_sees_the_call_next_to_the_chain_logger`; manual check 2 |
| 5 | `test_spending.py::test_spend_survives_a_restart`; manual check 3 |
| 6 | `test_spending.py::test_a_new_day_starts_from_zero`, `::test_day_follows_the_time_zone_in_settings`; `test_natural_api.py::test_natural_works_again_the_next_day` |
| 7 | The "without calling claude" / "makes no call" / "without any call" tests in `test_natural_api.py` and `test_similar_api.py` (fakes record zero calls); `test_natural_api.py::test_natural_daily_limit_comes_after_the_rate_limit` |
| 8 | `test_spending.py::test_cap_of_zero_blocks_at_once`; `test_similar_api.py::test_similar_with_voyage_switched_off_makes_no_call` |
| 9 | `test_natural_api.py::test_natural_counts_the_tokens_of_an_unusable_answer`; `test_similar_api.py::test_similar_counts_the_tokens_when_the_reasons_fail`, `::test_similar_does_not_count_a_failed_embedding`; `test_rag_chain.py::test_counter_keeps_the_tokens_of_an_unusable_answer` |
| 10 | `test_natural_api.py::test_natural_daily_limit_comes_after_the_rate_limit` (503 while under the rate limit, 429 on the 11th) |
| 11 | `test_config.py::test_spending_settings_have_defaults`, `::test_spending_settings_come_from_the_environment`, `::test_bad_spending_settings_are_rejected[*]`; `test_spending.py::test_day_follows_the_time_zone_in_settings`, `::test_claude_cost_uses_the_prices_in_settings`; the whole suite green with ci.yml unchanged |
| 12 | Every new test uses the fakes and `set_clock`; no network client is built (the fakes replace `get_parse_chain`, `get_reasons_chain`, `get_vector_store`); 018's CI blocks outbound HTTP |

No criterion is left uncovered. AC 10's 503-before-429 order is covered for `/search/natural`
only; `/search/similar` uses the same decorator and the same `except`, which the reviewer checks.

## Risks
- **One long query overshoots more than "a few cents":** the queries have no `max_length`. A
  natural-language query near Claude's context limit costs about 0.60 USD in input tokens and is
  only counted after the call, and up to 10 such requests per minute per IP can be in flight past
  the check. After that burst the cap holds. Voyage stays bounded (bytes are counted). A
  `max_length` on both query fields (for example 500 characters, a 422 beyond it) would bound it,
  but it changes the API and is not in this ticket: **suggest it to the user** as a small follow-up
  (or an addition here if they agree) before 025 puts the endpoints on the internet.
- **Unverified Claude prices:** see "Prices to verify". The defaults are a guess for Sonnet 5 until
  the user checks the price page. Long-context pricing (over 200k input tokens) is not modelled.
- **Concurrency:** check-then-call can overshoot by the requests already running (accepted, the
  ticket's note). The upsert itself is atomic, and `test_records_at_the_same_time_lose_nothing`
  shows no spend is lost.
- **Migration downgrade:** `downgrade()` drops `daily_spend` and today's totals with it. That only
  lifts the cap for the rest of the day; no other table refers to it. Tests use `create_all()`, so
  after pulling, run `uv run alembic upgrade head`, or the first AI search on the dev server fails
  with "UndefinedTable" (CLAUDE.md trap). Ticket 025 must run migrations before the new version
  takes traffic.
- **Existing data:** none changes. Groups, sectors, stays, planner runs and the `langchain_pg_*`
  tables are untouched.
- **Behaviour that must stay unchanged:** the 503 "assistant unavailable" and "embedding service"
  paths, the 400 and 422 paths, the reasons fallback in `/search/similar`, and the per-IP 429s. All
  existing tests in `test_natural_api.py`, `test_similar_api.py`, `test_rag_chain.py` and
  `test_usage_logging.py` pass with only the fakes' `invoke` signature widened. The token log line
  stays.
- **Two connections per search:** the spend read and write use their own short connection next to
  the request's session. SQLAlchemy's default pool (5 plus 10 overflow) has room; 024 and 025 size
  the managed database's connections and should count one more per concurrent AI search.
- **A cap set in `backend/.env`:** would have changed the suite's results; the autouse
  `pin_spending_settings` fixture pins the code defaults in every test.
- **External services:** no test touches the network; Claude and Voyage stay mocked at
  `natural_search.get_parse_chain`, `similar_search.get_vector_store` and
  `similar_search.get_reasons_chain`. Manual checks 2 and 4 make one or two real Voyage calls (free
  tier: 3 per minute) and a few Claude calls.
- **`uv add tzdata` on Windows + OneDrive:** stop the dev server first, or `.venv` is locked
  ("Access is denied").
- **Scripts are not counted:** `index_sectors_langchain` (also used by 023's data load) and
  `rag_playground` spend outside the cap, as the ticket's Out says.
- **Size:** the ticket is L: about 20 files (half of them tests and docs), one table, one migration,
  one service, one callback, two services and a router changed, 32 tests. It is one coherent
  change (counting without enforcing, or the reverse, can't be tested on its own), backend only, so
  one delivery is fine; the review is long but linear.

## Out of scope (copied from the ticket)
- Per-user quotas, billing pages, spend alerts by email: one cap per provider is enough for friends
  only. (An AWS billing alert is ticket 024.)
- Counting the scripts (`index_sectors_langchain`, `rag_playground`): run by hand, not through the
  services.
- A meter in the UI: the server's message is shown as the error.
- Changing the per-IP rate limits.
