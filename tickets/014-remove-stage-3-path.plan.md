# Plan for 014: Remove the Stage 3 path, keep only LangChain

**Ticket:** `tickets/014-remove-stage-3-path.md`
**Approach:** Delete everything that only Stage 3 or the comparison uses: playground steps
6.3 and 6.6 and their helpers, the Anthropic SDK `client` and `log_usage()`, the `voyage`
client and `embed_query()`, the Voyage half of `embed_sectors.py`, and the
`Sector.embedding` column. A hand-written migration drops the column, and its downgrade
adds it back empty. `LLM_MODEL`, `log_tokens()` and `EMBED_MODEL` stay where they are.
`build_text()` moves next to its only caller in `rag/loader.py`, and the approach notes
stay in a renamed notes-only script, `scripts/seed_notes.py`, which runs in the same
place in the seed order.

**Alternatives considered:**
- *Put the notes into `seed.py`'s `CRAGS` data (as was done for `approach_minutes`)
  and drop the extra seed step:* that means a bigger diff (13 sector dicts edited), and
  `seed.py` would change behaviour for no gain. Today's `NOTES.get(name)` loop moves
  unchanged into `seed_notes.py`, which is the smaller change.
- *Keep `build_text()` in the script:* then `app/rag/loader.py` (app code) keeps
  importing from `app/scripts/` (scripts you run by hand), which is the wrong direction.
  The loader is the only caller, and the text is the loader's Document format, so the
  function moves there.
- *Move `LLM_MODEL` / `log_tokens()` into `app/rag/llm.py` and `EMBED_MODEL` into
  `app/rag/vectorstore.py`, then delete both service modules:* this changes the logger
  name that 4 tests assert (`caplog.set_level(..., logger="app.services.llm")`), changes
  the import in `test_rag_chain.py`, and adds edits to README and CLAUDE.md. Nothing
  forces it, so keep the smaller change. Each module keeps a small, accurate job: the
  model name (plus the token log line) and the embedding model name.
- *`alembic revision --autogenerate` for the migration:* autogenerate reads the dev
  database, and the developer must not touch the dev DB. The diff is just two
  operations, so the developer uses a plain `alembic revision`, which doesn't connect
  (`revision_environment` is off in `alembic.ini`), and writes them by hand. The user then
  runs `uv run alembic check` after upgrading. It does the same comparison autogenerate
  would, through `env.py`'s `include_object` filter, so it confirms there is no leftover
  drift.

**Choices on the ticket's open questions:**
- Notes and `build_text()`: `build_text()` goes to `app/rag/loader.py`, unchanged.
  `NOTES` and the loop that fills `approach_notes` go to `app/scripts/seed_notes.py`
  (renamed from `embed_sectors.py`). The README seed order stays seed, then
  `seed_notes`, then `index_sectors_langchain`.
