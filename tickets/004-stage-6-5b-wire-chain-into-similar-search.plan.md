# Plan for 004: Stage 6.5b, wire the LangChain RAG path into the fuzzy search endpoint

**Ticket:** `tickets/004-stage-6-5b-wire-chain-into-similar-search.md`
**Approach:** `/search/similar` moves its logic into a new service,
`services/similar_search.py::find_similar_sectors()`. It runs in two steps. First it embeds
the query through the LangChain store's own Voyage embeddings and asks the cached PGVector
store for `(Document, distance)` pairs. Then it loads the `Sector` rows by id in one query,
keeping the store's order. The per-sector reasons come from a second, small LCEL chain in
a new `app/rag/reasons.py`: `REASONS_PROMPT | llm.with_structured_output(MatchReasons, method="json_schema")`.
It is the LangChain twin of Stage 3's `explain_matches()`, with the same prompt, the same
`MatchReasons` shape and the same response. The router stays HTTP only. The Stage 3 code
(`explain.py`, the raw pgvector query in the router) is deleted.

**Alternatives considered:**
- *Reuse `build_rag_chain()` from 003:* it returns one free-text answer for the whole
  query, not a reason per sector id, and its retriever drops the scores the endpoint must
  return. Its pieces still apply: `get_chat_model()`, `get_vector_store()`, and the
  prompt-template pattern and grounding wording.
- *One LCEL chain doing retrieval and reasons together* (`RunnableParallel` /
  `.assign`): it fits in fewer lines, but the two failures need different policies:
  Voyage fails → 503, Claude fails → `reason: null`. Inside one `.invoke()` both
  arrive as the same exception. Plain Python in a service keeps the two error paths
  visible and testable.
- *`store.similarity_search_with_score(query, k)` in one call:* it embeds and queries
  inside one method, so a database error would also be reported as "Couldn't reach the
  embedding service". Instead: `store.embeddings.embed_query(query)` (Voyage only, inside
  `try`), then `store.similarity_search_with_score_by_vector(vec, k=limit)`. That's the
  same pattern as playground step 6.3.
- *`with_structured_output` with its default `method="function_calling"`:* this forces a
  tool call, which the installed version can't do while adaptive thinking is on, and
  thinking is on by default for Sonnet 5 (`LLM_MODEL = "claude-sonnet-5"`). Then it only
  warns and raises `OutputParserException` when Claude doesn't call the tool
  (`langchain_anthropic/chat_models.py:2630-2659`, `:2911-2915`, `:1488-1489`).
  `method="json_schema"` sends `output_config.format` (`:2999-3012`), the same API feature
  Stage 3's `client.messages.parse(output_format=MatchReasons)` uses. So we keep parity
  and avoid the warning.
- *`PydanticOutputParser` plus format instructions in the prompt:* the model is only
  asked to follow the schema, not forced to. That's weaker than the API-enforced schema
  Stage 3 already has.

## Ticket check
- `/search/natural` at `routers/search.py:53` and `/search/similar` at `:111`, the 8 tests in
  `tests/test_similar_api.py` patching `embed_query` / `explain_matches` on
  `app.routers.search`: all correct.
- `similarity_search_with_score` returns `(Document, distance)`: correct (installed
  `langchain_postgres` 0.0.18, `vectorstores.py:974-995`, `:1059-1072`).
- **AC 2 holds by construction, verified in the installed code:** the default distance strategy
  is `COSINE` (`vectorstores.py:63`, `:382`), and `get_vector_store()` doesn't override
  it. COSINE maps to `EmbeddingStore.embedding.cosine_distance` (`:1024-1025`), the same
  pgvector `<=>` operator as Stage 3's `Sector.embedding.cosine_distance`. The query side
  uses `input_type="query"` in both (`langchain_voyageai/embeddings.py:96-102` vs.
  `services/embedding.py:15`). The documents are `build_text(sector)`, the exact Stage 3
  text (`rag/loader.py:23`). Increment 1 writes `distance_strategy=COSINE` out explicitly
  and tests it, so a later change can't silently break the ranking.
