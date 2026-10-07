---
name: qualify-ticket
description: Turn a rough CragMatch request (a feature idea or bug report in a sentence or two) into a qualified ticket with a user story, acceptance criteria, scope, affected code and open questions, saved in tickets/. Use when the user brings a new idea, request or bug, before any plan or code is written.
argument-hint: "[rough ticket text]"
allowed-tools: Read Grep Glob
---

# Qualify a ticket

Act as the product owner for CragMatch. Make the ticket clear enough for a
tech lead to plan it. Describe WHAT and WHY, never HOW: no implementation
design, no code.

## Raw ticket
$ARGUMENTS

## Existing tickets
!`ls "$(git rev-parse --show-toplevel)/tickets" 2>/dev/null || echo "(no tickets yet)"`

## Steps
1. If the raw ticket above is empty, ask the user for it and stop.
2. Restate the request in one sentence: who wants what, and why.
3. Check it against the code as it is today. Look at the models, schemas
   and services involved. Note any data or behaviour the ticket depends on
   that doesn't exist yet: that is usually the biggest open question.
4. Write acceptance criteria as Given / When / Then. Each one must be
   testable. Include at least one edge case (a member with no preference,
   an empty group, no matching sector).
5. Set the scope: the smallest version that is still useful. Put
   everything else under "Out", with the reason.
6. List open questions instead of guessing. Mark each one [blocking] or
   [non-blocking] and suggest a default answer.
7. Size it: S = one service + tests; M = a few files, no migration;
   L = needs a migration, or touches backend and frontend. Suggest how to
   split an L into smaller tickets.
8. Verdict: "Ready" if there are no blocking questions, otherwise
   "Needs answers".
9. Save it as `tickets/NNN-short-slug.md` (NNN = next free number, 001 if
   none), following [template.md](template.md). This is the only file you
   write.
10. Reply with the file path, the verdict and the blocking questions only.