- Downgrade: it adds `sectors.embedding` back as `Vector(1024)`, nullable and empty.
  The migration docstring says so and explains why. It never touches the `vector`
  extension (`178caab75ad8` created it and LangChain's tables need it) or
  `approach_notes`.
- Playground numbering: keep 6.2, 6.4, 6.5 and leave the gaps. The module docstring
  says 6.3 and 6.6 were comparisons, removed in ticket 014. The plans for tickets
  003-005 stay readable that way.

## Ticket check
- Correct: every file, line and name in "What exists today" matches the code (checked
  2026-10-09). `embed_query()` and `voyage` in `services/embedding.py` have no caller
  outside `embed_sectors.py`. `/search/similar` calls `store.embeddings.embed_query`
  (`services/similar_search.py:70`). `build_text` is imported only by `rag/loader.py`.
  No test covers step 6.3. `178caab75ad8` runs `CREATE EXTENSION IF NOT EXISTS vector`,
  and its downgrade drops `embedding` and `approach_notes` but not the extension.
- Incomplete: playground step 6.3 is also the only user of `get_embeddings`, and step 6.6
  is the only user of `get_parse_chain`. Both imports become unused and must go, or
  ruff fails. The playground docstring already leaves out 6.3. Once the 6.6 tests are
  gone, `test_rag_chain.py` no longer uses `SimpleNamespace` or `OutputParserException`.
- Incomplete: CLAUDE.md also mentions the removed code in "Stack" ("Claude via the
  Anthropic SDK (`app/services/llm.py`)") and in "Commands" ("`embed_sectors` hits
  Voyage's 3 req/min limit"), not only in "Reuse before writing" and "Traps".
  `README.md:109` ("ChatAnthropic with the Stage 3 settings") and `:113` ("Stage 3
  prompt") describe current files in terms of the removed path.
- Incomplete: "Stage 3" comments also appear in `rag/query_parsing.py`, `rag/reasons.py`,
  `services/natural_search.py`, `services/overpass.py` and `tests/test_natural_api.py`.
  These are history comments that explain *why* the current code is the way it is. None
  of them names removed code, so they stay (the reviewer shouldn't ask for them).
  Only the comments that point at removed code change: `rag/loader.py:21-22`,
  `rag/vectorstore.py:14,28`, `rag/llm.py:12`, `scripts/seed_stays.py:8`.
- AC 9 ("given an empty database") can't be fully checked by hand without wiping the
  dev DB. A test and an idempotent re-run on the dev DB cover it instead (see coverage).
- AC 5 says "none remain in code, tests or docs". That excludes `tickets/`: the old
  tickets and plans are history and stay as they are. The new migration has to name
  `embedding`.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. One AI path: LangChain only, no Stage 3 code, column or docs

**Before running any test (developer):**
- Never run two pytest processes against `cragmatch_test`: they deadlock. Before each
  run, check for one already running (`wmic` isn't installed):
  `powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'python.exe','uv.exe' -and $_.CommandLine -like '*pytest*' } | Select-Object ProcessId, CommandLine"`
  If a line shows up, wait for it to finish. Never kill it. If it looks stuck, report its
  PID to the user.
- Run pytest in the foreground only (never `run_in_background`). The finish hook runs
  the backend tests again, and a leftover background run would collide with it.
- Don't touch the dev database at all: no `alembic upgrade/downgrade/check`, no
  autogenerate, no seed or index scripts. The tests use `create_all()`, so they pass
  without the migration. The user runs the migration by hand (Check by hand).
- Don't touch anything in `tickets/` (another task is editing 007-012) or `.claude/`.

**Files** (in build order: migration, backend, docs; no frontend change):

Migration and model
- `backend/alembic/versions/<rev>_drop_embedding_from_sectors.py` (new): create with
  `uv run alembic revision -m "drop embedding from sectors"` (no `--autogenerate`; this
  doesn't connect to any DB). Check that `down_revision = '56e0971d2083'` (the current
  head). Then fill in:
  - docstring under the title: this is Stage 3's copy of the sector vectors; LangChain
    keeps its own copy in `langchain_pg_embedding`, which this migration doesn't touch;
    the downgrade brings the column back *empty*, because nothing writes these vectors
    any more; the `vector` extension stays because LangChain's tables need it.
  - `upgrade()`: `op.drop_column("sectors", "embedding")`. Nothing else: no extension
    drop, no `approach_notes`, no other table.
  - `downgrade()`: `op.add_column("sectors", sa.Column("embedding", Vector(dim=1024),
    nullable=True))` with `from pgvector.sqlalchemy import Vector` (a library import,
    as in `178caab75ad8`; migrations must not import app code). Because of this, a
    further downgrade past `178caab75ad8` still finds the column it drops.
- `backend/app/models/sector.py`: delete the `embedding` line and the
  `from pgvector.sqlalchemy import Vector` import. `approach_notes` and
  `approach_minutes` stay as they are.

Services
- `backend/app/services/llm.py`: delete `import anthropic`, the `settings` import, the
  `client` and `log_usage()`. Keep `logger = logging.getLogger(__name__)` (the logger
  name `app.services.llm` is part of the log format that tests assert), `LLM_MODEL` and
  `log_tokens()` unchanged. A one-line module docstring is fine: model name and token
  log line, shared by `app/rag/`.
- `backend/app/services/embedding.py`: delete `import voyageai`, the `settings` import,
  `voyage` and `embed_query()`. Keep `EMBED_MODEL = "voyage-3.5"`, with a one-line
  docstring or comment saying that documents and queries must use the same model.

LangChain code
- `backend/app/rag/loader.py`: move `build_text()` here from `embed_sectors.py`,
  character for character (same f-string, same `Sector` type hint). Remove
  `from app.scripts.embed_sectors import build_text`. Rewrite the page_content comment
  to the *why*: this string is what gets embedded, so changing it means re-running
  `index_sectors_langchain`.
- `backend/app/rag/llm.py:12`: the comment "Same timeout and retries as
  services/llm.py, so both paths fail the same way" points at the removed client.
  Replace it with the reason for the values: 20 s per attempt instead of the SDK's
  600 s default, 2 retries, so a slow Claude call fails fast instead of hanging a
  request. Keep the second comment line about reading settings at call time.
- `backend/app/rag/vectorstore.py:14` and `:28`: drop "Same model as Stage 3" and
  "must match Stage 3's <=> operator". Keep the why that's still true: documents and
  queries are embedded with the same `EMBED_MODEL` (vectors from different models
  can't be compared), and cosine is written out because similar_search turns the
  distance into a score as `1 - distance`. Check that wording against
  `services/similar_search.py` before writing it.

Scripts
- `backend/app/scripts/embed_sectors.py` → `backend/app/scripts/seed_notes.py`: rename it
  (or create the new file and delete the old one). Keep the `NOTES` dict and its
  "Illustrative notes" comment unchanged. `main()` keeps today's loop
  (`s.approach_notes = NOTES.get(s.name)` for every sector, then `db.commit()`,
  `finally: db.close()`). Remove the Voyage import, the `build_text` call, the
  `voyage.embed` call, the `sector.embedding` loop and the step comments. Drop
  `joinedload(Sector.crag)`, which only `build_text` needed. Add a short module docstring
  with the run command (`uv run python -m app.scripts.seed_notes`) and the rule that it
  runs after `seed` and before `index_sectors_langchain`, because the index embeds the
  notes. No Voyage call.
- `backend/app/scripts/seed_stays.py:8`: change "like the sector notes in
  embed_sectors.py" to `seed_notes.py`.
- `backend/app/scripts/rag_playground.py`:
  - delete `step_6_3`, `parse_with_messages_api`, `run_side`, `show_value`, `step_6_6`
    and `NATURAL_QUERIES`.
  - `STEPS = {"6.2": step_6_2, "6.4": step_6_4, "6.5": step_6_5}`. The `__main__` block
    stays as it is: an unknown step (now including 6.3 and 6.6) prints the usage with
    the remaining steps and exits with code 1 (AC 3).
  - imports: remove `Callable`, `Sector`, `PARSE_SYSTEM_PROMPT`, `get_parse_chain`,
    `get_embeddings`, `ParsedFilters` and the whole `app.services.llm` import. Keep
    `SessionLocal`, `StrOutputParser`, `RecursiveCharacterTextSplitter`, `RAG_PROMPT`,
    `build_rag_chain`, `format_docs`, `get_chat_model`, `SectorLoader`,
    `get_vector_store`. Let ruff confirm.
  - docstring: remove the `6.6` run line. Add one sentence: steps 6.3 and 6.6 compared
    Stage 3 with LangChain and were removed in ticket 014; the other numbers are kept
    so they match the plans in `tickets/`.
  - steps 6.2, 6.4 and 6.5 don't change at all.

Tests
- `backend/tests/test_rag_chain.py`: delete
  `test_step_6_6_prints_both_parsers_side_by_side` and
  `test_step_6_6_keeps_comparing_when_one_side_fails`. Remove the imports they leave
  unused (`SimpleNamespace`, `OutputParserException`). `LLM_MODEL`,
  `PARSE_SYSTEM_PROMPT`, `get_parse_chain` and `rag_playground` are still used. Add the
  playground test below.
- `backend/tests/test_usage_logging.py`: delete
  `test_log_usage_reads_an_anthropic_response`, the `log_usage` import and
  `SimpleNamespace` if it becomes unused. Update the module docstring if needed. The two
  `UsageLogger` tests stay unchanged.
- `backend/tests/test_rag_loader.py` (new): the three tests below.

Docs
- `README.md`:
  - seed block (lines 22-28): `seed` (crags + sectors), then
    `uv run python -m app.scripts.seed_notes    # approach notes (no API calls)`, then
    `index_sectors_langchain` with its comment changed to "needs the approach notes
    from seed_notes; 1 Voyage request". `seed_stays` and `import_stays` stay as they are.
  - structure: `models/sector.py` drops "pgvector embedding".
    `services/llm.py` → "LLM_MODEL + log_tokens(): Claude model name and token usage log
    line, used by app/rag/". `services/embedding.py` → "EMBED_MODEL (voyage-3.5), used by
    app/rag/vectorstore.py". `rag/loader.py` → "SectorLoader + build_text(): sectors as
    LangChain Documents". `rag/llm.py` → "get_chat_model(): ChatAnthropic (timeout,
    retries); UsageLogger callback". `rag/query_parsing.py` → "parse prompt" instead of
    "Stage 3 prompt". `scripts/embed_sectors.py` entry → `seed_notes.py   Illustrative
    approach notes per sector (run before indexing).` in the same position.
    `rag_playground.py` → "Stage 6 steps 6.2, 6.4, 6.5, one function per step".
- `CLAUDE.md`:
  - Stack: "Claude through LangChain's ChatAnthropic (`app/rag/llm.py`; model name in
    `app/services/llm.py`), Voyage `voyage-3.5` embeddings, 1024 dims, through LangChain
    (`app/rag/vectorstore.py`; model name in `app/services/embedding.py`)". Keep the
    `app/rag/` sentence.
  - Commands: the fresh-DB line says `seed_notes` must run before
    `index_sectors_langchain`, which makes 1 Voyage request (instead of the
    `embed_sectors` mention).
  - Reuse before writing: replace the two lines with: Claude: `get_chat_model()` and
    `UsageLogger` in `rag/llm.py`, `LLM_MODEL` and `log_tokens()` in `services/llm.py`.
    Embeddings and vector search: `get_embeddings()` / `get_vector_store()` in
    `rag/vectorstore.py`, `EMBED_MODEL` in `services/embedding.py`. Sector text:
    `SectorLoader` / `build_text()` in `rag/loader.py`.
  - Traps: replace the `langchain_pg_*` line with: sector vectors live only in
    LangChain's tables (`langchain_pg_*`, collection `sectors`); the `sectors` table has
    no vector column. After changing the notes or `build_text()`, re-run `seed_notes` /
    `index_sectors_langchain`. Leave the `pgvector <0.4` trap and the Voyage
    rate-limit trap as they are.

**Not changed:** `pyproject.toml` / `uv.lock` (no `uv add/remove`), `conftest.py` (its
`CREATE EXTENSION IF NOT EXISTS vector` is harmless), `core/config.py`, routers, schemas,
`services/similar_search.py`, `services/natural_search.py`, `rag/chain.py`,
`rag/reasons.py`, `rag/query_parsing.py`, all frontend files.

**Reuses:** `LLM_MODEL` / `log_tokens()` (`services/llm.py`) and `EMBED_MODEL`
(`services/embedding.py`) as they are; the existing `NOTES` dict and loop; `build_text()`
moved, not rewritten; `SectorLoader`; the playground's existing unknown-step handling;
the `db_session` fixture from `conftest.py`; the migration style of `178caab75ad8`
(pgvector `Vector` in a migration).

**Tests:**
- deleted: `tests/test_rag_chain.py::test_step_6_6_prints_both_parsers_side_by_side`,
  `tests/test_rag_chain.py::test_step_6_6_keeps_comparing_when_one_side_fails`,
  `tests/test_usage_logging.py::test_log_usage_reads_an_anthropic_response` (AC 11)
- new `tests/test_rag_chain.py::test_playground_offers_only_the_langchain_steps`:
  `list(rag_playground.STEPS) == ["6.2", "6.4", "6.5"]`. The usage message is built from
  `STEPS`, so this pins what 6.3/6.6 get told (AC 3, 4)
- new `tests/test_rag_loader.py::test_build_text_format_is_unchanged`: pure, with a
  stand-in `SimpleNamespace(name="Poble", crag=SimpleNamespace(name="Margalef",
  region="Priorat"), style=ClimbingStyle.SPORT, grade_min="5+", grade_max="7b",
  approach_notes="Easy-going crag.")`. Asserts the exact literal
  `"Poble at Margalef in Priorat. Style: sport. Grades: 5+ to 7b. Approach: Easy-going crag."`
  (AC 10)
- new `tests/test_rag_loader.py::test_sector_loader_builds_documents_from_build_text`:
  adds a `Crag` and a `Sector` with notes through `db_session`, then
  `SectorLoader(db_session).load()`. Asserts one Document whose `page_content` equals
  the same kind of exact literal, and whose metadata holds `sector_id`, `name`, `crag`,
  `style`, `grade_min`, `grade_max` (AC 10)
- new `tests/test_rag_loader.py::test_seed_notes_fills_notes_without_voyage`: adds a crag
  with two sectors through `db_session`, one named in `NOTES` (e.g. "Poble") and one not
  (e.g. "Unknown wall"). Monkeypatches `seed_notes.SessionLocal` to `lambda: db_session`
  and runs `seed_notes.main()`. Asserts the first sector's `approach_notes ==
  seed_notes.NOTES["Poble"]` and the second is `None`. No network: if the script still
  called Voyage it would fail without a key. `main()` closes the session, which is fine:
  a SQLAlchemy 2.0 session can be used again after `close()`, and the fixture teardown
  still works (AC 9)
- unchanged and still green: `tests/test_similar_api.py` (10, including the 503 on
  embedding failure and `"embedding" not in results[0]["sector"]`) (AC 1, 13),
  `tests/test_natural_api.py` (9) (AC 2), the `UsageLogger` tests in
  `tests/test_usage_logging.py`, plus `test_reasons_chain_logs_token_usage`,
  `test_parse_chain_logs_token_usage` and
  `test_chat_model_uses_llm_model_and_settings_key` in `tests/test_rag_chain.py`
  (AC 6), `test_step_6_5_prints_each_stage_and_calls_retriever_twice` (AC 3)

**Expected suite:** 127 passed (126 today − 3 deleted + 4 new). `uv run ruff check .`
clean.

**Check by hand** (the user, from `backend/`, in PowerShell; the dev server can stay
stopped until step 5):
1. Before upgrading: `uv run alembic current` shows `56e0971d2083 (head)`. Open psql
   with `docker compose exec db psql -U <your postgres user> -d cragmatch` (run from
   the repo root) and run:
   `SELECT count(*) FROM sectors WHERE embedding IS NOT NULL;` (13 on a seeded DB,
   which is the AC 13 edge case), `SELECT count(*) FROM sectors WHERE approach_notes
   IS NOT NULL;` and `SELECT count(*) FROM langchain_pg_embedding;` (13). Write the
   numbers down.
2. `uv run alembic upgrade head`: it succeeds. In psql, `\d sectors`: no `embedding`
   column; `approach_notes`, `approach_minutes` and the rest are there. The notes count
   and the `langchain_pg_embedding` count are the same as in step 1, and so is
   `SELECT count(*) FROM sectors;` (AC 7, 13).
3. `uv run alembic check` prints "No new upgrade operations detected." (the models
   and the DB agree; the reviewed migration is complete).
4. Round trip: `uv run alembic downgrade -1` succeeds. `\d sectors` shows
   `embedding | vector(1024)` again, and `SELECT count(*) FROM sectors WHERE embedding
   IS NOT NULL;` gives 0 (empty, by design). Then `uv run alembic upgrade head`
   succeeds again, and `uv run alembic current` shows the new revision as head (AC 8).
5. `uv run fastapi dev app/main.py`. In /docs (or the frontend's vibe search), send
   `POST /search/similar` with a query like "quiet crag, short approach": 200, sectors
   in rank order, each with a reason (1 Voyage + 1 Claude call). Then send
   `POST /search/natural` with "something around 6b, sport": 200 with sectors. The log
   shows `Claude reasons: N in / M out tokens` and `Claude natural_search: ...` lines
   (AC 1, 2, 6, 13).
6. Playground: `uv run python -m app.scripts.rag_playground 6.3`, then `echo
   $LASTEXITCODE`. It prints `(steps: 6.2, 6.4, 6.5)`, then `1`. Same for `6.6`. Then
   `uv run python -m app.scripts.rag_playground 6.2` runs as before (no API calls)
   (AC 3, 4).
7. Optional, the seed path on the dev DB (both scripts are safe to re-run):
   `uv run python -m app.scripts.seed_notes`, then
   `uv run python -m app.scripts.index_sectors_langchain`. The second prints "Indexed 13
   sectors into the 'sectors' collection.", after 1 Voyage request in total (AC 9).
8. Leftovers (AC 5), from the repo root:
   `git grep -n -E 'log_usage|embed_sectors|Sector\.embedding|parse_with_messages_api|run_side|show_value|NATURAL_QUERIES|anthropic\.Anthropic|voyageai\.Client|services\.embedding import .*(voyage|embed_query)|services\.llm import .*client' -- backend README.md CLAUDE.md`
   prints nothing.

**Commit:** stage only `backend/`, `README.md`, `CLAUDE.md`,
`tickets/014-remove-stage-3-path.md` and this plan. Leave out the other tickets and the
`.claude/skills` changes, which aren't part of this ticket. Message:
`Ticket 014: remove the Stage 3 path, keep only LangChain. Migration drops sectors.embedding (downgrade restores an empty column); delete the Anthropic SDK client and log_usage, the voyage client and embed_query, playground steps 6.3 and 6.6 and their tests; embed_sectors becomes seed_notes (notes only) and build_text moves to rag/loader.py with tests pinning its text; README and CLAUDE.md updated`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `tests/test_similar_api.py` (all 10, unchanged); Check by hand 5 |
| 2 | `tests/test_natural_api.py` (all 9, unchanged); Check by hand 5 |
| 3 | `tests/test_rag_chain.py::test_playground_offers_only_the_langchain_steps`, `::test_step_6_5_prints_each_stage_and_calls_retriever_twice`; Check by hand 6 (exit code 1, step 6.2 run; 6.4 isn't run by hand, its code is untouched) |
| 4 | `test_playground_offers_only_the_langchain_steps` (the comparison steps are gone); review: 6.2/6.4/6.5 untouched; Check by hand 6 |
| 5 | Check by hand 8 (git grep); ruff (no unused or broken imports); review |
| 6 | `tests/test_usage_logging.py::test_usage_logger_logs_tokens_of_a_model_call`, `tests/test_rag_chain.py::test_reasons_chain_logs_token_usage`, `::test_parse_chain_logs_token_usage`, `::test_chat_model_uses_llm_model_and_settings_key`; Check by hand 5 |
| 7 | Check by hand 1-3 |
| 8 | Check by hand 4 |
| 9 | `tests/test_rag_loader.py::test_seed_notes_fills_notes_without_voyage`; README seed block review; Check by hand 7. A real empty-DB run isn't part of the checks (it would mean wiping the dev DB), so it is only partly covered |
| 10 | `tests/test_rag_loader.py::test_build_text_format_is_unchanged`, `::test_sector_loader_builds_documents_from_build_text` |
| 11 | Expected suite 127 passed, offline (the hook and the reviewer run it) |
| 12 | Review of the README and CLAUDE.md diffs; Check by hand 8 |
| 13 | Check by hand 1, 2, 5 |

No criterion is left with no check at all. AC 9's "empty database" case is only partly
covered (see the row).

## Risks
- **The vectors in `sectors.embedding` are lost for good:** by decision. LangChain's copy
  in `langchain_pg_embedding` is untouched, and step 2 of the check confirms its count.
  The downgrade can only restore an empty column, and the migration docstring says so.
- **The migration drops more than the column:** it is hand-written with two operations.
  The reviewer checks that there is no extension drop and no `approach_notes` or
  `langchain_pg_*` change. `alembic check` (Check by hand 3) confirms there is no drift.
  `env.py`'s `include_object` only compares tables in our metadata, so neither PostGIS
  nor `langchain_pg_*` tables can show up.
- **Green tests don't prove the dev DB is current** (`create_all()`): the user runs
  the upgrade by hand. If they forget, nothing breaks: SQLAlchemy only selects mapped
  columns, so an extra nullable column in the DB is ignored. `alembic current` and
  `check` show the state.
- **The Document text silently changes and the index goes stale:** `build_text()` is
  moved character for character, and two tests pin the exact string. The text doesn't
  change, so the LangChain index needs no re-indexing.
- **`seed_notes` overwrites `approach_notes` on every sector, including sectors added
  through the API (set to `None` if not in `NOTES`):** `embed_sectors` already did this.
  Behaviour is kept, not changed in this ticket.
- **Concurrent pytest runs deadlock on `cragmatch_test`:** check with `Get-CimInstance`
  before each run, run in the foreground, and never kill by command-line text.
- **The lint hook runs on each edited file:** remove unused imports in the same edit
  (playground, both test files, both service modules, `sector.py`).
- **External services:** none in tests. Check by hand makes 1 Voyage and 2 Claude calls
  (step 5) and optionally 1 Voyage call (step 7). That's under Voyage's 3 req/min, and
  the slowapi limit allows 10/min per endpoint.
- **Parallel work:** another task is editing `tickets/007-012` plans. The developer
  touches nothing in `tickets/`, and the commit stages only this ticket's files.

## Out of scope (copied from the ticket)
- Removing `anthropic` / `voyageai` from `pyproject.toml`: the LangChain packages depend
  on them, and `uv add/remove` hits the OneDrive lock trap. (Tech lead: not done here.
  No code imports them directly any more, but removing them gains nothing, since
  they stay in `uv.lock` as transitive dependencies.)
- `ANTHROPIC_API_KEY` / `VOYAGE_API_KEY` settings: LangChain still uses both.
- Frontend: no frontend code uses the removed things (`types.ts` has no embedding field,
  and the API response already hides it, per `test_similar_api.py`).
- The `pgvector` extension and the `pgvector` Python package: `langchain-postgres` needs them.
- Changing LangChain behaviour, prompts, models or any API response.
- Migrating the data in `sectors.embedding` anywhere: LangChain has its own copy.
