"""PostToolUse hook: lint each file right after Claude edits it.

The edit has already happened, so this can't block it. Exit 2 shows our
stderr to Claude, which fixes the problem while the file is still fresh in
its context. When backend Python changes, it also leaves a marker file so
the Stop hook knows the tests need to run.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .claude/hooks/ -> repo root
BACKEND = ROOT / "backend"
# Each app has its own node_modules and ESLint config. Ticket 017 removes frontend/.
FRONTEND_APPS = [ROOT / "web", ROOT / "frontend"]
MARKER = ROOT / ".claude" / ".backend-edited"


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=50,
    )


def lint(path: Path) -> subprocess.CompletedProcess | None:
    """Run the right linter for this file, or None if it isn't ours to lint."""
    if path.suffix == ".py" and path.is_relative_to(BACKEND):
        MARKER.touch()
        # --no-sync: never let a hook install packages (OneDrive locks, and slow)
        return run(["uv", "run", "--no-sync", "ruff", "check", "--output-format", "concise", str(path)], BACKEND)
    if path.suffix in (".ts", ".tsx"):
        for app in FRONTEND_APPS:
            if path.is_relative_to(app / "src"):
                # Call ESLint through node directly: npx is a .cmd file on Windows,
                # which subprocess can't start without a shell.
                eslint = app / "node_modules" / "eslint" / "bin" / "eslint.js"
                return run(["node", str(eslint), str(path)], app)
    return None


def main() -> int:
    sys.stderr.reconfigure(encoding="utf-8")
    call = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    file_path = call.get("tool_input", {}).get("file_path")
    if not file_path:
        return 0

    result = lint(Path(file_path).resolve())
    if result is None or result.returncode == 0:
        return 0

    print(f"Lint errors in {file_path}. Fix them before moving on:\n{result.stdout}{result.stderr}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
