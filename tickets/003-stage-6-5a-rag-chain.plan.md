# Plan for 003: Stage 6.5a, the smallest RAG chain, end to end

**Ticket:** `tickets/003-stage-6-5a-rag-chain.md`
**Approach:** Add `langchain-anthropic` and a small `get_chat_model()` factory in
`app/rag/llm.py` that mirrors the Stage 3 client settings (`LLM_MODEL`, key from
`settings`, 20 s timeout, 2 retries, `max_tokens`). Put the reusable chain parts
(`format_docs`, the prompt, `build_rag_chain()`) in a new `app/rag/chain.py`, so
they can be tested without the network and ticket 004 can import them. `step_6_5`
in the playground first runs the pieces one by one, printing what each one hands
to the next, and then runs the composed LCEL chain on the same query.
**Alternatives considered:**
- `format_docs` and the prompt inside `rag_playground.py`: the ticket's scope lists
  only `llm.py` and the playground, but scripts aren't importable building blocks, and
  ticket 004 needs the same prompt/format/chain. A ~30-line `chain.py` is the smaller
  total change across 003 and 004.
- Two increments (dependency, then code): the dependency change on its own is just
  `pyproject.toml` + `uv.lock` and has nothing to test. One commit keeps the
  dependency with the code that needs it. The environment repair below happens before
  the increment and is never committed.

## Ticket check
- `app/rag/vectorstore.py` (`get_embeddings()`, `get_vector_store()`, collection
  `sectors`, 1024 dims), playground steps 6.2/6.3/6.4, `services/llm.py`
  (`client`, `LLM_MODEL = "claude-sonnet-5"`, `log_usage()`) and `services/explain.py`
  (`client.messages.parse`): all as described.
- `langchain-anthropic` is not installed: confirmed (`.venv/Lib/site-packages` has
  no `langchain_anthropic`; not in `pyproject.toml` or `uv.lock`). So I could **not**
  check the `ChatAnthropic` constructor against the installed version. The developer
  must do that after `uv add` (Step 0.4 below) before writing the factory.
- A dry resolution (`uv pip compile`, nothing installed) shows that `langchain-anthropic`
  resolves with `pgvector==0.3.6` kept: 1.7.4 with the current locks
  (`anthropic` 1.7.0, `langchain-core` 1.6.5), or 1.7.5 if uv bumps `anthropic` /
  `langchain-core` / `langchain-postgres`. So AC 1 is achievable either way.
- `log_usage()` can't be reused for the LangChain call: it reads
  `response.usage.input_tokens` (Anthropic SDK object), while LangChain returns an
  `AIMessage` with a `usage_metadata` dict. The step prints `usage_metadata` (AC 3c).
  Don't change `log_usage()`.
- **Brief vs. reality, `app/rag/__init__.py`:** the brief said it contains a `main()`
  (a copy of step 6.2) that runs on every `import app.rag.*`. It doesn't: the file is
  0 bytes on disk and in `HEAD` (blob `e69de29`, the empty blob, since `89777c1`).
  There is only a stale `__pycache__/__init__.cpython-312.pyc`, which Python
  regenerates. **Decision: leave `__init__.py` alone**, since there's nothing to fix.
- **The venv is broken right now (not caused by this ticket, must be repaired first):**
  `uv run pytest -q` fails at conftest import with
  `ImportError: cannot import name 'BaseDocumentTransformer' from 'langchain_core.documents' (unknown location)`.
  `.venv/Lib/site-packages/langchain_core/` has its folders but **0 `.py` files**,
  and `langchain_core-1.6.5.dist-info` has no `RECORD`. Both were modified today at
  17:33:13-14, the same second `pyproject.toml` and `uv.lock` were rewritten. Those
  two files show no git diff, so they were restored. That's the signature of a
  `uv add`/`uv sync` that failed partway: uv rolls back the project files but not the
  half-replaced package. The dev server (`fastapi dev app/main.py`, PID 15044, parent
  28156, started 16:05) was running at the time, which is the OneDrive-lock trap in
  CLAUDE.md.
