"""PreToolUse hook: keep Claude away from the secrets in .env files.

Claude Code sends the tool call it is about to make as JSON on stdin.
Exit 2 blocks the call, and what we print to stderr is shown to Claude as
the reason. Exit 0 lets the call through.
"""

import json
import re
import sys
from pathlib import PurePath

# ".env" in a shell command, but not ".env.example" or ".envrc".
ENV_IN_COMMAND = re.compile(r"\.env(?![\w.])")


def is_env_file(path: str) -> bool:
    return PurePath(path).name == ".env"


def main() -> int:
    sys.stderr.reconfigure(encoding="utf-8")
    call = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    tool = call.get("tool_name")
    args = call.get("tool_input", {})

    if tool in ("Read", "Edit", "Write") and is_env_file(args.get("file_path", "")):
        target = args["file_path"]
    elif tool == "Grep" and is_env_file(args.get("path", "")):
        target = args["path"]
    elif tool in ("Bash", "PowerShell") and ENV_IN_COMMAND.search(args.get("command", "")):
        target = args["command"]
    else:
        return 0

    print(
        f"Blocked: {target!r} touches a .env file, which holds secrets. "
        "Ask the user to make this change themselves. .env.example is fine to read and edit.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
