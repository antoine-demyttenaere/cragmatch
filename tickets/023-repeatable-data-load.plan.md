# Plan for 023: Stage 7, part 4: a data load that is safe to repeat

**Ticket:** `tickets/023-repeatable-data-load.md`
**Approach:** `seed` looks crags up by name and sectors by crag and name and only adds what is
missing; `seed_notes` sets notes only on the sample sectors (the crag and sector pairs in `seed.CRAGS`
that have an entry in `NOTES`) and leaves every other sector alone. A new `load_data` script prints the
target database as `host:port/name`, asks for confirmation (`--yes` skips the question), and then calls
the five existing scripts' `main()` in the README order. It stops at the first step that fails and
names it. Every step reports how many rows it added and how many were already there. It reads its
target from `settings.database_url`, the same property the engine, PGVector and Alembic use, so it
works before ticket 021 (with the five `CRAGMATCH_POSTGRES_*` variables) and after it (with 021's
single URL setting) without depending on 021.

**Alternatives considered:**
- *Unique constraints plus `ON CONFLICT` (a migration):* they would also stop the API from creating
  duplicates. But the ticket says no migration, the migration would fail on a dev database that
  already holds duplicates, and `POST /crags/` would change behaviour. Not this ticket.
- *A PowerShell or shell script that runs the five commands:* it can't be tested, it is tied to
  one platform, and it can't name the failing step cleanly. A Python module reuses each `main()`
  and is tested offline.
- *One subprocess per step:* it isolates the steps, but needs exit-code plumbing and gives tests
  nothing to replace. Running the steps in the same process is simpler, and the tests swap each
  module's `main`.