- **Port 8000 is in use now** by that dev server (PID 15044, verified as
  `...\.venv\Scripts\fastapi.exe dev app/main.py`). It must be stopped before any `uv`
  command (Step 0.1).
- README is missing the whole `app/rag/` folder and the scripts
  `index_sectors_langchain.py` and `rag_playground.py` (gap from 6.2-6.4). This
  increment adds them, because Definition of done #3 requires `llm.py`/`chain.py` to
  be listed and they can't be listed under a folder that isn't there.

## Step 0: repair and prepare the environment (before the increment, not committed)
1. **The user** stops the dev server: Ctrl+C in its terminal. If that terminal is gone,
   stop it only by exact, verified PID (CLAUDE.md Traps): check with
   `netstat -ano | findstr :8000` that it's still PID 15044 / its parent 28156, then stop
   that PID. The developer agent must not stop processes itself.
2. Developer confirms nothing listens on 8000 (`netstat -ano | findstr :8000` is empty).
3. Repair: `uv sync --reinstall-package langchain-core`, then `uv run pytest -q` must be
   **green before any change** (this is the baseline for AC 1). If it's still red, stop
   and report. Don't start the increment on a red baseline.
4. `uv add langchain-anthropic`, then check:
   - `git diff pyproject.toml`: only the new `langchain-anthropic>=...` line is added;
     `"pgvector>=0.3.6,<0.4"` is unchanged.
   - `git diff uv.lock`: `pgvector` stays `0.3.6`. Patch/minor bumps of `anthropic`,
     `langchain-core` or `langchain-postgres` are acceptable. Mention them in the report.
   - `uv run pytest -q` still green (AC 1).
   - **Verify the constructor in the installed version** before writing `llm.py`:
     `grep -n -E "^\s+(model|model_name|max_tokens|default_request_timeout|max_retries|anthropic_api_key)\b.*(Field|=)" .venv/Lib/site-packages/langchain_anthropic/chat_models.py`.
     Expected (langchain-anthropic 1.x): `model` (alias `model_name`), `max_tokens`
     (alias `max_tokens_to_sample`), `default_request_timeout` (alias `timeout`),
     `max_retries` (default 2), `anthropic_api_key` (alias `api_key`, a `SecretStr`).
     If any name differs, use the installed names and say so in the report.

## Increments

### 1. ChatAnthropic factory, chain helpers and playground step 6.5
**Files:**
- `backend/pyproject.toml`, `backend/uv.lock`: `langchain-anthropic` (from Step 0.4).
- `backend/app/rag/llm.py` (new): `get_chat_model(max_tokens: int = 1024) -> ChatAnthropic`.
  Builds `ChatAnthropic(model=LLM_MODEL, api_key=settings.anthropic_api_key,
  timeout=20.0, max_retries=2, max_tokens=max_tokens)`, using the keyword names verified
  in Step 0.4. It reads `settings` **at call time** (inside the function), not at import,
  so the test can swap the key. Short why-comment: same timeout/retries as
  `services/llm.py` so both paths fail the same way.
- `backend/app/rag/chain.py` (new):
  - `RAG_PROMPT`: a `ChatPromptTemplate.from_messages([("system", ...), ("human", "{question}")])`.
    The system message says: answer using ONLY the sectors below, name the sectors you
    recommend, say so if none fit, then `Sectors:\n{context}`. It reuses the grounding
    wording of `EXPLAIN_PROMPT` in `services/explain.py`.
  - `format_docs(docs: list[Document]) -> str`: the docs' `page_content` joined with a
    blank line, in retriever order. An empty list gives `""` (no result is normal; the
    prompt handles it).
  - `build_rag_chain(retriever: Runnable, llm: Runnable) -> Runnable`: returns exactly
    `{"context": retriever | format_docs, "question": RunnablePassthrough()} | RAG_PROMPT | llm | StrOutputParser()`.
    Type the parameters as `Runnable`, not `VectorStoreRetriever`/`ChatAnthropic`, so tests
    can pass `RunnableLambda` fakes.
