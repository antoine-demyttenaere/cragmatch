# Plan for NNN: <ticket title>

**Ticket:** `tickets/NNN-short-slug.md`
**Approach:** <two or three sentences>
**Alternatives considered:**
- <option>: <why not>

## Ticket check
- <claims verified against the code; anything that was wrong, and what is true>

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. <goal of the whole ticket>
**Files** (in build order: migration, backend, frontend):
- `path/to/file.py`: <what changes>

**Reuses:** <existing functions and patterns>

**Tests:**
- `tests/test_x.py::test_name`: <what it asserts> (AC 3)

**Expected suite:** <N> passed

**Check by hand:** <command, request or screen to look at>

**Commit:** `<message, no double quotes>`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `tests/test_groups_api.py::test_...` |

## Risks
- <risk>: <mitigation>

## Out of scope (copied from the ticket)
- <item>