- *Notes keyed by sector name only (today's key):* a friend's sector called "Poble" at another
  crag would have its own note overwritten. Matching by crag and sector name, the same key `seed`
  uses, protects it. `NOTES` and `CRAGS` stay unchanged.
- *Print the target only, with no question:* the writes would start straight away, so the target
  could not really be checked first (AC 7). Asking, with `--yes` for runs that nobody watches
  (a one-off task in ticket 025), meets AC 7 and still allows a script to run it. An empty answer
  or end-of-input counts as "no".

## Ticket check
Checked against the code on 2026-10-14. `uv run pytest --collect-only -q` found **199 tests**. No
other test was run, because the test database is shared.
- **Correct:**
  - The five scripts are in `backend/app/scripts/`, in the README order.
  - `seed.py` adds every crag and sector on every run with no existence check, and the `# TODO`
    block is still there. Re-counted: **5 crags and 13 sectors** (3 + 3 + 2 + 3 + 2).
  - `seed_notes.py` sets `approach_notes = NOTES.get(s.name)` on every sector.
  - `approach_notes` is part of `SectorCreate` (`schemas/sector.py:20`, `POST /sectors/`).
  - `seed_stays` skips a curated stay with the same name and prints "N added, M already present".
  - `import_stays` updates OSM rows by `external_id` and caches in `backend/.cache/overpass/`.
  - `index_sectors_langchain` uses the stable ids `sector-{id}`, and PGVector's `add_embeddings`
    really upserts: it does `insert ... on_conflict_do_update`
    (`.venv/.../langchain_postgres/vectorstores.py:790-800`).
  - The vectors live only in `langchain_pg_*`.
- **Missing or wrong in the ticket, and what is true:**
  - **`seed.py` has no `main()`.** Its function is `seed()`. It opens its own session and prints
    nothing. The suggested "call each script's `main()`" therefore needs `seed` to get a `main()`.
  - **An existing test asserts the bug:**
    `tests/test_rag_loader.py::test_seed_notes_fills_notes_without_voyage` expects "Unknown wall"
    to lose its "Old note." (it asserts `is None`). Its assertion changes in this ticket.
  - **`import_stays` ends with `sys.exit(1)` when a crag failed.** That raises `SystemExit`, which is
    not an `Exception`, so `load_data` has to catch it explicitly to name the step (AC 8).
  - **The index step reports only "Indexed N sectors",** not added against already there (AC 2).
    It also indexes *every* sector in the database, friends' sectors included, not "13"
    (`SectorLoader` loads all of them; the "13 Documents" comment is out of date).
  - **Open question 1 can't happen today:** there is no update endpoint for sectors or crags
    (only `POST`), so a friend can't edit a listed sector's notes through the API. The default
    (set the listed notes as today, leave every other sector alone) is safe.
  - **AC 2, "stays the same":** that holds when Overpass gives the same answer, which it does from
    the week-long cache. If OpenStreetMap gains a place between two uncached runs, a re-run adds
    it. That is a new place, not a duplicate.
  - **AC 6:** `langchain_voyageai` batches up to 1000 texts per request (`batch_size = 1000`,
    `embeddings.py:57`), so one `add_documents` call is one Voyage request at today's size.
  - **Database target ("the database URL from ticket 021"):** this works before 021 as well.
    Environment variables beat `backend/.env` in pydantic-settings, so `$env:CRAGMATCH_POSTGRES_DB`
    (and `_HOST`, `_PORT`, ...) in one window points everything at another database. After 021,
    its single URL setting does the same. `load_data` never reads a setting of its own.

## Delivery
One build, one review, one commit for the whole ticket (no increments).

### 1. Seed and notes safe to repeat, an index that reports what it did, and one load command
**Files** (in build order: there is no migration; backend, then docs):
- `backend/app/scripts/seed.py`:
  - Add a module docstring in the style of the other scripts. It gives the run command and says
    why the script checks before inserting: the vector ids are `sector-{id}`, so duplicates would
    double the index too. Delete the `# TODO` block. `CRAGS` is unchanged.
  - `sample_sector_keys() -> set[tuple[str, str]]` returns the `(crag name, sector name)` pairs in
    `CRAGS`. It is the one definition of "a sample sector", shared with `seed_notes`.
  - `seed(db: Session) -> tuple[int, int]` returns the crags and sectors it added.
    - Each crag is found with `select(Crag).where(Crag.name == ...).order_by(Crag.id)`, taking the
      first. Order by id so that on a database that already holds duplicates, the oldest row wins
      every time.
    - A missing crag is added, then `db.flush()` gives it an id. A comment says why: `SessionLocal`
      has `autoflush=False`.
    - Each sector is found by `crag_id` and `name`, and added only if missing. Existing rows are
      never changed (AC 3).
    - One `db.commit()` at the end.
  - `main() -> None`: `with SessionLocal() as db`, it calls `seed(db)` and prints
    "Crags: N added, M already present. Sectors: N added, M already present." The totals come from
    `CRAGS`, with the same wording as `seed_stays`. `__main__` calls `main()`.
- `backend/app/scripts/seed_notes.py`:
  - `apply_notes(db: Session) -> tuple[int, int]` returns how many notes it set and how many were
    already up to date. It loads sectors with their crag and touches a sector only when
    `(crag.name, sector.name)` is in `sample_sector_keys()` and `sector.name` is in `NOTES`.
    Comment why: sectors made through the API keep their own notes (ticket 023, AC 4).
  - `main() -> None` wraps it and prints "Approach notes: N set, M already up to date; other
    sectors left as they are." The docstring keeps its order note and adds "safe to re-run".
    `NOTES` is unchanged.
- `backend/app/scripts/index_sectors_langchain.py`:
  - Add a short docstring: the run command, 1 Voyage request, safe to re-run (stable ids).
  - `index_sectors(docs: list[Document], store: VectorStore) -> tuple[int, int]` builds the ids
    `sector-{id}` and counts the ids that are already there with `store.get_by_ids(ids)` (a database
    read, no Voyage). It then calls `store.add_documents(docs, ids=ids)` once, which is the single
    Voyage request (comment that), and returns (added, already there).
  - `main()` keeps today's shape: it loads the docs with a session closed before the Voyage call,
    then `index_sectors(docs, get_vector_store())`, and prints "Index: N added, M already there
    (updated in place)". Drop the out-of-date "13 Documents" comment.
- `backend/app/scripts/load_data.py` (new):
  - The docstring says:
    - the command: `uv run python -m app.scripts.load_data [--yes]`;
    - the order and why: notes before the index (it embeds them), curated stays before the import
      (the import skips OSM copies of them);
    - only the index step calls Voyage, once (the free tier allows 3 a minute);
    - a re-run leaves the data as it is;
    - a busy Overpass makes it exit 1 at the end, and running it again finishes the job;
    - the target is whatever the database settings point at (README).
  - `STEPS = (seed, seed_notes, index_sectors_langchain, seed_stays, import_stays)` holds the
    modules, not their functions. A comment says why: `main` is looked up when the step runs, so
    tests can replace it.
  - `step_name(step: ModuleType) -> str` returns the last part of `step.__name__`.
  - `target_label(database_url: str) -> str` uses `make_url` (as `psycopg_conninfo()` does) and
    returns `host:port/database`, with port 5432 when the URL has none. It has no user, no password
    and no query string (AC 7).
  - `load(database_url: str, confirm: Callable[[], bool], out: Callable[[str], None] = print,
    steps: Sequence[ModuleType] = STEPS) -> None`:
    1. It prints "Target database: <label>" first.
    2. If `confirm()` is false, it prints "Nothing loaded." and returns.
    3. For each step, it prints "== <name>" and calls `step.main()`. On `Exception` or `SystemExit`
       it prints "Step <name> failed: <reason>. The steps after it did not run. Fix it and run
       load_data again: it is safe to repeat." and raises `SystemExit(1)`.
    4. At the end it prints "Done: all N steps finished."
    Comment why `SystemExit` is caught: `import_stays` reports a busy Overpass with `sys.exit(1)`.
  - `ask_to_continue() -> bool` calls `input("Load into this database? [y/N] ")` and is true only
    for `y`/`yes`. `EOFError` counts as no.
  - `main()` uses `argparse` with `--yes`, then
    `load(settings.database_url, confirm=(lambda: True) if args.yes else ask_to_continue)`.
- `backend/tests/test_rag_loader.py`: in `test_seed_notes_fills_notes_without_voyage`, the
  assertion for "Unknown wall" becomes `== "Old note."`, and the test is renamed
  `test_seed_notes_fills_listed_notes_and_keeps_others`. Its known sector "Poble" at "Margalef" is a
  sample pair, so the other assertion stays.
- `README.md`:
  - "Running locally", above the five seed lines: `uv run python -m app.scripts.load_data   # all
    five steps below, in order; safe to re-run`. The five commands still work one by one.
  - A short paragraph, **Loading into another database**:
    - the load uses the same database settings as the app. Set them in a new PowerShell window:
      before ticket 021, the five `CRAGMATCH_POSTGRES_*` variables; once 021 is delivered, its single
      database URL setting (use the name in `app/core/config.py`);
    - `load_data` prints `host:port/name` and asks before writing; `--yes` is for runs nobody
      watches;
    - **never run `uv run pytest` in that window**: `conftest.py` builds the test URL from the same
      settings;
    - afterwards, `Remove-Item Env:CRAGMATCH_POSTGRES_...` or close the window.
  - Project structure (DoD 3):
    - a new line, `load_data.py  Runs seed, seed_notes, index_sectors_langchain, seed_stays,
      import_stays in order; shows the target first; safe to re-run.`;
    - `seed.py` gains "skips what is already there";
    - `seed_notes.py` gains "only on the sample sectors".
    The README lists no individual test file today (only the two `conftest.py`), so the two new
    test files follow that convention.
- `CLAUDE.md` (**proposed only; the user decides, and it is not part of the developer's commit
  unless the user says so**): in Commands, change "Fresh DB: seed scripts in README ..." to
  "Fresh DB: `uv run python -m app.scripts.load_data` (README "Running locally"; safe to re-run,
  1 Voyage request)".