- `backend/app/scripts/rag_playground.py`:
  - Import `get_chat_model` from `app.rag.llm` and `RAG_PROMPT`, `format_docs`,
    `build_rag_chain` from `app.rag.chain` **by name** (the test patches
    `rag_playground.get_vector_store` / `rag_playground.get_chat_model`).
  - `step_6_5(query: str = "quiet crag with a short approach, good for a beginner", k: int = 3)`,
    docstring `"... 2 Voyage calls, 2 Claude calls."` (matches the style of 6.3/6.4).
    Build `retriever = get_vector_store().as_retriever(search_kwargs={"k": k})` and
    `llm = get_chat_model()` once. Then:
    - **(a)** `docs = retriever.invoke(query)` (Voyage call 1): print each doc's
      `metadata["name"]`, `metadata["crag"]` and `page_content`.
    - `context = format_docs(docs)`; `prompt_value = RAG_PROMPT.invoke({"context": context, "question": query})`.
    - **(b)** print every message in `prompt_value.to_messages()`: its `type` and full
      `content`, i.e. the filled template exactly as Claude receives it.
    - **(c)** `message = llm.invoke(prompt_value)` (Claude call 1): print `type(message).__name__`,
      `message.content`, `message.usage_metadata`, and `message.response_metadata.get("stop_reason")`.
    - **(d)** `answer = StrOutputParser().invoke(message)`: print it.
    - Then the composed chain: `build_rag_chain(retriever, llm).invoke(query)`
      (Voyage call 2, Claude call 2), printed under its own heading so the two answers
      can be compared side by side (AC 4).
  - Add `"6.5": step_6_5` to `STEPS` and `6.5` to the module docstring's run examples.
- `README.md`: in the `app/` tree, add a `rag/` block after `services/`
  (`loader.py` SectorLoader: sectors as LangChain Documents; `vectorstore.py`
  Voyage embeddings + PGVector store, collection `sectors`; `llm.py` ChatAnthropic
  factory; `chain.py` prompt, format_docs, build_rag_chain), and under `scripts/` add
  `index_sectors_langchain.py` and `rag_playground.py` (Stage 6 steps, one per function).
- **Leave alone:** `app/rag/__init__.py`, `services/llm.py` (incl. `log_usage`),
  `services/explain.py`, `routers/`, all frontend files.

**Reuses:** `LLM_MODEL` (`services/llm.py`), `settings` (`core/config.py`),
`get_vector_store()` (`rag/vectorstore.py`), the playground's step/`STEPS` pattern,
the grounding wording of `EXPLAIN_PROMPT`, and the monkeypatch-where-used test pattern
from `tests/test_similar_api.py`. LangChain's own `ChatPromptTemplate`,
`RunnablePassthrough`, `StrOutputParser` and `RunnableLambda` (all in `langchain_core`,
already installed). No new helper beyond `format_docs` / `build_rag_chain`.

**Tests:** new file `backend/tests/test_rag_chain.py`. No network: no real Voyage,
Claude or PGVector object is ever invoked. The fakes are `RunnableLambda`s that return
fixed `Document`s / an `AIMessage(content=..., usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})`.
None of these tests need the database fixtures.
- `test_chat_model_uses_llm_model_and_settings_key`: `monkeypatch.setattr(settings, "anthropic_api_key", "test-key")`,
  then `get_chat_model()`. Asserts the model name `== LLM_MODEL` and the key's
  `.get_secret_value() == "test-key"`, which proves it comes from settings and isn't
  hardcoded. Use the fake key so the real one never appears in assertion output. (AC 2)
- `test_chat_model_has_timeout_retries_and_max_tokens`: default call gives timeout `20.0`,
  `max_retries == 2`, `max_tokens == 1024`; `get_chat_model(max_tokens=300)` gives `300`.
  Attribute names as verified in Step 0.4. (AC 2)
- `test_format_docs_joins_in_order_with_blank_lines`: two Documents give
  `"first text\n\nsecond text"`. (AC 3/4: what reaches `{context}`)
- `test_format_docs_empty_is_empty_string`: `format_docs([]) == ""`, no exception.
- `test_rag_chain_fills_prompt_and_returns_string`: fake retriever returns two docs for any
  query. The fake LLM records the `ChatPromptValue` it receives and returns an `AIMessage("Try Poble.")`.
  Asserts that `build_rag_chain(fake_retriever, fake_llm).invoke("beginner crag")` returns
  the **str** `"Try Poble."`, that the recorded system message contains both docs' text,
  that the recorded human message `== "beginner crag"`, and that the retriever received
  `"beginner crag"`. (AC 4: the composed chain wires context/question correctly)
