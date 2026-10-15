FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# Bytecode is compiled at build time (nothing is written at run time, so a
# read-only filesystem works), uv uses the image's Python, and logs go
# straight to stdout for the platform's log collector.
ENV UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1

WORKDIR /app

# Exactly the lock, no dev group, no uv cache left in the layer. This layer is
# reused while the lock is unchanged.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

# Only what runs: no tests, caches or .env.
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH"

# Not root, and a writable place for the Voyage tokenizer download. A platform
# with a read-only home overrides HF_HOME.
RUN useradd --create-home --uid 10001 --user-group cragmatch
ENV HF_HOME=/home/cragmatch/.cache/huggingface
USER cragmatch

EXPOSE 8000

# fastapi run listens on 0.0.0.0 and on $PORT (default 8000). One worker
# because the rate limits live in memory. Exec form so the server gets the
# stop signal. CMD (not ENTRYPOINT) so the same image can run
# "alembic upgrade head" instead.
CMD ["fastapi", "run", "app/main.py", "--workers", "1"]