**Reuses:**
- every script's `main()` (seed and index gain one small, testable function each);
- `seed_stays`' "skip if present" pattern and its output wording;
- `SectorLoader` and the stable-id upsert of PGVector;
- `get_vector_store()`;
- `settings.database_url` (works before and after 021);
- `make_url` as in `agent/checkpointer.py::psycopg_conninfo()`;
- the `db_session` and `client` fixtures, `monkeypatch`;
- the `FakePGVector`-style fakes in `tests/test_rag_vectorstore.py`.

No new dependency.

**Tests:**

*`backend/tests/test_seed.py` (new; `db_session`; Voyage is never called)*
- `test_seed_loads_every_crag_and_sector`: on an empty database, `seed(db_session)` returns
  `(5, 13)`. The database holds 5 crags and 13 sectors, and Siurana has exactly Can Marges,
  Siuranella and El Pati (AC 1).
- `test_seed_twice_adds_nothing`: the second `seed()` returns `(0, 0)`. The counts stay 5 and 13,
  and the set of sector ids is unchanged (AC 2).
- `test_seed_fills_in_a_partial_load`: start with crag Siurana holding Can Marges and a friend's
  sector "My Wall". `seed()` returns `(4, 12)`. There is still one Siurana, with the same id, and it
  has 4 sectors. Can Marges keeps its id, and "My Wall" is still there (AC 3).