- **Not in the ticket, important:** `PGVector(...)` is not a cheap object. Its
  constructor creates its own SQLAlchemy engine from `settings.database_url` and right
  away runs `CREATE EXTENSION IF NOT EXISTS vector`, `create_all` for the
  `langchain_pg_*` tables and "create collection if missing" (`vectorstores.py:432-478`,
  `:503-520`). Two consequences:
  1. It must be built **once per process**, not per request (otherwise every request
     runs DDL and leaks a new connection pool). Increment 1 caches `get_vector_store()`.
  2. In tests it would connect to the **dev database** (`cragmatch`), not
     `cragmatch_test`. So "the test DB has no `langchain_pg_*` tables" understates the
     problem: tests must never construct the real store. They patch the service's
     `get_vector_store`.
- Same thing for the model: building a `ChatAnthropic` per request creates a new
  Anthropic HTTP client each time. Stage 3 uses one module-level `client`. The reasons
  chain is cached the same way (`get_reasons_chain()`).
- AC 5 says "mocked where the router uses them". With the logic in a service (CLAUDE.md),
  the seams are `app.services.similar_search.get_vector_store` and
  `app.services.similar_search.get_reasons_chain`. It's the same patch-where-used rule, one
  module further in.
- `services/explain.py` is used only by the router and has no tests of its own. After
  increment 2 it's dead code. **Delete it** (the user's delete decision; it's in git
  history). `MatchReason` / `MatchReasons` and the prompt wording move to `app/rag/reasons.py`.
- `services/embedding.py::embed_query()` also loses its only caller. **Keep it**. The module
  stays anyway (`EMBED_MODEL` and the `voyage` client are used by `rag/vectorstore.py` and
  `embed_sectors.py`), `embed_query` is the query half of the Stage 3 embedding path the
  user wants kept for comparison until Stage 6 ends, and CLAUDE.md lists it under "Reuse".
  Remove it together with `sectors.embedding` / `embed_sectors.py` at the end of Stage 6.
- `explain_matches()` logs token usage (`log_usage("explain", ...)`). With
  `with_structured_output` (without `include_raw`) the usage isn't returned, and
  `log_usage()` only reads Anthropic SDK responses. Building a LangChain-aware usage log
  is ticket 005's job (its AC 5 and notes). **This ticket drops the "explain" usage log
  line for now.** 005 should also apply its usage logging to the reasons chain.
- README "Running locally" doesn't list `index_sectors_langchain`. After this ticket,
  `/search/similar` reads only the LangChain collection, so a fresh database needs that
  script. Increment 2 adds it.
- Baseline: `uv run pytest -q` → **102 passed** (checked while writing this plan).

## Before you start (every increment)
- **No concurrent pytest.** Two pytest runs on `cragmatch_test` deadlock (the Stop hook
  can be running the suite while you are). Before each `uv run pytest`, check that none
  is running:
  `wmic process where "name='python.exe'" get ProcessId,CommandLine | grep -i pytest`
  must print nothing. If it prints a line, wait and check again. Never stop it yourself.
- No new dependencies: `langchain-postgres`, `langchain-anthropic`, `langchain-voyageai`
  are installed. Don't run `uv add` / `uv sync`.
- Tests never touch the network or the dev DB: Voyage, Claude and PGVector are always
  fakes.

## Increments

### 1. The reasons chain and a cached cosine vector store (app/rag only, no API change)
**Files:**
- `backend/app/rag/vectorstore.py`:
  - Decorate `get_vector_store()` with `functools.lru_cache(maxsize=1)`. Why-comment: the
    constructor opens its own engine and runs DDL, so build it once per process.
  - Pass `distance_strategy=DistanceStrategy.COSINE` (import from
    `langchain_postgres.vectorstores`). Why-comment: the default, written out because the
    ranking must match Stage 3's `<=>` (same style as `max_retries=2` in `services/llm.py`).
  - Effect on the scripts (`index_sectors_langchain.py`, `rag_playground.py`): none. They
    call it once or a few times per process.
