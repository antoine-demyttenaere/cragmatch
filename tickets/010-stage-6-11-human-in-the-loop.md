# 010: Stage 6.11, human-in-the-loop: pause for the group's approval

**Status:** Ready
**Size:** M
**Mode:** guide. The user writes the code (see CLAUDE.local.md). This is a step brief, not for `/deliver-increment`.
**Raw request:** "Add an interrupt before the 'propose a plan' node, so the graph pauses and waits for the group to approve the chosen sector before it looks up stays and finalizes anything. Run it, see the pause happen, resume it manually, and have Claude Code explain what LangGraph is actually doing during that pause (this is usually the most confusing part, worth real time)."

## User story
As a group, I want the planner to show us the sector it picked and wait for our approval
before it looks for stays, so that nothing is planned around a sector we don't want.

## What exists today
- The graph from ticket 009: merge → (conflicts | search → stays).
- No checkpointer. A graph can only pause and resume if its state is saved somewhere.

## Acceptance criteria
1. Given the graph is compiled with a checkpointer, when it runs for a group, then it stops
   after the sector is picked and before stays are looked up, and the run returns the
   proposed sector.
2. Given the paused run, when its saved state is read (by the same thread id), then the
   chosen sector is there and no stays are.
3. Given the group approves, when the run is resumed with the same thread id, then it
   continues from the pause (merge and search are not run again), finds stays, and
   produces a final plan.
4. Given the group rejects with a reason, when the run is resumed, then it goes back to
   pick another sector or ends with no plan (whichever the user chooses in "Open
   questions"). It never looks up stays for the rejected sector.
5. Given the explanation, then it covers: what the checkpointer stores and when, what a
   thread id is, why the state must be serializable, and that "paused" means the process
   simply returned and nothing keeps running.

## Scope
**In:** an in-memory checkpointer, the interrupt, resume with approve or reject, and a
"propose plan" node that builds the final plan (sector, stays, booking links for the
trip dates).
**Out:**
- A persistent checkpointer (Postgres): a Stage 7 question.
- An API or UI to approve: ticket 011 decides how a group runs it.

## Open questions
- [non-blocking] On rejection, retry with the next candidate or end? (suggested default:
  next candidate, at most 3, then end with "no plan".)

## Notes for the tech lead
- Check against the INSTALLED `langgraph` version: the in-memory checkpointer class and
  module, and whether to use `interrupt()` inside a node (with `Command(resume=...)`) or
  `interrupt_before` at compile time. Prefer the one the installed docs recommend, and
  explain the difference.
- Booking links reuse `airbnb_url()` / `booking_url()` and `next_saturday()` from
  `services/stays.py`.