- `test_apply_notes_sets_sample_notes_and_keeps_api_sectors_notes`: after `seed()`, create through
  `client`:
  - `POST /sectors/` "My Wall" at Siurana with the notes "Our own beta.";
  - `POST /crags/` "Elsewhere", then `POST /sectors/` "Poble" there with "Not Margalef's.".
  `apply_notes(db_session)` returns `(13, 0)`. Can Marges' notes equal `NOTES["Can Marges"]`. Both
  API sectors keep their own notes (AC 4).
- `test_apply_notes_twice_changes_nothing`: the second `apply_notes()` returns `(0, 13)`, and every
  sample sector's notes are unchanged (AC 2).
- `test_index_sectors_upserts_by_stable_ids_in_one_call`: after `seed()`, the docs come from
  `SectorLoader(db_session).load()`. A fake store records `add_documents` calls and remembers ids,
  and its `get_by_ids` returns the remembered ones.
  - The first `index_sectors()` returns `(13, 0)`, the second `(0, 13)`.
  - Each run made exactly one `add_documents` call, with the ids `sector-{id}` of every sector.
  - The fake holds 13 distinct ids, so the index count stays the same (AC 2, AC 6).

*`backend/tests/test_load_data.py` (new; no database; each step's `main` is replaced with
`monkeypatch.setattr(<module>, "main", recorder)`)*
- `test_load_data_runs_the_steps_in_the_documented_order`: `load(..., confirm=lambda: True)` calls
  `seed, seed_notes, index_sectors_langchain, seed_stays, import_stays` in that order, each once, so
  there is one index call and therefore one Voyage request. The output ends with "Done" (AC 5, 6, 1).
- `test_load_data_stops_at_the_first_failing_step`: `seed_notes.main` raises `RuntimeError`.
  `load()` raises `SystemExit` with code 1, and the calls are only `seed, seed_notes`, so the index
  never runs without the notes. An output line names `seed_notes` (AC 5).
- `test_load_data_reports_a_failed_stays_import_at_the_end`: `import_stays.main` raises
  `SystemExit(1)`. All five steps were called, `load()` exits with code 1, and an output line names
  `import_stays` and says it is safe to run again (AC 8).
