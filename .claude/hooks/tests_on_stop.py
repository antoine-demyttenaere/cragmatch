"""Stop hook: run the backend tests before Claude says it's done.

Only runs if Claude edited backend Python since the last green run (the
marker left by lint_after_edit.py), so your own half-typed code never sets
it off. Exit 2 makes Claude keep working, with our stderr as its input.
"""

import json
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
MARKER = ROOT / ".claude" / ".backend-edited"
MAX_ATTEMPTS = 3


def database_is_up() -> bool:
    # Without this check, pytest would hang on the first DB connection.
    try:
        with socket.create_connection(("localhost", 5433), timeout=2):
            return True
    except OSError:
        return False


def main() -> int:
    sys.stderr.reconfigure(encoding="utf-8")
    call = json.loads(sys.stdin.buffer.read().decode("utf-8"))

    if not MARKER.exists():
        return 0  # Claude didn't touch backend Python: nothing to test

    if not database_is_up():
        if call.get("stop_hook_active"):
            return 0  # we already said so once; let Claude stop
        print(
            "Backend code changed but the tests can't run: the database on port 5433 is down. "
            "Don't change any code for this. Tell the user to start Docker Desktop and run "
            "`docker compose up -d`, then run `uv run pytest` in backend/.",
            file=sys.stderr,
        )
        return 2

    result = subprocess.run(
        ["uv", "run", "--no-sync", "pytest", "-q", "-x", "-p", "no:warnings"],
        cwd=BACKEND, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=240,
    )
    if result.returncode == 0:
        MARKER.unlink()
        return 0

    attempts = int(MARKER.read_text() or 0) + 1
    tail = "\n".join(result.stdout.splitlines()[-60:])
    if attempts >= MAX_ATTEMPTS:
        MARKER.unlink()
        print(
            f"Tests still fail after {attempts} attempts. Stop changing code and report the "
            f"failure below to the user, with what you tried:\n{tail}",
            file=sys.stderr,
        )
        return 2

    MARKER.write_text(str(attempts))
    print(f"Backend tests fail (attempt {attempts}/{MAX_ATTEMPTS}). Fix them before finishing:\n{tail}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
