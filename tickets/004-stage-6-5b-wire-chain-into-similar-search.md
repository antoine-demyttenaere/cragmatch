# 004: Stage 6.5b, wire the LangChain RAG path into the fuzzy search endpoint

**Status:** Ready
**Size:** M
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "Only after that, wire it to the /search/natural fuzzy-matching path from Stage 3, replacing your hand-built version."

## User story
As a climber using "describe the vibe" search, I want the same kind of results and reasons
as today, now produced by the LangChain pipeline, so that the app runs on the rebuilt RAG
instead of the hand-built Stage 3 code.

## What exists today
- **The plan names `/search/natural`, but that endpoint isn't the fuzzy path.**
  `POST /search/natural` (`routers/search.py:53`) turns free text into hard filters with
  `client.messages.parse(output_format=ParsedFilters)`. That's the parsing that ticket
  005 (Stage 6.6) rebuilds.
- The fuzzy, retrieval-based path is `POST /search/similar` (`routers/search.py:111`):
  `embed_query()` → pgvector `cosine_distance` → `explain_matches()` (Claude reasons) →
  `SimilarSearchResponse` with `similarity` and `reason` for each sector.
- `SimilarMatch` returns a `similarity` score. **A plain retriever drops scores** (seen in
  6.4), so the endpoint needs `similarity_search_with_score` or an equivalent.
- `tests/test_similar_api.py` (8 tests) monkeypatches `embed_query` and `explain_matches`
  on `app.routers.search`. Those patches stop working once the endpoint calls LangChain.

## Acceptance criteria
1. Given a query, when `POST /search/similar` is called, then the response shape is
   unchanged: each result has a sector, a similarity between 0 and 1, and a reason or null.
2. Given the same query and data, when it runs through LangChain, then the sector ranking
   matches the Stage 3 version (6.3 showed identical distances).
3. Given Claude fails, when the endpoint runs, then the results still come back with
   `reason: null` (same as today), and no 500.
4. Given Voyage fails, when the endpoint runs, then it returns 503 with the current message.
5. Given the tests, when `uv run pytest` runs, then no test calls Voyage or Claude: the
   LangChain pieces are mocked where the router uses them.
6. Given the rate limit, when the endpoint is called, then it is still limited to 10/minute.

## Scope
**In:** `/search/similar` runs on the PGVector store and a LangChain chain for the reasons.
The tests are updated to mock the new seams.

**Out:**
- `/search/natural` parsing: that's ticket 005.
- Deleting `sectors.embedding` or `embed_sectors.py`: keep the Stage 3 path's data until
  Stage 6 is finished, so the two can still be compared.
- Frontend changes: the response shape doesn't change.

## Decisions
- **Which endpoint 6.5 replaces:** `/search/similar`, the retrieval path.
  `/search/natural` stays as it is and is covered by ticket 005 (Stage 6.6).
- **Stage 3 code:** delete it from the router (it stays in git history), no switch.
  Keep `sectors.embedding` and `embed_sectors.py` for comparison until Stage 6 ends.

## Notes for the tech lead
- The ranking needs scores: `PGVector.similarity_search_with_score` returns
  `(Document, distance)`; similarity = 1 - distance, as today.
- Documents carry `sector_id` in their metadata. The endpoint still needs `Sector` rows
  (with `crag`) for `SectorRead`, so load them by id in one query, keeping the order.
- Re-index (`app.scripts.index_sectors_langchain`) only if `build_text()` or the notes
  change. Mind Voyage's 3 requests/minute.