- `test_load_data_shows_the_target_and_writes_nothing_unconfirmed`, with the URL
  `postgresql+psycopg://loader:s3cret@db.example:6543/app?sslmode=require`:
  - when `confirm` is called, the output already holds "Target database: db.example:6543/app";
  - `confirm` returns False, so no step is called, and "Nothing loaded." is printed;
  - neither "loader" nor "s3cret" appears anywhere in the output (AC 7).
- `test_target_label_hides_user_and_password`: the URL above gives `db.example:6543/app`, and
  `postgresql+psycopg://u:p@localhost/cragmatch` gives `localhost:5432/cragmatch` (AC 7).

**Expected suite:**
- **199 today.**
- **251 before this ticket:** 017 +0, 018 +0, 019 +3, 020 +0, 021 +17, 022 +32.
- **This ticket adds 11 tests:** 6 in `test_seed.py` and 5 in `test_load_data.py`. One existing test
  is changed and renamed, which adds nothing to the count.
- **So 262 passed (251 + 11), that is, whatever lands before plus 11.**
- `uv run ruff check .`: clean.
- No frontend change, so no `npm` check.

**Check by hand** (the user, on a scratch database next to the dev one, in `backend/`, in a new
PowerShell window; it costs 2 Voyage requests, so wait a minute before any vibe search):
1. Create the scratch database:
   `docker compose exec db sh -c 'createdb -U "${POSTGRES_USER:-postgres}" cragmatch_load_check'`
   (or `createdb` with your database user). Then:
   - `$env:CRAGMATCH_POSTGRES_DB = "cragmatch_load_check"`;
   - `uv run alembic upgrade head`.
2. AC 7, 1, 5: run `uv run python -m app.scripts.load_data`.
   - The first line shows `localhost:5433/cragmatch_load_check` and no user or password.
   - Answer `n`: "Nothing loaded." Run it again and answer `y`.
   - The steps run in order: seed, seed_notes, index, seed_stays, import_stays.
3. Count the rows in `cragmatch_load_check`, with `docker compose exec db psql` and your user:
   - `crags` 5;
   - `sectors` 13, with 13 `approach_notes` not null;
   - `langchain_pg_embedding` 13 for collection `sectors`;
   - `stays` more than 5.
4. AC 2: run `uv run python -m app.scripts.load_data --yes`. It asks nothing, and every step reports
   "0 added", with the index "0 added, 13 already there". The counts are the same as in check 3.
5. AC 3: delete one sector (`delete from sectors where name = 'Serrat'`) and its index row, then
   run `uv run python -m app.scripts.seed`. It says "Sectors: 1 added, 12 already present", and
   the other sector ids are unchanged.
6. AC 9: `uv run python -m app.scripts.seed_notes` and `uv run python -m app.scripts.seed_stays`
   on their own both print their counts and add nothing.
7. Clean up:
   - `Remove-Item Env:CRAGMATCH_POSTGRES_DB`, and close the window;
   - drop `cragmatch_load_check` with `dropdb`.
   Do not run pytest in that window before the variable is removed.

**Commit:** `Ticket 023: seed and seed_notes safe to re-run (crags by name, sectors by crag and name, notes only on the sample sectors), the index step reports added and already there, load_data runs the five steps in order after showing and confirming the target database and stops at the first failing step; README documents it and how to point it at another database`

