"""Load all the sample data in one go, after showing which database it is.

    uv run python -m app.scripts.load_data [--yes]

Runs seed, seed_notes, index_sectors_langchain, seed_stays, import_stays, in that
order: the notes come before the index (it embeds them) and the curated stays come
before the import (it skips OSM copies of them). Only the index step calls Voyage,
once (the free tier allows 3 a minute).

Safe to re-run: a second run leaves the data as it is. A busy Overpass makes it
exit 1 at the end; running it again finishes the job.

The target is whatever the database settings point at (README, "Loading into
another database"). It prints host:port/name and asks first; --yes skips the question.
"""

import argparse
from collections.abc import Callable, Sequence
from types import ModuleType

from sqlalchemy.engine import make_url

from app.core.config import settings
from app.scripts import import_stays, index_sectors_langchain, seed, seed_notes, seed_stays

# Modules, not functions: main is looked up when the step runs, so tests can replace it.
STEPS = (seed, seed_notes, index_sectors_langchain, seed_stays, import_stays)


def step_name(step: ModuleType) -> str:
    return step.__name__.rsplit(".", 1)[-1]


def target_label(database_url: str) -> str:
    # No user, password or query string: this line may end up in logs.
    url = make_url(database_url)
    return f"{url.host}:{url.port or 5432}/{url.database}"


def load(
    database_url: str,
    confirm: Callable[[], bool],
    out: Callable[[str], None] = print,
    steps: Sequence[ModuleType] = STEPS,
) -> None:
    out(f"Target database: {target_label(database_url)}")
    if not confirm():
        out("Nothing loaded.")
        return

    for step in steps:
        name = step_name(step)
        out(f"== {name}")
        try:
            step.main()
        # SystemExit is not an Exception: import_stays reports a busy Overpass with sys.exit(1).
        except (Exception, SystemExit) as exc:
            reason = exc.code if isinstance(exc, SystemExit) else exc
            out(
                f"Step {name} failed: {reason}. The steps after it did not run. "
                "Fix it and run load_data again: it is safe to repeat."
            )
            raise SystemExit(1) from exc
    out(f"Done: all {len(steps)} steps finished.")


def ask_to_continue() -> bool:
    try:
        answer = input("Load into this database? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the sample data into the configured database.")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args()
    load(settings.database_url, confirm=(lambda: True) if args.yes else ask_to_continue)


if __name__ == "__main__":
    main()
