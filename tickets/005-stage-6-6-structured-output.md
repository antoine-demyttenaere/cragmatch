# 005: Stage 6.6, query parsing with LangChain structured output

**Status:** Ready
**Size:** M
**Mode:** guide. The user writes the code (see CLAUDE.local.md). This is a step brief, not for `/deliver-increment`.
**Raw request:** "Redo the query-parsing part of Stage 3 (grade, distance, style extraction) using LangChain's structured output support instead of your raw Pydantic-validation loop. Compare side by side with your Stage 3 code: same idea, different amount of boilerplate."

## User story
As a climber typing "something around 6b, not too far, sport", I want the same filters
and results as today, so that natural-language search runs through LangChain, and the
learner can compare the two ways of getting structured output.

## What exists today
- `POST /search/natural` (`routers/search.py:53`): `client.messages.parse(model=LLM_MODEL,
  system=SYSTEM_PROMPT, output_format=ParsedFilters)`, then `log_usage()`, then
  `understood` false → 422, unknown style → 400, `find_matching_sectors()` (ValueError → 400).
  Claude failing → 503.
- `ParsedFilters` (`schemas/search.py:10`): `understood`, `min_grade`, `max_grade`,
  `max_distance_km`, `style`. The field descriptions are part of the prompt.
- There is **no test for `/search/natural`** (a known gap since Stage 3).

## Acceptance criteria
1. Given a playground step `6.6`, when it parses the same 3–4 queries with Stage 3's
   `messages.parse` and with LangChain's `with_structured_output(ParsedFilters)`, then it
   prints both results side by side.
2. Given `/search/natural` switched to LangChain, when a clear query is sent, then the
   response shape is unchanged (`parsed_filters` and `results`).
3. Given an off-topic query, when it is sent, then the response is still 422 with the
   current message.
4. Given Claude fails, when the endpoint runs, then it still returns 503 with the current
   message.
5. Given a successful call, when it finishes, then token usage is still logged.
6. Given the new tests, when they run, then the structured-output call is mocked: they
   cover a clear query, `understood=false` → 422, an unknown style → 400, and failure → 503.

## Scope
**In:** a `6.6` playground comparison, `/search/natural` on LangChain, and the missing
tests for that endpoint.

**Out:**
- Changing `ParsedFilters` or the prompt wording: same contract, different plumbing.
- The fuzzy path: that's ticket 004.

## Decisions
- Reuse `ParsedFilters` as the output schema. The descriptions keep acting as instructions.

## Notes for the tech lead
- Check against the INSTALLED `langchain_anthropic`: the default `method` of
  `with_structured_output` (function calling vs JSON schema), and whether forcing a tool
  call conflicts with the model's extended thinking. Pick the method on purpose and
  explain why.
- `with_structured_output` returns the Pydantic object, not the message, so token usage
  is lost unless `include_raw=True` is used. `log_usage()` expects an Anthropic response,
  so it needs a LangChain-aware version or a callback.