## Acceptance criteria coverage
| AC | Covered by |
|---|---|
| 1 | `test_seed.py::test_seed_loads_every_crag_and_sector`; `test_load_data.py::test_load_data_runs_the_steps_in_the_documented_order`; manual checks 2 and 3 |
| 2 | `test_seed.py::test_seed_twice_adds_nothing`, `::test_apply_notes_twice_changes_nothing`, `::test_index_sectors_upserts_by_stable_ids_in_one_call`; manual check 4 (same counts, "0 added"). The stays half rests on the existing `seed_stays` and `import_stays` logic (unchanged) and the manual check |
| 3 | `test_seed.py::test_seed_fills_in_a_partial_load`; manual check 5 |
| 4 | `test_seed.py::test_apply_notes_sets_sample_notes_and_keeps_api_sectors_notes`; `test_rag_loader.py::test_seed_notes_fills_listed_notes_and_keeps_others` (changed) |
| 5 | `test_load_data.py::test_load_data_runs_the_steps_in_the_documented_order`, `::test_load_data_stops_at_the_first_failing_step` |
| 6 | `test_load_data.py::test_load_data_runs_the_steps_in_the_documented_order` (the index runs once); `test_seed.py::test_index_sectors_upserts_by_stable_ids_in_one_call` (one `add_documents` call); Voyage's 1000-text batch (Ticket check) |
| 7 | `test_load_data.py::test_load_data_shows_the_target_and_writes_nothing_unconfirmed`, `::test_target_label_hides_user_and_password`; manual check 2 |
| 8 | `test_load_data.py::test_load_data_reports_a_failed_stays_import_at_the_end`; `import_stays`' own retry-from-cache behaviour (unchanged) |
| 9 | manual check 6; `test_rag_loader.py::test_seed_notes_fills_listed_notes_and_keeps_others` runs `seed_notes.main()` |
| 10 | Every new test runs on `cragmatch_test` or without a database; Voyage, Overpass and PGVector are never reached (each step's `main` replaced, the store faked) |

Every criterion is covered.

## Risks
- **Migration:** none, so there is no downgrade to worry about.
- **Existing data:**
  - A dev database that is already duplicated stays duplicated (cleaning it up is out of scope).
    `seed` then uses the oldest crag of each name and adds nothing more.
  - A crag a friend created with a sample name (for example "Siurana") is reused, and the sample
    sectors are added to it. Same name, same crag: that is the intended reading.
- **Behaviour that changes on purpose:** `seed_notes` no longer clears the notes of sectors outside
  the sample list. The existing test that asserted the clearing is updated.
- **Behaviour that must stay unchanged:**
  - every `python -m app.scripts.<name>` command, in the README order;
  - `CRAGS`, `NOTES` and `build_text()`, so the vectors don't need a re-index;
  - `import_stays`' `--no-cache` flag (`load_data` uses the cache, as the default does).
- **Voyage, 3 requests a minute:**
  - one load makes 1 request, and a re-run one more;
  - more than 1000 sectors, or Voyage's per-batch token limit, would split the index into more
    requests, which is far from today's 13;
  - the README and the docstring say to wait a minute before a vibe search.
- **Overpass is busy:** `import_stays` runs last, so the earlier steps are already committed. The
  load exits 1 and names the step, and a re-run fills in from the cache.
- **Pointed at the wrong database:** the target is printed first, and nothing runs until the
  question is answered. `--yes` skips that, so it is only for runs that nobody watches.
  - pytest follows the same settings, so the README warns against running it in that window.
  - A prompt in a non-interactive run gets end-of-input, which counts as "no", so nothing is
    written.
- **Steps run in the same process:**
  - an exception or `sys.exit` inside a step is caught and named;
  - Ctrl+C stops at once;
  - each step commits once at its end, so an interrupted step leaves its own rows out, and a re-run
    is safe.
- **Shared test database:** the new tests never create the `langchain_pg_*` tables (the store is
  faked) and leave nothing behind, because `db_session` empties our tables.
- **Ticket 021's setting name isn't known yet:** the code doesn't depend on it. Only the README
  sentence names it, and the developer reads the name from `config.py` at build time.

## Out of scope (copied from the ticket)
- Running the load on AWS: ticket 025 (how a laptop or a task reaches the cloud database is decided
  there).
- A dump and restore of the local database: the earlier plan found it brings PostGIS's own schemas
  and test groups along, and extension versions may differ. The scripts are the supported way.
- Cleaning up data already duplicated in someone's dev database: the user's choice, by hand.
- Changing what the notes or sectors say.
