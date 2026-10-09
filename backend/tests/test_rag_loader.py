"""SectorLoader, build_text() and the seed_notes script. No network: Voyage is never called."""

from types import SimpleNamespace

from app.models import Crag, Sector
from app.models.sector import ClimbingStyle
from app.rag.loader import SectorLoader, build_text
from app.scripts import seed_notes

POBLE_TEXT = "Poble at Margalef in Priorat. Style: sport. Grades: 5+ to 7b. Approach: Easy-going crag."


def add_crag(db_session) -> Crag:
    crag = Crag(name="Margalef", region="Priorat", latitude=41.29, longitude=0.76)
    db_session.add(crag)
    db_session.commit()
    return crag


def add_sector(db_session, crag: Crag, name: str, notes: str | None = None) -> Sector:
    sector = Sector(
        name=name,
        style=ClimbingStyle.SPORT,
        grade_min="5+",
        grade_max="7b",
        crag_id=crag.id,
        approach_notes=notes,
    )
    db_session.add(sector)
    db_session.commit()
    return sector


def test_build_text_format_is_unchanged():
    sector = SimpleNamespace(
        name="Poble",
        crag=SimpleNamespace(name="Margalef", region="Priorat"),
        style=ClimbingStyle.SPORT,
        grade_min="5+",
        grade_max="7b",
        approach_notes="Easy-going crag.",
    )

    assert build_text(sector) == POBLE_TEXT


def test_sector_loader_builds_documents_from_build_text(db_session):
    crag = add_crag(db_session)
    sector = add_sector(db_session, crag, "Poble", notes="Easy-going crag.")

    docs = SectorLoader(db_session).load()

    assert len(docs) == 1
    assert docs[0].page_content == POBLE_TEXT
    assert docs[0].metadata == {
        "sector_id": sector.id,
        "name": "Poble",
        "crag": "Margalef",
        "style": "sport",
        "grade_min": "5+",
        "grade_max": "7b",
    }


def test_seed_notes_fills_notes_without_voyage(db_session, monkeypatch):
    crag = add_crag(db_session)
    known = add_sector(db_session, crag, "Poble")
    unknown = add_sector(db_session, crag, "Unknown wall", notes="Old note.")
    known_id, unknown_id = known.id, unknown.id
    monkeypatch.setattr(seed_notes, "SessionLocal", lambda: db_session)

    seed_notes.main()

    # main() closes the session, so read the rows again.
    assert db_session.get(Sector, known_id).approach_notes == seed_notes.NOTES["Poble"]
    assert db_session.get(Sector, unknown_id).approach_notes is None
