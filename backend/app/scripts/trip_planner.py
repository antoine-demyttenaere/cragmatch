"""Run the Stage 6 trip planner on a group, in the terminal.

    uv run python -m app.scripts.trip_planner <share_code> [--checkin YYYY-MM-DD] [--nights N] [--guests N]

It prints one line per node as the graph runs, asks the group to approve the
proposed sector (y/n, and why not on a no), then prints the final plan or the
reason there is none.

The paused run lives in memory only (InMemorySaver): Ctrl+C at the prompt loses it.
"""

import argparse
import sys
from collections.abc import Callable
from datetime import date
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.agent.graph import build_trip_planner
from app.agent.state import Approval, PlannerContext, initial_state
from app.core.database import SessionLocal


def describe_update(node: str, update: dict | None) -> str:
    if not update:
        return f"{node}: (no change)"
    return f"{node}: {', '.join(update)}"


def run_planner(
    db: Session,
    share_code: str,
    ask: Callable[[dict], Approval],
    out: Callable[[str], None] = print,
    checkin: date | None = None,
    nights: int = 2,
    guests: int | None = None,
) -> dict:
    graph = build_trip_planner(InMemorySaver())
    # One thread id per run, and the context is passed on every resume: the
    # checkpointer doesn't store it (see plan 010).
    config = {"configurable": {"thread_id": str(uuid4())}}
    context = PlannerContext(db=db)
    next_input = initial_state(share_code, checkin, nights, guests)

    while True:
        question = None
        for chunk in graph.stream(next_input, config, context=context, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__":
                    question = update[0].value
                elif node != "approve_sector":
                    # approve_sector's own update is skipped: the decision line below
                    # reports it, with the reason.
                    out(describe_update(node, update))
        if question is None:
            break

        decision = ask(question)
        verdict = "approved" if decision.approved else f"rejected: {decision.reason or ''}"
        out(f"approve_sector: {verdict}")
        next_input = Command(resume=decision.model_dump())

    return graph.get_state(config).values


def ask_in_terminal(question: dict) -> Approval:
    sector = question["sector"]
    walk_in = sector["approach_minutes"]
    print(
        f"{sector['sector_name']}, {sector['crag_name']}, "
        f"{sector['grade_min']}-{sector['grade_max']}, {sector['style']}, "
        f"{sector['distance_km']} km, "
        f"walk-in {f'{walk_in} min' if walk_in is not None else 'unknown'}"
    )
    answer = input("Approve this sector? [y/n] ").strip().lower()
    if answer in ("y", "yes"):
        return Approval(approved=True)
    return Approval(approved=False, reason=input("Why not? ").strip() or None)


def format_plan(state: dict) -> str:
    plan = state.get("plan")
    if not plan:
        return state.get("message") or "No plan."

    sector = plan["sector"]
    lines = [
        f"Sector: {sector['sector_name']} ({sector['crag_name']})",
        f"{plan['checkin']} to {plan['checkout']}, {plan['guests']} guests",
        "Stays:",
    ]
    for item in plan["stays"][:5]:
        stay = item["stay"]
        lines.append(f"  {stay['name']}, {stay['type']}, {item['distance_km']} km")
    lines.append(f"Airbnb: {plan['links']['airbnb']}")
    lines.append(f"Booking: {plan['links']['booking']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the trip planner on a group.")
    parser.add_argument("share_code")
    parser.add_argument("--checkin", type=date.fromisoformat, help="YYYY-MM-DD, default next Saturday")
    parser.add_argument("--nights", type=int, default=2)
    parser.add_argument("--guests", type=int)
    args = parser.parse_args()

    # Same rules as the group stays endpoint.
    if args.checkin is not None and args.checkin < date.today():
        sys.exit("checkin can't be in the past")
    if not 1 <= args.nights <= 30:
        sys.exit("nights must be between 1 and 30")
    if args.guests is not None and not 1 <= args.guests <= 30:
        sys.exit("guests must be between 1 and 30")

    with SessionLocal() as db:
        try:
            state = run_planner(
                db,
                args.share_code,
                ask=ask_in_terminal,
                checkin=args.checkin,
                nights=args.nights,
                guests=args.guests,
            )
        except ValueError as error:
            print(error)
            sys.exit(1)
        print(format_plan(state))


if __name__ == "__main__":
    main()
