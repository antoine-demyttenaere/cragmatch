# 003: Stage 6.5a, the smallest RAG chain, end to end

**Status:** Ready
**Size:** S
**Mode:** guide. The user writes the code (see CLAUDE.local.md). This is a step brief, not for `/deliver-increment`.
**Raw request:** "Build the smallest possible chain: retriever → prompt template → LLM → output, for one hardcoded query. Run it, read the output, then ask Claude Code to walk through the chain step by step with that one example (what went into the prompt template, exactly)."

## User story
As the learner, I want to build and run one retriever → prompt → LLM → output chain on a
single query, so that I can see exactly what each LangChain piece passes to the next before
any of it touches the API.

## What exists today
- `backend/app/rag/vectorstore.py`: `get_embeddings()` (Voyage `voyage-3.5`) and
  `get_vector_store()` (PGVector, collection `sectors`, 1024 dims).
- `backend/app/scripts/rag_playground.py`: steps `6.2`, `6.3` and `6.4`, run with
  `uv run python -m app.scripts.rag_playground <step>`.
- The `sectors` collection is filled by `app.scripts.index_sectors_langchain` (13 sectors).
- Stage 3 equivalents: `services/llm.py` (Anthropic client, `LLM_MODEL`, `log_usage()`)
  and `services/explain.py` (`client.messages.parse`).
- **Missing:** `langchain-anthropic` isn't installed. `app/rag/llm.py` (a `ChatAnthropic`
  factory) doesn't exist yet.

## Acceptance criteria
1. Given the backend dev server is stopped, when `uv add langchain-anthropic` runs, then it
   installs without changing the `pgvector<0.4` pin, and `uv run pytest` still passes.
2. Given `app/rag/llm.py`, when it builds the chat model, then it uses `LLM_MODEL` and the
   key from `settings` (never hardcoded), with a timeout, retries and `max_tokens`.
3. Given `step_6_5` in the playground, when it runs on one hardcoded query, then it prints
   (a) the retrieved documents, (b) the exact prompt messages after the template is filled,
   (c) the raw `AIMessage` with its `usage_metadata`, and (d) the final string from
   `StrOutputParser`.
4. Given the same step, when it runs the composed LCEL chain
   (`{"context": retriever | format_docs, "question": RunnablePassthrough()} | prompt | llm | parser`),
   then the answer has the same meaning as the step-by-step run.
5. Given a Voyage free tier of 3 requests per minute, when the step runs once, then it
   makes at most 2 Voyage calls (one per retriever invoke).

## Scope
**In:**
- `langchain-anthropic` dependency, `app/rag/llm.py`, `step_6_5` in `rag_playground.py`.
- A written walk-through: what went into the template, what the LLM saw, what came back.

**Out:**
- Wiring the chain into an endpoint: that's ticket 004.
- Structured output: that's ticket 005.
- Streaming, memory or chat history: not in the Stage 6 plan.

## Decisions
- Model: `LLM_MODEL` from `services/llm.py`, the user's cost choice from Stage 3.

## Notes for the tech lead
- Stop the dev server before `uv add` (OneDrive locks, see CLAUDE.md Traps).
- Check the `ChatAnthropic` constructor arguments against the INSTALLED
  `langchain_anthropic` version (grep `.venv`) before giving code.
- Comparison to write down afterwards: LCEL `|` vs Stage 3's explicit
  `client.messages.parse(...)` call in `explain.py`.
