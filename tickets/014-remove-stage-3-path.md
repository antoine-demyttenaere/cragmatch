# 014: Remove the Stage 3 path, keep only LangChain

**Status:** Ready
**Size:** L (needs a migration; the user wants it as ONE delivery, no increments)
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Now I would like to remove everything that wasn't part LangChain. When we did stage 3 I want to remove the things that were in the comparison between stage 3 and LangChain. In comparison I only want to keep LangChain. You can remove the code that is unnecessary, I mean the stage 3 has already been replaced by LangChain but that wouldn't break the app. I don't want the comparison anymore. I only want LangChain."

## User story
As the developer and learner of CragMatch, I want the Stage 3 code that only existed
for the Stage 3 vs LangChain comparison removed, so that the project has one AI path
(LangChain) and no dead code, data or docs left over from the comparison.

## Decisions already made by the user
- Drop the Stage 3 vector column `sectors.embedding`, with an Alembic migration.
  LangChain's own copy of the vectors (`langchain_pg_embedding`) stays.
- One delivery for the whole ticket, no increments.
- This overrides two earlier decisions: ticket 004 (keep `sectors.embedding` and
  `embed_sectors.py` until Stage 6 ends) and ticket 005 (keep `client` / `log_usage()`
  for the playground comparison).

## What exists today
(Checked against the code on 2026-10-09.)
- Playground, `backend/app/scripts/rag_playground.py`: steps 6.2, 6.3, 6.4, 6.5, 6.6.
  - 6.3 compares LangChain PGVector with Stage 3 raw SQL on `Sector.embedding`. Comparison only.
  - 6.6 compares `messages.parse` with the LangChain parse chain. Comparison only. Its
    helpers `parse_with_messages_api`, `run_side`, `show_value` and the `NATURAL_QUERIES`
    list exist only for it. The file imports `client`, `log_usage`, `Sector`,
    `Callable`, `PARSE_SYSTEM_PROMPT`, `ParsedFilters` partly for these.
  - Steps 6.2, 6.4, 6.5 are LangChain only.
- Tests in `backend/tests/test_rag_chain.py`: `test_step_6_6_prints_both_parsers_side_by_side`
  and `test_step_6_6_keeps_comparing_when_one_side_fails` cover 6.6 (they monkeypatch
  `rag_playground.client`). `test_step_6_5...` (around line 107) covers 6.5 and stays. I found
  no test for 6.3.
- `backend/app/services/llm.py`: holds the Anthropic SDK `client` and `log_usage()`
  (Stage 3 only now), plus `LLM_MODEL` and `log_tokens()`, which `app/rag/llm.py` imports
  and which stay.
- `backend/app/services/embedding.py`: holds the `voyage` client and `embed_query()`
  (Stage 3 only now) plus `EMBED_MODEL`, which `app/rag/vectorstore.py` imports and which stays.
  `embed_query` has no remaining caller besides what the playground/Stage 3 used; the
  similar search calls the LangChain embeddings object's own `embed_query`.
- `backend/app/models/sector.py` line 35: `embedding` column (`Vector(1024)`), added by
  migration `178caab75ad8` (which also added `approach_notes`, which must stay). Nothing
  in routers, schemas or services reads it except playground step 6.3 and
  `embed_sectors.py`.
- `backend/app/scripts/embed_sectors.py` does three things: it fills `approach_notes` from
  its `NOTES` dict, it defines `build_text()` (imported by `app/rag/loader.py`), and it
  writes `sectors.embedding` through Voyage. Only the last one is Stage 3.
- `backend/tests/test_usage_logging.py::test_log_usage_reads_an_anthropic_response` tests
  `log_usage()`. The two `UsageLogger` tests in that file are LangChain and stay.