- `backend/app/rag/reasons.py` (new):
  - `MatchReason(sector_id: int, reason: str = Field(description="One short sentence explaining the match."))`
    and `MatchReasons(reasons: list[MatchReason])`, moved verbatim from `services/explain.py`
    (keep its why-comment: they're Claude's answer format, not API schemas, so they don't
    go in `schemas/`). For this increment `explain.py` keeps its own copy. Increment 2
    deletes it.
  - `REASONS_PROMPT = ChatPromptTemplate.from_messages([("system", <EXPLAIN_PROMPT text verbatim>), ("human", "Search: {query}\n\nSectors:\n{sectors}")])`.
    The human message has the same layout as Stage 3's `user_message`.
  - `format_sectors(docs: list[Document]) -> str`: one line per doc,
    `f"id={doc.metadata['sector_id']} | {doc.page_content}"`, joined with `"\n"`, in the
    given order. Why-comment: the id is how Claude's answer is matched back to a sector
    (`format_docs` from `chain.py` has no ids, so it can't be reused here).
  - `build_reasons_chain(llm: BaseChatModel) -> Runnable`: returns
    `REASONS_PROMPT | llm.with_structured_output(MatchReasons, method="json_schema")`.
    Why-comment: json_schema is the same API feature as Stage 3's `output_format`, and
    forced tool calls don't work with Sonnet 5's default thinking. Input:
    `{"query": str, "sectors": str}`, output: a `MatchReasons` instance.
  - `get_reasons_chain() -> Runnable`: `lru_cache(maxsize=1)`, returns
    `build_reasons_chain(get_chat_model())`. Why-comment: one Anthropic client per
    process, like `services/llm.py`. Note: `lru_cache` doesn't cache exceptions, so a
    failed build is retried on the next call.
- `README.md`: under `rag/`, add `reasons.py  Per-sector match reasons: prompt, MatchReasons, build_reasons_chain(), get_reasons_chain().`
  and extend the `vectorstore.py` line with "built once per process, cosine distance".
- **Leave alone:** `services/explain.py`, `routers/`, `rag/chain.py`, `rag/llm.py`, all tests
  except the ones listed below.

**Reuses:** `get_chat_model()` (`rag/llm.py`), `get_embeddings()` / `COLLECTION`
(`rag/vectorstore.py`), `EXPLAIN_PROMPT` wording and `MatchReason(s)` (`services/explain.py`,
moved), the `ChatPromptTemplate.from_messages` pattern of `RAG_PROMPT`, the fakes style of
`tests/test_rag_chain.py` (`RunnableLambda`, no DB fixtures).

**Tests:**
- `tests/test_rag_chain.py` (extend; update the module docstring to "app/rag chain tests").
  No DB fixtures, no network:
  - `test_format_sectors_prefixes_each_doc_with_its_sector_id`: two Documents with
    `sector_id` 1 and 2 give exactly `"id=1 | first text\nid=2 | second text"`. (AC 1:
    reasons can be mapped back to sectors)
  - `test_reasons_chain_fills_prompt_and_asks_for_json_schema`: a small fake model class
    whose `with_structured_output(schema, **kwargs)` records `schema` and `kwargs` and
    returns a `RunnableLambda` that records the `ChatPromptValue` and returns
    `MatchReasons(reasons=[MatchReason(sector_id=1, reason="Short approach.")])`. Asserts:
    `build_reasons_chain(fake).invoke({"query": "short approach", "sectors": "id=1 | first text"})`
    returns that `MatchReasons`; the recorded schema `is MatchReasons`; `kwargs["method"] == "json_schema"`;
    the system message contains `"Use ONLY the details given"`; the human message
    `== "Search: short approach\n\nSectors:\nid=1 | first text"`. (AC 1, AC 3 groundwork)
  - `test_get_reasons_chain_is_built_once`: monkeypatch `app.rag.reasons.get_chat_model`
    with a counting factory that returns the fake model. Call `get_reasons_chain.cache_clear()`
    before and after (in a fixture with `yield`, so a fake never stays cached for later
    tests). Two calls return the same object, and the factory ran once.
- `tests/test_rag_vectorstore.py` (new):
  - `test_vector_store_is_cosine_and_built_once`: monkeypatch `app.rag.vectorstore.PGVector`
    with a fake class that records its kwargs, and `app.rag.vectorstore.get_embeddings`
    with `lambda: "fake-embeddings"`. Same `cache_clear()` fixture. Two calls return the
    same object and the fake was constructed once, with `distance_strategy == DistanceStrategy.COSINE`,
    `collection_name == "sectors"`, `embedding_length == 1024`. (AC 2)
- Expected suite after this increment: **106 passed**.

**Check by hand:** `uv run pytest -q` and `uv run ruff check .` green (after the
no-concurrent-pytest check). Optional, 1 Claude call and no Voyage, run by the user:
`uv run python -c "from langchain_core.documents import Document; from app.rag.reasons import get_reasons_chain, format_sectors; docs = [Document(page_content='Poble at Siurana. Approach: 5 minutes from the car, good for beginners.', metadata={'sector_id': 1})]; print(get_reasons_chain().invoke({'query': 'short approach for beginners', 'sectors': format_sectors(docs)}))"`
→ prints `reasons=[MatchReason(sector_id=1, reason='...')]`, with no warning about forced
tool calling.

**Commit:** `Stage 6.5b part 1: per-sector reasons chain in app/rag (LangChain structured output via json_schema) and a cached PGVector store with explicit cosine distance, with unit tests`

### 2. /search/similar on LangChain, Stage 3 explain code removed
**Files:**
- `backend/app/services/similar_search.py` (new). Module docstring in the style of
  `group_search.py`: glue between the LangChain pieces in `app/rag` and the database.
  - `class EmbeddingUnavailableError(Exception)`: Voyage couldn't embed the query, so
    there is no search at all.
  - `find_similar_sectors(db: Session, query: str, limit: int) -> SimilarSearchResponse`:
    1. `store = get_vector_store()`.
    2. `try: query_vec = store.embeddings.embed_query(query)`. On any `Exception`:
       `raise EmbeddingUnavailableError from exc`. Only this call sits in the `try`, so a
       DB error stays a 500, as today.
    3. `scored = store.similarity_search_with_score_by_vector(query_vec, k=limit)`.
    4. `ranked = _attach_sectors(db, scored)`: a small helper that loads the sectors in
       **one** query, `db.query(Sector).options(joinedload(Sector.crag)).filter(Sector.id.in_(ids)).all()`
       (same `db.query` style as the rest of the services), puts them in a dict by id, then
       walks `scored` **in the store's order** and returns `list[tuple[Sector, Document, float]]`.
       Documents whose `sector_id` isn't in the dict (sector deleted since indexing) are
       skipped with `logger.warning(...)` naming the id and suggesting re-running
       `index_sectors_langchain`. No 500, as with Stage 3's `embedding IS NOT NULL` filter.
    5. `reasons = _explain(query, [doc for _, doc, _ in ranked])`: returns `{}` without
       calling anything when the list is empty. Otherwise, inside one
       `try / except Exception` (the build too, so a missing key or bad config also gives
       `reason: null`):
       `get_reasons_chain().invoke({"query": query, "sectors": format_sectors(docs)})`, then
       `{r.sector_id: r.reason for r in answer.reasons}`. On an exception:
       `logger.exception("reasons chain failed; returning results without reasons")` and `{}`.
    6. Return `SimilarSearchResponse(results=[SimilarMatch(sector=s, similarity=1 - distance, reason=reasons.get(s.id)) ...])`
       in ranked order.
  - Import `get_vector_store`, `get_reasons_chain`, `format_sectors` **by name**, so tests
    can patch them on this module.
- `backend/app/routers/search.py`:
  - `search_similar` body becomes: `try: return find_similar_sectors(db, body.query, body.limit)`,
    `except EmbeddingUnavailableError:` → `logger.exception("Failed to embed query")` and
    `HTTPException(503, "Couldn't reach the embedding service, try again later.")`
    (exact current text). Keep `@limiter.limit("10/minute")`, `request: Request`,
    `body`, `response_model=SimilarSearchResponse`, `summary`.
  - Update `description`: the query is embedded with Voyage and ranked by cosine
    similarity in the LangChain PGVector store, and a LangChain chain asks Claude for a
    reason per sector.
  - Remove the now-unused imports: `embed_query`, `explain_matches`, `joinedload`,
    `Sector`, `SimilarMatch`. Keep `ClimbingStyle` (used by `/natural`). `/search/natural` is
    otherwise untouched.
- `backend/app/services/explain.py`: **delete**.
- `backend/app/rag/chain.py`: line 6 comment now points to `REASONS_PROMPT in rag/reasons.py`
  instead of the deleted `EXPLAIN_PROMPT in services/explain.py`. Comment only.
- `backend/tests/test_similar_api.py`: rewritten around the new seams (below). Drop `DIM`,
  `_unit` and the direct `Sector.embedding` writes. `_make_sector(client, name) -> int` creates
  crag and sector through the API as today. Update the module docstring: the endpoint's
  external calls now come through `get_vector_store()` (Voyage + PGVector) and
  `get_reasons_chain()` (Claude), both patched on `app.services.similar_search`. Explain
  why: the real store would connect to the dev DB and Voyage.
- `README.md`:
  - `services/`: remove the `explain.py` line, add
    `similar_search.py  /search/similar logic: PGVector scores, sectors in rank order, reasons chain.`
  - `routers/search.py` line: `/search/similar (LangChain PGVector + reasons chain)`.
  - "Running locally": after `embed_sectors`, add
    `uv run python -m app.scripts.index_sectors_langchain   # LangChain PGVector index, used by /search/similar`.
    The comment notes that it needs the approach notes from `embed_sectors` and makes 1 Voyage request.
- **Leave alone:** `services/embedding.py` (incl. `embed_query`), `scripts/embed_sectors.py`,
  `models/sector.py` (`embedding` column), `schemas/search.py`, `/search/natural`,
  `rag/chain.py` code, the frontend. No migration.

**Reuses:** `get_vector_store()` (`rag/vectorstore.py`), `get_reasons_chain()` /
`format_sectors()` (increment 1), `get_db`, `limiter`, `SimilarSearchResponse` /
`SimilarMatch` / `SectorRead` (`schemas/search.py`), the `joinedload(Sector.crag)` pattern
from the old route and `rag/loader.py`, the service-returns-response-schema pattern of
`services/group_search.py::search_for_group()`, and the error-to-HTTPException mapping
pattern of the router.

**Tests:** `tests/test_similar_api.py`. An **autouse** fixture installs both fakes for every
test (so a new test can't reach Voyage, Claude or the dev DB) and returns them so tests can
configure them:
- a fake store: `.embeddings.embed_query(text)` returns a dummy vector, or raises when
  told to. `similarity_search_with_score_by_vector(embedding, k)` records `k` and returns
  its configured `(Document, distance)` list cut to `k`. It records every call.
- a fake reasons chain: `.invoke(inputs)` records `inputs` and returns its configured
  `MatchReasons` (default: empty `reasons`), or raises when told to.
- `monkeypatch.setattr(similar_search, "get_vector_store", lambda: store)` and
  `monkeypatch.setattr(similar_search, "get_reasons_chain", lambda: chain)`.
- A helper `_doc(sector_id, name)` builds `Document(page_content=f"{name} text", metadata={"sector_id": sector_id, "name": name})`.

Tests (10; was 8):
- `test_similar_keeps_the_store_ranking_order`: create A then B (A has the lower id). The
  store returns `[(doc B, 0.1), (doc A, 0.4)]`. The response names are `["B", "A"]` (not id
  order), the similarities are `pytest.approx(0.9)` and `pytest.approx(0.6)`, and
  `"embedding" not in results[0]["sector"]`. (AC 1, AC 2)
- `test_similar_skips_documents_whose_sector_is_gone`: the store returns A and a doc with
  `sector_id=999999`. Only A comes back with 200, and the reasons chain's `inputs["sectors"]`
  doesn't contain `"id=999999"`. (AC 1)
- `test_similar_passes_limit_to_the_store`: 3 docs configured, `limit: 2`. The store
  received `k == 2` and the response has 2 results. (AC 1)
- `test_similar_returns_503_when_embedding_fails`: `embed_query` raises. Status 503,
  `detail == "Couldn't reach the embedding service, try again later."`, the store search was
  never called, and the reasons chain was never invoked. (AC 4)
- `test_similar_attaches_reason_to_each_result`: A and B in the store, the chain returns
  reasons for both ids, and each result gets its own reason. The chain received
  `inputs["query"] == "x"` and `inputs["sectors"]` contains `f"id={a_id} | A text"` and
  `f"id={b_id} | B text"`. (AC 1)
- `test_similar_reason_is_none_for_sector_claude_skipped`: the chain returns a reason for A
  only. Result: `{"A": "only this one", "B": None}`. (AC 1, AC 3)
- `test_similar_still_returns_results_when_reasons_chain_fails`: `chain.invoke` raises
  `RuntimeError`. Status 200, the same results, `reason is None`. (AC 3)
- `test_similar_still_returns_results_when_reasons_chain_cannot_be_built`: patch
  `get_reasons_chain` with a function that raises. Status 200, `reason is None`. (AC 3)
- `test_similar_with_no_matches_returns_empty_and_skips_claude`: the store returns `[]`.
  Status 200, `results == []`, and the chain was never invoked ("no result" is a normal
  answer).
- `test_similar_is_rate_limited`: unchanged logic (limiter on, `limiter.reset()`, 11 calls),
  now running against the autouse fakes. Exactly `[200] * 10 + [429]`. (AC 6)
- Expected suite after this increment: **108 passed** (106 − 8 + 10).
- After the change, `git grep -n -E "explain_matches|services.explain|services import explain" -- backend`
  returns nothing (AC 5, no dead seams left).

**Check by hand** (the user, with the DB up, the dev server running and the `sectors`
collection indexed; on a fresh DB run `index_sectors_langchain` first). This uses
2 Voyage requests and 1 Claude call, so don't repeat it within a minute:
1. `uv run python -m app.scripts.rag_playground 6.3`: note the "Stage 3 raw pgvector" list
   for `quiet crag, short approach` (k=5).
2. In `/docs`, `POST /search/similar` with `{"query": "quiet crag, short approach", "limit": 5}`:
   the same 5 names in the same order, and similarities equal to 3 decimals (AC 2). Every
   `reason` is a sentence, not `null` (if all are null, the server log has the reasons
   chain's traceback). The response shape is unchanged (AC 1).
3. Frontend "describe the vibe" search: the cards still show similarity and reason.
4. Developer: `uv run pytest -q` (after the no-concurrent-pytest check) and `uv run ruff check .` green.

**Commit:** `Stage 6.5b part 2: /search/similar runs on LangChain (PGVector scores plus the per-sector reasons chain) through a new similar_search service; delete the Stage 3 explain service and rewrite the similar API tests around the new seams`

## Walk-through: one request to /search/similar, Stage 3 vs. now
Example: `POST /search/similar {"query": "quiet crag, short approach", "limit": 5}`.

**Stage 3 (before this ticket), all in the router:**
1. slowapi checks the 10/minute limit. FastAPI validates `body` (`SimilarSearchRequest`).
2. `embed_query(query)` calls the Voyage SDK (`input_type="query"`) → `list[float]` (1024 numbers).
3. One SQL query on **our** `sectors` table: `ORDER BY sectors.embedding <=> :vec LIMIT 5`,
   with `joinedload(crag)` → `(Sector, distance)` rows. The vectors live in the
   `sectors.embedding` column, written by `embed_sectors.py`.
4. `explain_matches(query, sectors)` builds one line per sector from the DB columns, calls
   `client.messages.parse(output_format=MatchReasons)`, logs usage → `{sector_id: reason}`.
5. The router builds `SimilarMatch(sector, similarity=1 - distance, reason)` for each row.

**Now:**
1. Same rate limit and validation. The router calls
   `find_similar_sectors(db, query, 5)` and only translates `EmbeddingUnavailableError` → 503.
2. **The vector store.** `get_vector_store()` returns the one cached `PGVector` object. It
   holds a `VoyageAIEmbeddings` (same model, `voyage-3.5`) and its own connection to the
   same Postgres.
3. **Embed.** `store.embeddings.embed_query(query)` → Voyage with `input_type="query"` →
   the same vector Stage 3 got. If this fails, the service raises
   `EmbeddingUnavailableError` and the router answers 503 with the same message as before.
4. **Search with scores.** `store.similarity_search_with_score_by_vector(vec, k=5)` runs
   the same `<=>` cosine operator, but on LangChain's tables (`langchain_pg_embedding`,
   filtered to the `sectors` collection), written by `index_sectors_langchain.py`. It
   returns `[(Document, distance), ...]`, closest first. A `Document` has
   `page_content` (the `build_text()` string, the same text Stage 3 embedded) and
   `metadata` (`sector_id`, `name`, `crag`, ...). We call the store directly instead of a
   retriever because a retriever throws the distances away (step 6.4).
5. **Back to our models.** The response needs real `Sector` rows (with `crag`) for
   `SectorRead`, so one `WHERE id IN (...)` query loads them all. Then we walk the
   store's list **in its order** (SQL `IN` doesn't keep order), dropping ids that no longer
   exist.
6. **Reasons, the LangChain way.** `format_sectors(docs)` turns the documents into
   `id=3 | Poble at ...` lines. Then the cached reasons chain runs:
   - `REASONS_PROMPT` fills `{query}` and `{sectors}` → a system message (the Stage 3
     grounding rules) and a human message (`Search: ...\n\nSectors:\n...`).
   - `llm.with_structured_output(MatchReasons, method="json_schema")` sends those messages
     to Claude together with the `MatchReasons` JSON schema (the same API feature as
     Stage 3's `output_format`). It then parses Claude's JSON into a `MatchReasons`
     object, so there's no `StrOutputParser` here.
   - The service turns it into `{sector_id: reason}`. Any exception → `{}` → every
     `reason` is `null`, and the results still come back.
   Claude now reads the **retrieved text** (the same text that was embedded) instead of
   DB columns. That's the "augmented" part of RAG: the model explains from what the
   search actually matched.
7. Same `SimilarMatch(sector, similarity=1 - distance, reason)` list, so the frontend
   doesn't change.

**What changed, in one line each:** where the vectors live (our column → LangChain's
collection), who talks to Voyage (our SDK wrapper → `VoyageAIEmbeddings`), and how Claude
is called (`client.messages.parse` → prompt template `|` structured-output model). What
didn't change: the cosine math, the text that's embedded, the response, the error
behaviour, the rate limit.
**Why not `build_rag_chain()` from 003:** that chain answers the whole question in one
paragraph. Here every sector needs its own reason, keyed by id, plus a score. So the
retrieval step runs outside the chain (to keep the scores), and the chain's output is a
structured object instead of a string. Ticket 005 builds on this: it compares
`with_structured_output` with Stage 3's `messages.parse` side by side for
`/search/natural`, and brings token usage logging back.

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Increment 2: `test_similar_keeps_the_store_ranking_order`, `test_similar_attaches_reason_to_each_result`, `test_similar_reason_is_none_for_sector_claude_skipped`, `test_similar_passes_limit_to_the_store`, `test_similar_skips_documents_whose_sector_is_gone`; increment 1: `test_format_sectors_prefixes_each_doc_with_its_sector_id`, `test_reasons_chain_fills_prompt_and_asks_for_json_schema`; manual step 2 |
| 2 | Increment 1 `tests/test_rag_vectorstore.py::test_vector_store_is_cosine_and_built_once` (same distance operator); increment 2 `test_similar_keeps_the_store_ranking_order` (store order survives the DB load); manual comparison with playground 6.3 (real data) |
| 3 | Increment 2 `test_similar_still_returns_results_when_reasons_chain_fails`, `test_similar_still_returns_results_when_reasons_chain_cannot_be_built`, `test_similar_reason_is_none_for_sector_claude_skipped` |
| 4 | Increment 2 `test_similar_returns_503_when_embedding_fails` (status and exact message) |
| 5 | The autouse fixture in `tests/test_similar_api.py` patches both seams for every test; `test_rag_chain.py` / `test_rag_vectorstore.py` patch `get_chat_model` / `PGVector`; reviewer checks no test constructs a real store or model |
| 6 | Increment 2 `test_similar_is_rate_limited` |

All criteria are covered. AC 2 on real data can only be confirmed by hand; the tests cover
the two code paths it depends on (cosine operator, order preserved).

## Risks
- **Concurrent pytest deadlocks** on `cragmatch_test`: run the process check from "Before
  you start" before every run. Never stop another pytest process.
- **Tests reaching the dev DB or Voyage:** the real `get_vector_store()` connects to
  `settings.database_url` (dev DB) and Voyage. Mitigation: the autouse fixture, and the
  `cache_clear()` fixtures in the rag tests so a fake never stays cached across tests.
- **Cached objects and threads:** FastAPI runs sync endpoints in a thread pool. PGVector
  uses a `scoped_session` (one per thread) over a shared engine, and the Anthropic client
  is thread-safe, so one cached instance of each is fine. PGVector's engine is a second
  connection pool to the same database (default size 5). That's fine at this scale.
- **First request after startup** builds the store: one round of `CREATE EXTENSION IF NOT EXISTS`
  / `create_all` / collection check on the dev DB. These are no-ops when the tables exist
  (they do since 6.2).
- **Fresh or stale index:** `/search/similar` now reads only the LangChain collection. On a
  fresh DB, results are `[]` until `index_sectors_langchain` runs (README update).
  Sectors added or edited after indexing are missing or out of date, the same as with
  `embed_sectors` in Stage 3. Deleted sectors are skipped with a warning.
- **Structured output on the real model:** the tests fake the structured-output call, so
  only the manual check proves `json_schema` parsing works with `claude-sonnet-5` and its
  default thinking. If every reason is `null` by hand, read the server log. AC 3 is
  designed to hide such failures from the user.
- **Usage logging gap:** the reasons call no longer logs tokens until ticket 005 adds a
  LangChain-aware logger. Accepted for this ticket (see Ticket check).
- **Similarity range:** `1 - cosine distance` is in [-1, 1] in theory. With real Voyage
  vectors it's in (0, 1), and the formula is unchanged from Stage 3, so no clamping.
- **Voyage 3 requests/minute** in the manual checks: increment 2 uses 2 requests (playground
  6.3 + one endpoint call). Don't repeat within a minute, and don't hammer the endpoint
  by hand to test the rate limit (the test covers it).
- **Behaviour that must stay unchanged:** `/search/natural`, the 503 message, the
  10/minute limit, the response schema, the frontend, `sectors.embedding`,
  `embed_sectors.py`, playground steps 6.2-6.5 and the `index_sectors_langchain` script.
- **No migration, no dependency change.** Nothing to downgrade.

## Out of scope (copied from the ticket)
- `/search/natural` parsing: that's ticket 005.
- Deleting `sectors.embedding` or `embed_sectors.py`: keep the Stage 3 path's data until
  Stage 6 is finished, so the two can still be compared.
- Frontend changes: the response shape doesn't change.