- `test_step_6_5_prints_each_stage_and_calls_retriever_twice`: monkeypatch
  `rag_playground.get_vector_store` with a fake store whose `as_retriever(**kwargs)` returns
  a counting fake retriever, and `rag_playground.get_chat_model` with the fake LLM. Run
  `step_6_5()` and capture with `capsys`. Asserts the retriever was invoked **exactly 2**
  times (AC 5), and that the output contains the doc names (a), the filled system text
  and the query (b), `AIMessage` and `input_tokens` (c), and the final answer
  string (d). (AC 3, AC 5)

**Check by hand:** with the DB up and the `sectors` collection indexed (13 docs), run
`uv run python -m app.scripts.rag_playground 6.5` **once** (2 Voyage requests out of the
3/min, 2 small Claude calls). Read (a)-(d), confirm (c) shows `usage_metadata` with
non-zero `input_tokens`/`output_tokens`, and compare the step-by-step answer with the
composed-chain answer: same recommended sectors / same meaning (AC 4). Wording may
differ because Claude isn't deterministic. Don't re-run within a minute. Also
`uv run pytest -q` and `uv run ruff check .` are green. Leave the dev server stopped
until the developer is done. The user restarts it afterwards.

**Commit:** `Stage 6.5a: smallest RAG chain (retriever, prompt, ChatAnthropic, StrOutputParser) as playground step 6.5; add langchain-anthropic, a ChatAnthropic factory and reusable chain helpers in app/rag`

## Walk-through (for the user: what each piece passes to the next)
Example query: `"quiet crag with a short approach, good for a beginner"`, `k=3`.

1. **Input: a plain `str`.** In the composed chain, `.invoke(query)` hands the same
   string to both branches of the dict at the start.
2. **The dict `{"context": ..., "question": ...}`.** LCEL turns a dict into a
   `RunnableParallel`: every value is a runnable that gets the **same input**, and the
   result is a dict with the same keys.
   - `"question": RunnablePassthrough()` returns its input unchanged, so `question` is
     the query string.
   - `"context": retriever | format_docs`:
     - The **retriever** embeds the query with Voyage (`input_type="query"`, 1 request),
       asks PGVector for the 3 closest sectors, and returns `list[Document]`. Each
       `Document` has `page_content` (the same text Stage 3 embedded, e.g.
       `"Poble at <crag> in <region>. Style: sport. Grades: ... Approach: Easy-going crag just above the village, 5 minutes from the car..."`)
       and `metadata` (`sector_id`, `name`, `crag`, `style`, grades). The scores are
       dropped, as seen in 6.4.
     - **`format_docs`** is a plain function. Next to `|` LangChain wraps it in a
       `RunnableLambda`. It turns the list into **one string**: the three
       `page_content`s separated by blank lines. Metadata isn't included, so Claude only
       sees the text.
   - Output of this stage: `{"context": "<3 sector texts>", "question": "quiet crag ..."}`.
3. **`RAG_PROMPT` (a `ChatPromptTemplate`).** It fills `{context}` and `{question}` and
   returns a `ChatPromptValue`, i.e. a list of messages:
   `SystemMessage("Answer using ONLY these sectors ... Sectors:\n<3 sector texts>")` and
   `HumanMessage("quiet crag with a short approach, good for a beginner")`. Step (b)
   prints exactly this, which is everything Claude will see.
4. **`llm` (`ChatAnthropic`).** It sends those messages to the Messages API (model
   `LLM_MODEL`, `max_tokens` 1024, 20 s timeout, 2 retries) and returns an **`AIMessage`**:
   `content` (the answer text), `usage_metadata` (`input_tokens`, `output_tokens`,
   `total_tokens`) and `response_metadata` (model, `stop_reason`, ...). Step (c) prints it.
