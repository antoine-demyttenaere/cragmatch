---
name: write-resolution-plan
description: Turn a Ready ticket from tickets/ into a resolution plan (approach, one delivery with files and tests, acceptance-criteria coverage, risks), saved next to the ticket. Use after /qualify-ticket, when a ticket is Ready and before any code is written.
argument-hint: "[ticket file, e.g. tickets/001-max-approach-time.md]"
allowed-tools: Read Grep Glob
---

# Write a resolution plan

Act as the tech lead for CragMatch. Decide HOW the ticket gets built, so a
developer can follow the plan step by step. Write no code: the plan file is
the only file you write.

## Ticket
$ARGUMENTS

## Repository state
!`git log --oneline -5`
!`git status --short`

## Steps
1. Read the ticket. If no path was given, list `tickets/` and ask which one.
   If its status isn't "Ready", stop and repeat its open questions.
2. Check the ticket against the code: read every file it mentions and the
   code those files call. List any claim that turns out wrong (names,
   paths, behaviour). The plan follows the code, not the ticket.
3. Choose the approach. If there are two reasonable options, give each in
   one or two lines and say why you picked one.
4. For every step, name the existing code it reuses (see "Reuse before
   writing" in CLAUDE.md). Only add a new helper when nothing fits.
5. Plan the whole ticket as ONE delivery: one build, one review, one commit
   that leaves the tests green. Never split it into increments (the user
   wants each ticket done in one go). Order the work inside it: migration
   first, then backend, then frontend. Give the files and what changes in
   them, the tests (file::name, what they assert, which acceptance
   criterion), the expected test count, a manual check, and the commit
   message. If the ticket looks too big for one delivery, say so in your
   reply and suggest splitting the TICKET; don't split the plan yourself.
6. Map every acceptance criterion to at least one test or manual check.
   Call out any criterion left uncovered.
7. List the risks: migration downgrade, existing data, behaviour that must
   stay unchanged, external services and their rate limits.
8. Save the plan as `tickets/NNN-short-slug.plan.md` (same number and slug
   as the ticket), following [template.md](template.md).
9. Reply with the file path, the approach in two sentences, the expected
   test count, and anything in the ticket that was wrong.
