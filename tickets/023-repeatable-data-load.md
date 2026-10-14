# 023: Stage 7, part 4: a data load that is safe to repeat

**Status:** Ready
**Size:** M (a few scripts and tests, no migration)
**Mode:** delivery. Built with `/deliver-increment` from a resolution plan: the developer agent writes the code and tests, the tech lead reviews, the user commits.
**Raw request:** "7 cloud deployment (to be reworked)." (ticket 013, split on 2026-10-13; this ticket was carved out of the old ticket 020 on 2026-10-14, so that the AWS tickets can load data without surprises.)
**Part of:** Stage 7 in execution order: 018 CI, 019 and 020 trip planner screen, 021 production config and container, 022 daily spending cap, 023 (this), 024 to 026 deploy on AWS.
**Depends on:** nothing new. Can be done any time before ticket 025.

## User story
As the owner of CragMatch, I want to load the sample data (crags, sectors, approach notes, the
vector index and stays) into a fresh database with one documented command, and be able to run it
again without damage, so that I can fill the cloud database from my laptop without worrying about
duplicates or lost notes.

## What exists today
(Checked against the code on 2026-10-14.)
- Data loading is manual (README "Running locally"), in this order: `seed`, `seed_notes`,
  `index_sectors_langchain`, `seed_stays`, `import_stays`. The scripts are in `backend/app/scripts/`.
- **`seed.py` is not repeatable.** It adds every crag and sector in its list on every run
  (`db.add(...)`), with no existence check, and a leftover `# TODO` comment block is still in it.
  A second run silently duplicates the crags and sectors (the earlier plan counted 5 crags and 13
  sectors; not re-counted today). Because the vector ids are `sector-{id}`, the duplicates would
  also double the vector index.
- **`seed_notes.py` overwrites notes.** For every sector it sets `approach_notes` to the value in its
  `NOTES` list, or to nothing when the sector is not in the list (`NOTES.get(s.name)`). A second run
  therefore erases the notes of any sector a friend created through the API (`approach_notes` is part
  of creating a sector, per the earlier plan).
- `seed_stays` only adds a stay it does not already have; `import_stays` updates by external id; and
  `index_sectors_langchain` upserts by stable ids (earlier plan, from the scripts; not re-checked).
  So these three are already safe to repeat.
- `index_sectors_langchain` makes one Voyage request and needs the notes first; the Voyage free tier
  allows 3 requests a minute (CLAUDE.md). `import_stays` calls the public Overpass API (often busy)
  and keeps a cache in `backend/.cache/overpass/`.
- The vector index lives in LangChain's tables (`langchain_pg_*`, collection `sectors`), not in
  `sectors`.
- There is no single command to run all five steps.

## Acceptance criteria
1. Given an empty database with the migrations applied, when the documented load runs, then it ends
   with the same kinds of data as local: crags, sectors, approach notes, the vector index and stays.
2. Given the load has run, when it runs a second time, then nothing is duplicated and the counts of
   crags, sectors, index entries and stays are the same. The output says how many rows were added
   and how many were already there.
3. Given a partly loaded database (some crags or sectors missing), when the load runs, then it fills
   in the missing ones and keeps the existing rows (and their ids).
4. Given a sector created through the API with its own approach notes, when the notes step runs, then
   that sector keeps its notes, and the listed sectors get theirs.
5. Given the documented order, then notes come before the index, and curated stays before the import.
   Given a step fails, then the load stops there and says which step, and does not run the index
   without the notes.
6. Given the load, then it makes at most one Voyage request, so it stays within 3 a minute.
7. Given the load is pointed at a database, then it first prints which database (host, port, name)
   without the user or password, so the right target can be checked before anything is written.
8. Edge case: given the stays import cannot reach Overpass, then the load reports it and exits with a
   failure at the end, and running it again finishes the job.
9. Given the existing commands (`uv run python -m app.scripts.seed` and the others), then they still
   work on their own, in the README order.
10. Given the test suite, then it runs offline as today, and the new behaviour is covered by tests on
    the test database.

## Scope
**In:**
- Making `seed` and `seed_notes` safe to repeat.
- One command that runs the five steps in order and prints its target.
- Tests for both fixes and for the order and stop behaviour.
- README: the new command, and a note that the data load can be pointed at another database.

**Out:**
- Running the load on AWS: ticket 025 (how a laptop or a task reaches the cloud database is decided
  there).
- A dump and restore of the local database: the earlier plan found it brings PostGIS's own schemas
  and test groups along, and extension versions may differ. The scripts are the supported way.
- Cleaning up data already duplicated in someone's dev database: the user's choice, by hand.
- Changing what the notes or sectors say.

## Open questions
- [non-blocking] Should a re-run of `seed_notes` fill empty notes on listed sectors only, or also
  overwrite notes that a friend edited on a listed sector? (suggested default: set the listed notes
  as today for listed sectors, and leave every other sector alone; that is the minimum that
  protects friends' own sectors.)
- [non-blocking] Should `import_stays` be part of the single command, since it can fail on a busy
  Overpass? (suggested default: yes, last, so earlier steps are not lost when it fails, and a re-run
  is safe.)

## Notes for the tech lead
- This ticket was carved out of the old Render deploy ticket because the bug is platform
  independent. The earlier plan's design is a suggestion: look up crags by name and sectors by
  crag and name; a `load_data` script listing the five script modules and calling each one's
  `main()`; a helper that prints the target without the password. You decide.
- Scripts run on the laptop against the cloud database by setting the database URL from ticket 021.
  The laptop's pytest follows the same setting, so the README should warn not to run tests in a
  window that points at the cloud.
- Tests belong on the test database with `db_session`; the load-order test can replace each step with
  a recorder so no network or Voyage call happens (CLAUDE.md: tests never touch the network).
- Code standards: small functions, comments explain why. Keep `CRAGS` and `NOTES` unchanged.
- Definition of done: README "Running locally" line and project structure for the new files; tests
  green.