- Docs: `README.md` seed steps (lines 24-26 mention `embed_sectors` as "approach notes +
  Voyage embeddings" and as the source of the notes for the LangChain index), structure
  entries for `llm.py`, `embedding.py`, `embed_sectors.py`, `rag_playground.py`, and a
  pgvector mention near line 66. `CLAUDE.md` "Reuse before writing" lists the client,
  `log_usage()` and `embed_query()`, and "Traps" mention `sectors.embedding`.
  Comments mentioning Stage 3 also appear in `rag/loader.py`, `rag/vectorstore.py`,
  `rag/llm.py`, `scripts/seed_stays.py`; they should not point at things that no longer exist.
- `anthropic` and `voyageai` stay in `pyproject.toml` for now. `langchain-anthropic` and
  `langchain-voyageai` depend on them anyway, as `uv.lock` shows.

## Acceptance criteria
1. Given the app after this ticket, when a climber calls `/search/similar`, then the
   response (status codes, fields, ordering, per-sector reasons, 503 on embedding
   failure) is the same as before.
2. Given the app after this ticket, when a climber calls `/search/natural`, then the
   response and its error cases (422, 400 style, 400 grades, 503) are the same as before.
3. Given the playground, when run with steps 6.2, 6.4 and 6.5, then each behaves as
   before. When run with 6.3 or 6.6, then the usage message lists only the remaining
   steps and exits with an error code, as it does today for an unknown step.
4. Given the playground output of any remaining step, when read, then nothing in it
   compares Stage 3 with LangChain.
5. Given the repository, when searching for imports or references to the removed code
   (the Anthropic `client`, `log_usage`, the `voyage` client, `embed_query` from
   `services/embedding.py`, `Sector.embedding`, `parse_with_messages_api`, `run_side`,
   `show_value`, `NATURAL_QUERIES`), then none remain in code, tests or docs.
6. Given `LLM_MODEL`, `log_tokens` and `EMBED_MODEL`, when the LangChain code imports
   them, then they still work and the token usage log lines look exactly as before
   (`Claude <purpose>: N in / M out tokens`).
7. Given a dev database at the current migration head, when `uv run alembic upgrade head`
   runs, then `sectors.embedding` no longer exists, `sectors.approach_notes` and all
   other columns and rows are untouched, and `langchain_pg_embedding` still holds its vectors.
8. Given the new migration applied, when `uv run alembic downgrade -1` runs, then it
   succeeds and the `sectors.embedding` column exists again (empty, nullable); and
   upgrading again succeeds.
9. Given an empty database, when the README "Running locally" steps are followed in order,
   then every sector has its approach notes and the LangChain collection `sectors` is
   indexed, and no step requires the removed Stage 3 embedding. Given the same steps
   after this ticket, the number of Voyage requests is one (the LangChain indexing), not two.
10. Given the notes and the `build_text()` text format that `rag/loader.py` relies on,
    when the loader builds a Document for a sector, then its text is identical to today's.
    (Where the notes and `build_text` live afterwards is the tech lead's call.)
11. Given `uv run pytest`, when it runs with no network and no API keys, then it is green:
    the tests for the removed behaviour are deleted, the LangChain tests are kept, and no
    test depends on `Sector.embedding`.
12. Given `README.md` and `CLAUDE.md`, when read, then the seed steps, the file structure,
    "Reuse before writing" and "Traps" describe only what exists, with no mention of the
    removed client, `log_usage`, `embed_query` or `sectors.embedding` as live code. The
    README structure matches the files that exist (CLAUDE.md definition of done 3).
13. Edge case: given a dev database where `sectors.embedding` still holds vectors, when
    the upgrade runs, then it succeeds (the data is discarded, by decision) and the
    dev server starts and `/search/similar` still works.

## Scope
**In:**
- Remove playground steps 6.3 and 6.6, their helpers, constants and imports, and their tests.
- Remove the Anthropic SDK `client` and `log_usage()` from `services/llm.py`, and the
  `voyage` client and `embed_query()` from `services/embedding.py`; keep the constants
  and `log_tokens` that LangChain code uses.
- Remove the `embedding` column from the model, with a reviewed Alembic migration
  (upgrade and downgrade).
- Remove the Stage 3 embedding work from `embed_sectors.py` while keeping the approach
  notes and `build_text()` available to seeding and `rag/loader.py`.
- Update `README.md` and `CLAUDE.md`, and stale "Stage 3" comments in the touched files.

**Out:**
- Removing `anthropic` / `voyageai` from `pyproject.toml`: the LangChain packages depend
  on them, and `uv add/remove` hits the OneDrive lock trap. Only if the tech lead finds it
  clearly safe, and then with the dev server stopped.
- `ANTHROPIC_API_KEY` / `VOYAGE_API_KEY` settings: LangChain still uses both.
- Frontend: no frontend code uses the removed things (`types.ts` has no embedding field,
  and the API response already hides it, per `test_similar_api.py`).
- The `pgvector` extension and the `pgvector` Python package: `langchain-postgres` needs them.
- Changing LangChain behaviour, prompts, models or any API response.
- Migrating the data in `sectors.embedding` anywhere: LangChain has its own copy.

## Open questions
- [non-blocking] Where should the approach notes and `build_text()` live once
  `embed_sectors.py` stops embedding? (suggested default: the tech lead decides; the user
  only requires acceptance criteria 9 and 10. One option is to rename the script to
  something like `seed_notes`, with the README steps updated.)
- [non-blocking] Should the downgrade restore the column only, with no data (it cannot
  restore the vectors)? (suggested default: yes, document it in the migration.)
- [non-blocking] Should the playground docstring and `README` still describe the
  playground as "Stage 6 steps" with 6.3 and 6.6 simply missing from the numbering?
  (suggested default: yes, keep the other step numbers so the plans and tickets 003-005
  stay readable.)

## Notes for the tech lead
- Differences from the request as relayed: nothing contradicts it. Details I confirmed or
  added: I found no existing test for step 6.3; `embed_query()` in `services/embedding.py`
  has no live caller (the similar search uses the LangChain embeddings object's own
  `embed_query`); `test_rag_chain.py` still imports `LLM_MODEL` from `services.llm`, which
  stays; the playground also imports `Sector`, `Callable` and `ParsedFilters` which may
  become unused (the lint hook runs on each edited file).
- CLAUDE.md rules that apply: a model change needs a reviewed migration (`alembic/env.py`
  compares only our own tables, check the autogenerated diff does not touch PostGIS or
  `langchain_pg_*` tables); the Traps entry about running `alembic upgrade head` after
  delivering a migration; tests build their schema with `create_all()`, so green tests do
  not prove the dev DB is current; no network in tests; `pgvector` stays pinned `<0.4`.
- The migration that created `embedding` (`178caab75ad8`) also created `approach_notes`
  and may have created the `vector` extension. The new migration must not drop the
  extension, LangChain's tables need it. Check this before writing the downgrade.
- Seed order matters (CLAUDE.md "Commands"): `index_sectors_langchain` needs the approach
  notes, so the notes step must still run before it.
- New files or folders (for example a renamed script) go into the README structure.
