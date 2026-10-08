"""PreToolUse hook for the product-owner and tech-lead agents: they may
write in tickets/ and nowhere else.

It is registered in those agents' frontmatter, not in settings.json, so it
only runs while one of them is working.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKETS = ROOT / "tickets"


def main() -> int:
    sys.stderr.reconfigure(encoding="utf-8")
    call = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    file_path = call.get("tool_input", {}).get("file_path", "")

    target = Path(file_path)
    if not target.is_absolute():
        target = Path(call.get("cwd", ROOT)) / target
    if target.resolve().is_relative_to(TICKETS):
        return 0

    print(
        f"Blocked: this agent may only write in tickets/, not {file_path!r}. "
        "Describe the change in the ticket or plan instead; the developer agent changes code.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
