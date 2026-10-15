"""load_data: order, stopping, and the target line. No database, no network."""

import pytest

from app.scripts import import_stays, index_sectors_langchain, load_data, seed, seed_notes, seed_stays

URL = "postgresql+psycopg://loader:s3cret@db.example:6543/app?sslmode=require"
STEP_MODULES = [seed, seed_notes, index_sectors_langchain, seed_stays, import_stays]


@pytest.fixture()
def calls(monkeypatch) -> list[str]:
    recorded: list[str] = []
    for module in STEP_MODULES:
        name = module.__name__.rsplit(".", 1)[-1]
        monkeypatch.setattr(module, "main", lambda name=name: recorded.append(name))
    return recorded


def test_load_data_runs_the_steps_in_the_documented_order(calls):
    output: list[str] = []

    load_data.load(URL, confirm=lambda: True, out=output.append)

    assert calls == ["seed", "seed_notes", "index_sectors_langchain", "seed_stays", "import_stays"]
    assert output[-1].startswith("Done")


def test_load_data_stops_at_the_first_failing_step(calls, monkeypatch):
    def fail() -> None:
        calls.append("seed_notes")
        raise RuntimeError("boom")

    monkeypatch.setattr(seed_notes, "main", fail)
    output: list[str] = []

    with pytest.raises(SystemExit) as exit_info:
        load_data.load(URL, confirm=lambda: True, out=output.append)

    assert exit_info.value.code == 1
    assert calls == ["seed", "seed_notes"]
    assert any("seed_notes" in line and "failed" in line for line in output)


def test_load_data_reports_a_failed_stays_import_at_the_end(calls, monkeypatch):
    def busy() -> None:
        calls.append("import_stays")
        raise SystemExit(1)

    monkeypatch.setattr(import_stays, "main", busy)
    output: list[str] = []

    with pytest.raises(SystemExit) as exit_info:
        load_data.load(URL, confirm=lambda: True, out=output.append)

    assert exit_info.value.code == 1
    assert len(calls) == 5
    assert any("import_stays" in line and "safe to repeat" in line for line in output)


def test_load_data_shows_the_target_and_writes_nothing_unconfirmed(calls):
    output: list[str] = []
    seen_when_asked: list[str] = []

    def decline() -> bool:
        seen_when_asked.extend(output)
        return False

    load_data.load(URL, confirm=decline, out=output.append)

    assert "Target database: db.example:6543/app" in seen_when_asked
    assert calls == []
    assert "Nothing loaded." in output
    text = "\n".join(output)
    assert "loader" not in text
    assert "s3cret" not in text


def test_target_label_hides_user_and_password():
    assert load_data.target_label(URL) == "db.example:6543/app"
    assert load_data.target_label("postgresql+psycopg://u:p@localhost/cragmatch") == "localhost:5432/cragmatch"
