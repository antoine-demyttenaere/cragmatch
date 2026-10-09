# Plan for 005: Stage 6.6, query parsing with LangChain structured output

**Ticket:** `tickets/005-stage-6-6-structured-output.md`
**Approach:** `/search/natural` gets the same split as `/search/similar` in 004. A new
`app/rag/query_parsing.py` holds the unchanged Stage 3 prompt and a cached chain,
`PARSE_PROMPT | llm.with_structured_output(ParsedFilters, method="json_schema")`. A new
`services/natural_search.py` runs that chain and applies today's rules (understood, style,
grades, distance from Barcelona). The router only maps four exceptions to 503/422/400.
Token usage comes back through one small LangChain callback, `UsageLogger`, attached to
both structured-output chains (this one and 004's reasons chain). Playground step 6.6 runs
Stage 3's `messages.parse` and the new chain on the same queries and prints the results
side by side.

**Alternatives considered:**
- *`with_structured_output` with its default `method="function_calling"`:* this
  doesn't work with our model. `get_chat_model()` leaves `thinking=None`, and
  `_supports_forced_tool_choice("claude-sonnet-5")` is True (`chat_models.py:1161-1164`).
  So LangChain takes the forced branch and sends `tool_choice=ParsedFilters`
  (`:2966-2985`). But Sonnet 5 has adaptive thinking on by default (`:1485-1489`), and the
  API rejects a forced tool call while thinking is on (LangChain's own comment at
  `:2832`). `method="json_schema"` sends `output_config.format` (`:2999-3012`). That's
  the same API feature Stage 3's `messages.parse(output_format=...)` uses, so the
  comparison is fair. It's also what `rag/reasons.py` already does.
- *`include_raw=True` for usage:* the chain would then return
  `{"raw", "parsed", "parsing_error"}` instead of `ParsedFilters`. Worse, it *catches*
  parse errors (`:3020-3030`), so every caller would have to re-raise them by hand. That
  adds exactly the boilerplate this stage is meant to remove, and it would have to be
  repeated for the reasons chain.
- *langchain_core's built-in `get_usage_metadata_callback()`:* it collects usage
  inside a `with` block, so each call site needs a `with`, a `try/finally` and a log
  loop. Our `UsageLogger` is ~15 lines, follows the same `on_llm_end` pattern as the
  built-in handler (`langchain_core/callbacks/usage.py:50-75`), and is attached once
  where the chain is built.
- *Keeping the rules (understood / style / grades) in the router:* that breaks CLAUDE.md
  ("routers are HTTP only"), and the task asks to move them.

## Ticket check
Verified against the working tree (004 increment 2 applied but not committed) and the
installed packages: `langchain-anthropic` 1.7.5, `langchain-core` 1.6.8, `anthropic` 1.7.0.
- `POST /search/natural` at `routers/search.py:53`: correct. The flow is as described:
  `client.messages.parse(model=LLM_MODEL, max_tokens=1024, system=SYSTEM_PROMPT, output_format=ParsedFilters)`,
  then `log_usage("natural_search", ...)`, then 422 / 400 (style) / 400 (grades, from
  `find_matching_sectors` ValueError). Any exception from Claude gives 503. All the logic
  sits in the router today, so it moves to a service.
- `ParsedFilters` at `schemas/search.py:10` with those five fields: correct.
- "No test for `/search/natural`": correct (`grep -rn natural backend/tests` finds nothing).
- **Raw request, slightly off:** "your raw Pydantic-validation loop". Stage 3 has no
  hand-written validation loop. It already uses the SDK's `messages.parse(output_format=...)`,
  which sends the JSON schema and validates the answer with Pydantic. The side-by-side
  comparison is therefore SDK helper vs. LangChain runnable, not "manual loop vs.
  LangChain". The Walk-through says so honestly.
- **AC 1 literally says `with_structured_output(ParsedFilters)`**, which means the
  default method. The plan uses `method="json_schema"` on purpose (see Alternatives).
  It is still `with_structured_output`.
- **Correction to 004's plan:** 004 said the default method "only warns and raises
  `OutputParserException`". That only happens when `thinking` is set *explicitly*
  (`:2630-2659`). With our factory (`thinking=None`), the forced call is sent and the API
  is expected to reject it. That's not verified live (tests never touch the network),
  but the conclusion doesn't change: `json_schema`. The comment in `rag/reasons.py`
  ("the default forced tool call doesn't work with Sonnet 5's default thinking") stays
  accurate.
- **A Stage 3 edge case that changes (for the better):** `ParsedMessage.parsed_output`
  returns `None` when no text block parsed (`anthropic/types/parsed_message.py:78-82`,
  e.g. a refusal or a cut-off answer). Stage 3 then hits `filters.understood` on `None`,
  which gives a 500. In LangChain, `PydanticOutputParser` raises `OutputParserException`
  instead, which lands in the same `except` as "Claude failed", so the answer is 503 with
  the current message. A test covers it (AC 4).
- **Parity of settings:** `get_chat_model()` uses the same model, `max_tokens=1024`,
  `timeout=20.0` and `max_retries=2` as Stage 3's `client`. So the failure timing and
  the output budget are unchanged.
- **The prompt can go into a `ChatPromptTemplate` verbatim:** `SYSTEM_PROMPT`
  (`routers/search.py:26-48`) contains no `{` or `}`, so templating doesn't change it.
  A test asserts the system message equals the text exactly. The user's query is a
  *value* for `{query}`, and values are never re-templated, so braces typed by a user
  are harmless.
- **Token usage for the reasons chain (004's open point):** included in increment 1.
  It's the same `UsageLogger` with one line in `build_reasons_chain`, and 004 explicitly
  deferred it to this ticket. That keeps AC 5's promise ("token usage is still logged")
  for every Claude call the API makes.
- **What's left of the Stage 3 client:** after this ticket, `client` and `log_usage()` in
  `services/llm.py` have no API callers; only playground 6.6 uses them (the Stage 3 side
  of the comparison). **Keep them.** They're listed in CLAUDE.md "Reuse", and the
  comparison needs them. They can go at the end of Stage 6 together with `embed_query()`.
  `LLM_MODEL` stays (used by `rag/llm.py`).
- **Usage numbers:** LangChain's `usage_metadata["input_tokens"]` adds cache-read and
  cache-creation tokens to Anthropic's `input_tokens` (`chat_models.py:3340-3348`). We
  don't use prompt caching, so the numbers match `log_usage()`'s.
- Frontend: `SearchPage.tsx:91` reads `parsed_filters` and `results`. The shape doesn't
  change, so no frontend work and no `types.ts` change. No model change, no migration,
  no new dependency (`GenericFakeChatModel` and `PydanticOutputParser` ship with
  `langchain-core`).
- Baseline: `uv run pytest --collect-only -q` → **108 tests** on the working tree.

## Before you start (every increment)
- **Never run two pytest runs at once.** Two runs on `cragmatch_test` deadlock (the Stop
  hook may be running the suite while you are). `wmic` is **not installed** on this
  machine, so 004's check command doesn't work. Use this one from Git Bash instead; it
  must print nothing:
  `powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'pytest' } | Select-Object ProcessId, CommandLine | Format-List"`
  If it prints a process, wait and check again. Never stop it yourself. Run pytest in the
  **foreground**, never in the background.
- Tests never touch the network: Claude is always a fake. Patch where the function is
  *used* (`app.services.natural_search.get_parse_chain`, `app.rag.query_parsing.get_chat_model`,
  `app.scripts.rag_playground.client` / `.get_parse_chain`).
- Every fake that is cached through `lru_cache` gets a `cache_clear()` fixture with
  `yield` (same as `clean_reasons_cache` in `tests/test_rag_chain.py`).
- No `uv add` / `uv sync`.

## Increments

### 1. LangChain token-usage logging, applied to the reasons chain
**Files:**
- `backend/app/services/llm.py`:
  - New `log_tokens(purpose: str, input_tokens: int, output_tokens: int) -> None`. It
    holds the one existing format string, `"Claude %s: %d in / %d out tokens"`.
  - `log_usage(purpose, response)` now calls
    `log_tokens(purpose, response.usage.input_tokens, response.usage.output_tokens)`.
    Why-comment: one log format for the SDK path and the LangChain path, so the log
    lines look the same.
- `backend/app/rag/llm.py`:
  - New `class UsageLogger(BaseCallbackHandler)` (import from `langchain_core.callbacks`):
    - `__init__(self, purpose: str)` stores the purpose.
    - `on_llm_end(self, response: LLMResult, **kwargs: Any) -> None`: takes the first
      generation if there is one (the same guard as langchain_core's
      `UsageMetadataCallbackHandler`). If it has a `message` with `usage_metadata`, it
      calls `log_tokens(self.purpose, usage["input_tokens"], usage["output_tokens"])`.
      If there's no usage, it does nothing.
    - Why-comment: `with_structured_output` returns only the parsed object, so usage is
      read where LangChain still sees the raw message, in the model's `on_llm_end`
      event. LangChain catches exceptions raised in a callback, so logging can never
      break a request.
- `backend/app/rag/reasons.py`: `build_reasons_chain()` returns
  `(REASONS_PROMPT | llm.with_structured_output(MatchReasons, method="json_schema")).with_config(callbacks=[UsageLogger("reasons")])`.
  Extend its comment: the callback brings back the token log that `explain_matches()`
  had. Callbacks set with `with_config` reach every step inside the chain, including the
  model.
- `README.md`: the `services/llm.py` line becomes "Anthropic client (timeout/retries) +
  token usage logging (log_usage, log_tokens)". The `rag/llm.py` line becomes
  "get_chat_model(): ChatAnthropic with the Stage 3 settings; UsageLogger callback (token
  usage)".
- **Leave alone:** routers, `services/similar_search.py`, `rag/chain.py` (its free-text
  chain isn't used by the API).

**Reuses:** the `log_usage()` format (`services/llm.py`), the `on_llm_end` pattern of
`langchain_core.callbacks.usage.UsageMetadataCallbackHandler`, `build_reasons_chain()`.

**Tests:**
- `tests/test_usage_logging.py` (new; no DB fixtures, uses `caplog`). Call
  `caplog.set_level(logging.INFO, logger="app.services.llm")` first, because the root
  level is WARNING in tests:
  - `test_log_usage_reads_an_anthropic_response`:
    `log_usage("natural_search", SimpleNamespace(usage=SimpleNamespace(input_tokens=12, output_tokens=3)))`
    → `"Claude natural_search: 12 in / 3 out tokens"` in `caplog.text`. This protects
    the Stage 3 path that playground 6.6 still uses. (AC 5)
  - `test_usage_logger_logs_tokens_of_a_model_call`:
    `UsageLogger("reasons").on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content="{}", usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}))]]), run_id=uuid4())`
    → `"Claude reasons: 10 in / 5 out tokens"`. (AC 5)
  - `test_usage_logger_skips_a_message_without_usage`: the same call with an `AIMessage`
    that has no `usage_metadata` raises nothing, and no record contains `"Claude"`.
- `tests/test_rag_chain.py` (extend):
  - A new fake, `FakeJsonModel(json_text: str)`. Its
    `with_structured_output(schema, **kwargs)` returns
    `GenericFakeChatModel(messages=iter([AIMessage(content=json_text, usage_metadata=USAGE)])) | PydanticOutputParser(pydantic_object=schema)`
    (`langchain_core.language_models.fake_chat_models`, `langchain_core.output_parsers`).
    That's the same `model | PydanticOutputParser` pair ChatAnthropic builds for
    `json_schema` (`chat_models.py:2999-3031`), but offline. Unlike the
    `RunnableLambda` fakes, it is a real chat model, so it fires `on_llm_end`.
    Docstring: why this fake exists.
  - `test_reasons_chain_logs_token_usage`:
    `build_reasons_chain(FakeJsonModel('{"reasons": [{"sector_id": 1, "reason": "Short approach."}]}')).invoke({"query": "q", "sectors": "id=1 | t"})`
    returns `MatchReasons(reasons=[MatchReason(sector_id=1, reason="Short approach.")])`,
    and `caplog.text` contains `"Claude reasons: 10 in / 5 out tokens"`. (AC 5, 004's gap)
  - The existing `test_reasons_chain_fills_prompt_and_asks_for_json_schema` and
    `test_get_reasons_chain_is_built_once` must pass unchanged.
- Expected suite after this increment: **112 passed** (108 + 4).

**Check by hand:** `uv run pytest -q` (after the process check, in the foreground) and
`uv run ruff check .` green. With the dev server running (the user, 1 Voyage + 1 Claude
call): `POST /search/similar {"query": "quiet crag, short approach"}` in `/docs`. The
server log shows `app.services.llm: Claude reasons: N in / M out tokens`, and the
response is unchanged.

**Commit:** `Stage 6.6 part 1: log Claude token usage from LangChain chains with a UsageLogger callback, shared log format with log_usage, applied to the reasons chain`

### 2. /search/natural on LangChain structured output, logic in a service, first endpoint tests
**Files:**
- `backend/app/rag/query_parsing.py` (new). Module docstring: the LangChain version of
  Stage 3's query parsing, with the same prompt and the same `ParsedFilters` schema.
  - `PARSE_SYSTEM_PROMPT: str`: `SYSTEM_PROMPT` from `routers/search.py:26-48`, moved
    **verbatim** (out of scope to change it). Comment: no `{}` allowed in this text,
    because it goes into a prompt template.
  - `PARSE_PROMPT = ChatPromptTemplate.from_messages([("system", PARSE_SYSTEM_PROMPT), ("human", "{query}")])`.
    This is the same layout as Stage 3's `system=` + one user message.
  - `build_parse_chain(llm: BaseChatModel) -> Runnable`: returns
    `(PARSE_PROMPT | llm.with_structured_output(ParsedFilters, method="json_schema")).with_config(callbacks=[UsageLogger("natural_search")])`.
    Why-comment: json_schema is Stage 3's `output_format` feature; the default forced
    tool call doesn't work with Sonnet 5's default thinking; `ParsedFilters`' field
    descriptions travel in the schema and act as instructions. Input: `{"query": str}`.
    Output: a `ParsedFilters` instance.
  - `get_parse_chain() -> Runnable`, with `lru_cache(maxsize=1)`: returns
    `build_parse_chain(get_chat_model())`. Same why-comment as `get_reasons_chain()`.
  - Import `ParsedFilters` from `app.schemas.search`. The API schema doubles as Claude's
    answer format, as in Stage 3. Unlike `MatchReasons`, it *is* returned to clients.
- `backend/app/services/natural_search.py` (new). Module docstring in the style of
  `similar_search.py`: Claude turns the text into filters (chain in `app/rag`), then the
  Stage 1 filter runs. The router only turns errors into HTTP codes.
  - Three exception classes, one docstring line each:
    - `AssistantUnavailableError`: Claude couldn't be reached or gave an unusable answer.
    - `QueryNotUnderstoodError`: Claude says the text isn't a climbing search. It's an
      exception and not a "no result", because the API contract answers it with 422.
    - `UnusableFiltersError`: the parsed filters can't be applied. `str(exc)` is the
      message for the user.
  - `_parse(query: str) -> ParsedFilters`:
    `try: return get_parse_chain().invoke({"query": query})`,
    `except Exception as exc: raise AssistantUnavailableError from exc`. Building the
    chain is inside the `try` too, so a missing key or bad config is also "assistant
    unavailable" (the same as Stage 3, where the call failed). Why-comment: this also
    catches `OutputParserException`, where Stage 3 would have crashed with a 500 on
    `parsed_output=None`.
  - `_style(filters: ParsedFilters) -> ClimbingStyle | None`: `None` when
    `not filters.style` (the same truthiness as today, so `""` also means "any"). On
    `ValueError` it raises
    `UnusableFiltersError(f"Model returned an unrecognized style: {filters.style!r}")`.
  - `find_sectors_from_query(db: Session, query: str) -> NaturalSearchResponse`:
    `_parse`, then `if not filters.understood: raise QueryNotUnderstoodError`, then
    `_style`, then `find_matching_sectors(db, min_grade=..., max_grade=..., style=style, origin_lat=BARCELONA[0], origin_lon=BARCELONA[1], max_distance_km=filters.max_distance_km)`.
    Only that call sits in a `try`, so a DB error stays a 500. Its `ValueError` raises
    `UnusableFiltersError(f"Couldn't understand the grade range in that query: {filters.min_grade}-{filters.max_grade}")`.
    Returns `NaturalSearchResponse(parsed_filters=filters, results=results)`. The checks
    run in the same order as today (422 before 400).
  - Import `get_parse_chain` **by name**, so tests can patch it on this module.
- `backend/app/routers/search.py`:
  - `search_natural` body becomes: `try: return find_sectors_from_query(db, body.query)`.
    `except AssistantUnavailableError:` logs
    `logger.exception("Failed to parse natural language query")` and raises
    `HTTPException(503, "The search assistant is unavailable, try the search form instead.")`.
    `except QueryNotUnderstoodError:` → 422,
    `"Couldn't understand that as a climbing search — try the search form instead."`.
    `except UnusableFiltersError as exc:` → 400, `detail=str(exc)`. **Copy the 503 and
    422 strings from the current file**: the 422 one contains an em dash (U+2014), not a
    hyphen.
  - Keep `@limiter.limit("10/minute")`, `request: Request`, `body`,
    `response_model=NaturalSearchResponse`.
  - Remove `SYSTEM_PROMPT` and the imports that become unused: `ClimbingStyle`,
    `ParsedFilters`, `BARCELONA`, `find_matching_sectors`, `LLM_MODEL`, `client`,
    `log_usage`. Leave `/search/similar` untouched.
- `backend/tests/test_natural_api.py` (new). See below.
- `README.md`:
  - `routers/search.py` line: `/search/natural (LangChain structured output) and /search/similar (...)`.
  - `services/`: add `natural_search.py  /search/natural logic: Claude's filters (parse chain), then find_matching_sectors().`
  - `rag/`: add `query_parsing.py   Natural-language query to ParsedFilters: Stage 3 prompt, build_parse_chain(), get_parse_chain().`
- **Leave alone:** `schemas/search.py` (`ParsedFilters` unchanged, out of scope),
  `services/llm.py` (`client` / `log_usage` stay for the playground), the frontend.

**Reuses:** `get_chat_model()` and `UsageLogger` (`rag/llm.py`), the `build_*_chain` /
cached `get_*_chain` pattern of `rag/reasons.py`, `ParsedFilters` / `NaturalSearchResponse`
(`schemas/search.py`), `find_matching_sectors()` (`services/search.py`), `BARCELONA`
(`services/geo.py`), `ClimbingStyle`, the service-raises / router-maps pattern of
`services/similar_search.py` (`EmbeddingUnavailableError`), `get_db`, `limiter`.

**Tests:**
- `tests/test_rag_chain.py` (extend). Add a module-level constant
  `CLEAR = ParsedFilters(understood=True, min_grade="6b", max_grade="6b", max_distance_km=200, style="sport")`
  (increment 3 uses it too). Generalise `FakeStructuredModel` to take an `answer`
  argument (default: today's `MatchReasons`), so it can return a `ParsedFilters` too:
  - `test_parse_chain_fills_prompt_and_asks_for_json_schema`:
    `build_parse_chain(FakeStructuredModel(answer=CLEAR)).invoke({"query": "around 6b, sport"})`
    returns `CLEAR`. The recorded schema `is ParsedFilters`, `kwargs["method"] == "json_schema"`,
    the system message `.content == PARSE_SYSTEM_PROMPT` (verbatim, nothing templated
    away), and the human message `.content == "around 6b, sport"`. (AC 2: same prompt and
    contract)
  - `test_parse_chain_logs_token_usage`: `build_parse_chain(FakeJsonModel(CLEAR.model_dump_json())).invoke(...)`
    returns a `ParsedFilters` equal to `CLEAR`, and the log contains
    `"Claude natural_search: 10 in / 5 out tokens"`. (AC 5)
  - `test_get_parse_chain_is_built_once`: the same shape as the reasons test, with a
    `clean_parse_cache` fixture (`get_parse_chain.cache_clear()` before and after) and
    `monkeypatch.setattr(query_parsing, "get_chat_model", counting_factory)`.
- `tests/test_natural_api.py` (new). Module docstring: the endpoint's only external call
  is Claude through `get_parse_chain()`, and an **autouse** fixture patches it on
  `app.services.natural_search` for every test, so a new test can't reach Claude. A
  `FakeParseChain` has `answer` (default: understood, `"4"`–`"9c+"`, 200 km, no style),
  `error` (raised by `invoke` if set) and `calls` (every `inputs` dict). It returns its
  `answer`. The helper `_make_sector(client, name, style, lat, lon) -> int` creates a crag
  and a sector (6a–7a) through the API, as in `test_similar_api.py`. The same `CLEAR`
  constant as in `test_rag_chain.py`.
  Tests (9):
  - `test_natural_returns_parsed_filters_and_matching_sectors`: "Sporty" (sport) and
    "Blocs" (boulder), both at (41.4, 2.0). The answer is `CLEAR`, and the query is
    `"something around 6b, not too far, sport"`. Asserts: 200, top-level keys are exactly
    `{"parsed_filters", "results"}`, `parsed_filters == CLEAR.model_dump()`, the result
    names are `["Sporty"]`, and `chain.calls == [{"query": "something around 6b, not too far, sport"}]`. (AC 2, AC 6)
  - `test_natural_measures_distance_from_barcelona`: "Near" at (41.4, 2.0) (~14 km) and
    "Far" at (41.0, 1.0) (~107 km), both sport. The answer has `max_distance_km=50` and
    `style=None`. Result: `["Near"]`. (AC 2: the same filters as before, origin
    `BARCELONA`)
  - `test_natural_returns_422_when_query_not_understood`: `understood=False`. 422, with
    the exact current detail. (AC 3, AC 6)
  - `test_natural_returns_400_for_unrecognized_style`: `style="ice"`. 400,
    `detail == "Model returned an unrecognized style: 'ice'"`. (AC 6)
  - `test_natural_returns_400_for_unknown_grade`: `min_grade="6z"`, `max_grade="6b"`.
    400, `detail == "Couldn't understand the grade range in that query: 6z-6b"`.
    (unchanged behaviour, main error case)
  - `test_natural_returns_503_when_claude_fails`: `chain.error = RuntimeError("Claude is down")`.
    503, `detail == "The search assistant is unavailable, try the search form instead."`.
    (AC 4, AC 6)
  - `test_natural_returns_503_when_answer_is_unusable`:
    `chain.error = OutputParserException("not JSON")` (`langchain_core.exceptions`). 503
    with the same detail. (AC 4; Stage 3 gave a 500 here)
  - `test_natural_returns_503_when_chain_cannot_be_built`: patch `get_parse_chain` with
    a function that raises `RuntimeError("missing API key")`. 503. (AC 4)
  - `test_natural_is_rate_limited`: the same pattern as `test_similar_is_rate_limited`
    (`monkeypatch.setattr(limiter, "enabled", True)`, `limiter.reset()`, collect 11
    status codes) with the default answer and an empty DB. The codes are exactly
    `[200] * 10 + [429]`. (unchanged behaviour)
- Expected suite after this increment: **124 passed** (112 + 3 + 9).

**Check by hand** (the user, DB up, dev server running; 3 Claude calls, no Voyage):
1. In `/docs`, `POST /search/natural {"query": "something around 6b, not too far, sport"}`:
   200, `parsed_filters` (6b-ish, a distance, `"sport"`) and `results`. The server log
   shows `app.services.llm: Claude natural_search: N in / M out tokens` (AC 2, AC 5).
2. `{"query": "what is your favorite color"}` → 422 with the same message as before (AC 3).
3. The frontend natural-language search: results and the parsed filters still show.
4. Developer: `uv run pytest -q` (after the process check, in the foreground) and
   `uv run ruff check .` green. `git grep -n "SYSTEM_PROMPT\|messages.parse" -- backend/app/routers`
   returns nothing.

**Commit:** `Stage 6.6 part 2: /search/natural parses queries with LangChain structured output (same prompt and ParsedFilters, json_schema method) through a new natural_search service; the router only maps errors; first endpoint tests`

### 3. Playground step 6.6: Stage 3 messages.parse vs. LangChain, side by side
**Files:**
- `backend/app/scripts/rag_playground.py`:
  - Docstring: add `uv run python -m app.scripts.rag_playground 6.6`.
  - Imports: `client`, `LLM_MODEL`, `log_usage` (`app.services.llm`), `ParsedFilters`
    (`app.schemas.search`), `PARSE_SYSTEM_PROMPT`, `get_parse_chain` (`app.rag.query_parsing`).
  - `NATURAL_QUERIES`: 4 queries, `"something around 6b, not too far, sport"`,
    `"easy bouldering, at most an hour and a half by car"`,
    `"long multi-pitch routes between 6a and 6c+"`, `"what is your favorite color"`
    (the off-topic one, which should give `understood=False` on both sides).
  - `parse_with_messages_api(query: str) -> ParsedFilters | None`: Stage 3's call, kept
    here for the comparison now that it has left the router. It's the pre-005 router
    code (the Stage 3 snippet in the Walk-through below, or
    `git show HEAD~1:backend/app/routers/search.py` lines 55-73 while increment 2 is the
    last commit):
    `client.messages.parse(model=LLM_MODEL, max_tokens=1024, system=PARSE_SYSTEM_PROMPT, messages=[{"role": "user", "content": query}], output_format=ParsedFilters)`,
    then `log_usage("natural_search_stage3", response)`, then return
    `response.parsed_output`.
  - `step_6_6(queries: list[str] = NATURAL_QUERIES)`. Docstring: "Stage 3
    messages.parse vs. LangChain with_structured_output, same prompt and schema. 2
    Claude calls per query, no Voyage." Build `chain = get_parse_chain()` once. For each
    query: print `=== Step 6.6: '<query>' ===` and a header `field / Stage 3 / LangChain`.
    Then print one row per name in `ParsedFilters.model_fields`, with both values and
    `same` or `DIFFERS`. A `None` side prints `(none)`. After the loop, print one line:
    differences in `max_distance_km` or the grades are normal, because they're Claude's
    estimates and two calls can round differently.
  - `STEPS`: add `"6.6": step_6_6`.
- `README.md`: nothing new (the `rag_playground.py` line already says "Stage 6 steps").

**Reuses:** `client` / `LLM_MODEL` / `log_usage()` (`services/llm.py`), `PARSE_SYSTEM_PROMPT`
and `get_parse_chain()` (increment 2), `ParsedFilters`, the step / `STEPS` pattern of
the playground.

**Tests:** `tests/test_rag_chain.py` (extend):
- `test_step_6_6_prints_both_parsers_side_by_side`. A fake `client` is
  `SimpleNamespace(messages=SimpleNamespace(parse=fake_parse))`. `fake_parse(**kwargs)`
  records `kwargs` and returns
  `SimpleNamespace(parsed_output=CLEAR, usage=SimpleNamespace(input_tokens=1, output_tokens=1))`.
  A fake chain records `invoke` inputs and returns `CLEAR` with `style=None`. Monkeypatch
  `rag_playground.client` and `rag_playground.get_parse_chain`. Run
  `rag_playground.step_6_6(["q one", "q two"])`. Asserts:
  - both query headers are in the output;
  - the `style` row has `DIFFERS` and the `min_grade` row has `same`;
  - `fake_parse` was called twice, with `model == LLM_MODEL`, `system == PARSE_SYSTEM_PROMPT`,
    `output_format is ParsedFilters`, `max_tokens == 1024`,
    `messages == [{"role": "user", "content": "q one"}]`;
  - the chain got `[{"query": "q one"}, {"query": "q two"}]`;
  - `3 <= len(rag_playground.NATURAL_QUERIES) <= 4`. (AC 1)
- Expected suite after this increment: **125 passed**.

**Check by hand** (the user; 8 Claude calls, no Voyage):
`uv run python -m app.scripts.rag_playground 6.6`. You get four tables. The off-topic
query shows `understood False` in both columns. Mostly `same`, with maybe a `DIFFERS` on
distance. Then read the Walk-through below next to the output. Developer:
`uv run pytest -q` (after the process check, in the foreground) and `uv run ruff check .`
green.

**Commit:** `Stage 6.6 part 3: playground step 6.6 parses the same queries with Stage 3 messages.parse and the LangChain parse chain and prints them side by side`

## Walk-through: parsing one query, Stage 3 vs. LangChain
Example: `POST /search/natural {"query": "something around 6b, not too far, sport"}`.

**The idea is the same in both:** give Claude instructions plus a JSON schema, let the API
force the answer into that schema, then validate it into a `ParsedFilters` object. The
same prompt text and the same schema, so you should see the same filters.

**Stage 3 (before), everything in the router, once per request:**
```python
response = client.messages.parse(
    model=LLM_MODEL,
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": body.query}],
    output_format=ParsedFilters,     # SDK turns the class into a JSON schema
)
log_usage("natural_search", response)
filters = response.parsed_output     # ParsedFilters, or None if nothing parsed
```

**Stage 6.6 (now): build once, then one line per request:**
```python
# app/rag/query_parsing.py, built once per process
PARSE_PROMPT = ChatPromptTemplate.from_messages(
    [("system", PARSE_SYSTEM_PROMPT), ("human", "{query}")]
)
chain = (
    PARSE_PROMPT
    | get_chat_model().with_structured_output(ParsedFilters, method="json_schema")
).with_config(callbacks=[UsageLogger("natural_search")])

# services/natural_search.py, per request
filters = chain.invoke({"query": query})   # always a ParsedFilters, or an exception
```

| Concern | Stage 3 | LangChain |
|---|---|---|
| Instructions | `system=SYSTEM_PROMPT` on each call | the same text as the system message of a `ChatPromptTemplate`; `{query}` fills the human message |
| Schema | `output_format=ParsedFilters` | `with_structured_output(ParsedFilters, method="json_schema")` |
| What goes over the wire | `output_config.format` with the JSON schema | the same field, built with the same `anthropic.transform_schema` (`chat_models.py:3287`) |
| Model, max tokens, timeout | on the client and on each call | once, in `get_chat_model()` |
| Validation | the SDK fills `response.parsed_output` | `PydanticOutputParser` returns the object directly |
| Unusable answer | `parsed_output` is `None`, then a crash, then a 500 | `OutputParserException`, then 503 |
| Token usage | `log_usage(...)` after each call | a callback attached once; it fires on every model call |
| Where it lives | the router | prompt and chain in `app/rag`, rules in a service, HTTP in the router |

**Being honest about "less boilerplate":** Stage 3 never had a hand-written validation loop.
The SDK's `messages.parse` already did the schema and the validation. What LangChain
changes:
1. **The setup moves to build time.** The prompt, model settings, schema and usage
   logging are wired once. Each request is one `invoke`.
2. **It composes.** `prompt | model` is a `Runnable`. The same object can be a step in a
   bigger chain, or a node in the LangGraph planner (tickets 007-012), without changing
   it.
3. **It's swappable.** Any LangChain chat model has `with_structured_output`. The SDK
   version is Anthropic-only.
4. **Usage is no longer free.** Because `invoke` returns only the parsed object, the raw
   response (with its token counts) disappears. LangChain's answer is **callbacks**:
   while a chain runs, it sends events (`on_chain_start`, `on_llm_end`, ...) to every
   handler in its config. `with_config(callbacks=[...])` attaches a handler to the whole
   chain, and handlers are passed down to every step inside it. `UsageLogger` listens
   to just one event: the model's `on_llm_end`, where the raw message with
   `usage_metadata` is still available.

**Why `method="json_schema"` and not the default:** LangChain can get structured output in
two ways.
- **Function calling** pretends there's a tool named `ParsedFilters` and forces Claude to
  call it; the tool's arguments are the answer. The API refuses a *forced* tool call
  while Claude is thinking, and Sonnet 5 thinks by default.
- **JSON schema** constrains Claude's normal text answer to the schema. That's exactly
  what Stage 3's `output_format` does, and it works with thinking on.

**What didn't change:** the prompt text, `ParsedFilters`, the response shape, the 422 / 400
/ 503 messages, the 10/minute limit, the filtering (`find_matching_sectors` from
Barcelona), and the frontend.

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Increment 3: `tests/test_rag_chain.py::test_step_6_6_prints_both_parsers_side_by_side`; manual run of step 6.6 |
| 2 | Increment 2: `tests/test_natural_api.py::test_natural_returns_parsed_filters_and_matching_sectors`, `::test_natural_measures_distance_from_barcelona`, `tests/test_rag_chain.py::test_parse_chain_fills_prompt_and_asks_for_json_schema`; manual step 1 |
| 3 | Increment 2: `tests/test_natural_api.py::test_natural_returns_422_when_query_not_understood`; manual step 2 |
| 4 | Increment 2: `tests/test_natural_api.py::test_natural_returns_503_when_claude_fails`, `::test_natural_returns_503_when_answer_is_unusable`, `::test_natural_returns_503_when_chain_cannot_be_built` |
| 5 | Increment 1: `tests/test_usage_logging.py` (3 tests), `tests/test_rag_chain.py::test_reasons_chain_logs_token_usage`; increment 2: `tests/test_rag_chain.py::test_parse_chain_logs_token_usage`; manual log line in increments 1 and 2 |
| 6 | Increment 2: the autouse `FakeParseChain` fixture in `tests/test_natural_api.py` and the four named cases (clear query, 422, unknown style 400, 503) |

All criteria are covered. AC 5 at the endpoint level is covered in two parts: the tests
prove that the chain the service uses (`get_parse_chain` → `build_parse_chain`) logs
usage, and the manual check proves the log line appears on a real call. The endpoint
tests replace the whole chain, so they can't see the callback.

## Risks
- **Concurrent pytest deadlocks:** run the PowerShell check from "Before you start"
  before every run, and run pytest in the foreground. `wmic` doesn't exist on this
  machine.
- **Structured output on the real model:** the tests fake Claude, so only the manual
  checks prove that `json_schema` parsing of `ParsedFilters` works with `claude-sonnet-5`.
  The reasons chain already proves the method works for this model (004's manual check).
  If every natural query returns 503, the server log has the traceback (logged by the
  router).
- **Prompt text in a template:** a future `{` or `}` in `PARSE_SYSTEM_PROMPT` would turn
  into a template variable and break the chain (a KeyError → 503). The comment and the
  verbatim-equality test guard it.
- **Behaviour change (intended):** an unparseable answer now gives 503 instead of a 500.
  Every other status and message is unchanged and has a test.
- **Callback failures:** LangChain logs and swallows exceptions raised in callbacks, so a
  bug in `UsageLogger` costs a log line, never a request. The unit tests cover the
  "no usage" path.
- **Cached chain and threads:** like `get_reasons_chain()`, there's one chain (and one
  Anthropic client) per process, and `UsageLogger` keeps no state, so it is
  thread-safe. A fake in tests must never stay cached: use the `cache_clear()` fixture.
- **Cost and rate limits in the manual checks:** step 6.6 makes 8 Claude calls. The
  endpoint checks make 3 Claude calls plus 1 Voyage call (increment 1), and the
  endpoint is limited to 10/minute. Don't test the rate limit by hand; the test covers
  it.
- **Behaviour that must stay unchanged:** `/search/similar` (its tests must stay green
  in increment 1), playground steps 6.2-6.5, `ParsedFilters`, the frontend.
- **No migration, no dependency change.** Nothing to downgrade.

## Out of scope (copied from the ticket)
- Changing `ParsedFilters` or the prompt wording: same contract, different plumbing.
- The fuzzy path: that's ticket 004 (only the one-line usage callback is added to its
  reasons chain, as 004 deferred that to this ticket).