5. **`StrOutputParser`.** It takes the `AIMessage` and returns just `message.content` as
   a **`str`**. Step (d) prints it, and it's what the whole chain returns.

**LCEL `|` vs. Stage 3's `explain.py`.** In `explain_matches()` every hand-off is written
out: build `sector_lines` with an f-string, call `client.messages.parse(model=..., system=..., messages=[...], output_format=MatchReasons)`,
call `log_usage()`, read `response.parsed_output`. The LCEL chain does the same hand-offs
(retrieve, format, fill prompt, call model, extract output), but each one is a `Runnable`
with the same `.invoke()` interface, and `|` connects them. That makes pieces easy to swap
(a different retriever, model or parser) and gives every step `.batch()`/`.stream()` for
free. The cost: the hand-offs are hidden, which is why step 6.5 runs them one by one
first. Structured output, the equivalent of `output_format=MatchReasons`, comes in ticket 005.

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | Step 0.3/0.4 (pyproject and lock diff review: pin unchanged, pgvector 0.3.6) + `uv run pytest -q` green after `uv add` |
| 2 | `tests/test_rag_chain.py::test_chat_model_uses_llm_model_and_settings_key`, `::test_chat_model_has_timeout_retries_and_max_tokens` |
| 3 | `tests/test_rag_chain.py::test_step_6_5_prints_each_stage_and_calls_retriever_twice` (a-d present, mocked) + manual run of step 6.5 (real content, real `usage_metadata`) |
| 4 | `tests/test_rag_chain.py::test_rag_chain_fills_prompt_and_returns_string` (wiring) + manual comparison of the two answers. "Same meaning" can only be judged by hand. |
| 5 | `tests/test_rag_chain.py::test_step_6_5_prints_each_stage_and_calls_retriever_twice` (retriever invoked exactly 2 times = 2 Voyage requests) |

No criterion is left uncovered. AC 4's "same meaning" is a manual check by nature.

## Risks
- **Broken venv / OneDrive locks:** `langchain_core` is currently half-uninstalled (see
  Ticket check). If the dev server or any other Python process from `.venv` holds files,
  `uv` fails again in the same way. Mitigation: Step 0 (stop server, confirm port 8000 is
  free, reinstall, green baseline before `uv add`). Until it's repaired, the
  tests-on-stop hook fails for every agent, whatever the change.
- **Dependency drift:** `uv add` may bump `anthropic`, `langchain-core` or
  `langchain-postgres`. Mitigation: review `git diff uv.lock`. `pgvector` must stay
  `0.3.6`, and the full suite (incl. `test_similar_api.py`, which uses the Anthropic and
  Voyage paths through mocks) must stay green.
- **Constructor names differ in the installed version:** Mitigation: Step 0.4 grep, and
  the tests assert on the verified attribute names.
- **Unknown model name:** `LLM_MODEL = "claude-sonnet-5"`. If the installed
  `langchain-anthropic` looks up model profiles, it could warn on construction. Setting
  `max_tokens` explicitly avoids relying on a profile default. If it warns, note it in
  the report and don't change `LLM_MODEL` (user's Stage 3 decision).
- **Voyage 3 req/min:** step 6.5 makes 2 requests. Running it twice within a minute
  (or right after 6.4, which makes 3) gives a 429. Mitigation: the docstring states the
  count, and the manual check says run once.
- **Claude cost:** 2 calls of ~1k input tokens each per run. Small, but don't loop it.
- **Network in tests:** all tests use `RunnableLambda` fakes. `get_chat_model()` only
  *constructs* `ChatAnthropic`, which makes no request. LangSmith tracing is installed
  (`langsmith`) but stays off unless `LANGCHAIN_TRACING_V2`/`LANGSMITH_TRACING` is set,
  so don't set it.
- **Behaviour that must stay unchanged:** all API endpoints, `services/llm.py`,
  `services/explain.py`, playground steps 6.2-6.4.
- **Secrets:** the key only comes from `settings`. Tests use a fake key and never print
  or assert on the real one.

## Out of scope (copied from the ticket)
- Wiring the chain into an endpoint: that's ticket 004.
- Structured output: that's ticket 005.
- Streaming, memory or chat history: not in the Stage 6 plan.
