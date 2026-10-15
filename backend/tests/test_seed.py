"""seed, seed_notes.apply_notes and index_sectors: safe to repeat. Voyage is never called."""

from sqlalchemy import func, select

from app.models import ClimbingStyle, Crag, Sector
from app.rag.loader import SectorLoader
from app.scripts.index_sectors_langchain import index_sectors
from app.scripts.seed import seed
from app.scripts.seed_notes import NOTES, apply_notes


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def sector_ids(db_session) -> set[int]:
    return set(db_session.scalars(select(Sector.id)))


def notes_of(db_session, name: str) -> str | None:
    return db_session.scalars(select(Sector.approach_notes).where(Sector.name == name)).one()


class FakeStore:
    """Remembers ids like an upserting vector store, and counts add_documents calls."""

    def __init__(self) -> None:
        self.ids: set[str] = set()
        self.add_calls: list[list[str]] = []

    def get_by_ids(self, ids):
        return [id_ for id_ in ids if id_ in self.ids]

    def add_documents(self, docs, ids):
        self.add_calls.append(list(ids))
        self.ids.update(ids)


def test_seed_loads_every_crag_and_sector(db_session):
    assert seed(db_session) == (5, 13)

    assert count(db_session, Crag) == 5
    assert count(db_session, Sector) == 13
    siurana = db_session.scalars(select(Crag).where(Crag.name == "Siurana")).one()
    assert {s.name for s in siurana.sectors} == {"Can Marges", "Siuranella", "El Pati"}


def test_seed_twice_adds_nothing(db_session):
    seed(db_session)
    ids_before = sector_ids(db_session)

    assert seed(db_session) == (0, 0)

    assert count(db_session, Crag) == 5
    assert count(db_session, Sector) == 13
    assert sector_ids(db_session) == ids_before


def test_seed_fills_in_a_partial_load(db_session):
    crag = Crag(name="Siurana", region="Priorat", latitude=41.2436, longitude=0.9186)
    db_session.add(crag)
    db_session.flush()
    can_marges = Sector(
        name="Can Marges", style=ClimbingStyle.SPORT, grade_min="6a", grade_max="8a", crag_id=crag.id
    )
    my_wall = Sector(name="My Wall", style=ClimbingStyle.SPORT, grade_min="6a", grade_max="7a", crag_id=crag.id)
    db_session.add_all([can_marges, my_wall])
    db_session.commit()
    crag_id, can_marges_id, my_wall_id = crag.id, can_marges.id, my_wall.id

    assert seed(db_session) == (4, 12)

    siurana = db_session.scalars(select(Crag).where(Crag.name == "Siurana")).one()
    assert siurana.id == crag_id
    assert len(siurana.sectors) == 4
    assert db_session.scalars(select(Sector.id).where(Sector.name == "Can Marges")).one() == can_marges_id
    assert db_session.get(Sector, my_wall_id) is not None


def test_apply_notes_sets_sample_notes_and_keeps_api_sectors_notes(db_session, client):
    seed(db_session)
    siurana_id = db_session.scalars(select(Crag.id).where(Crag.name == "Siurana")).one()
    client.post(
        "/sectors/",
        json={
            "name": "My Wall", "style": "sport", "grade_min": "6a", "grade_max": "7a",
            "crag_id": siurana_id, "approach_notes": "Our own beta.",
        },
    )
    elsewhere = client.post(
        "/crags/", json={"name": "Elsewhere", "region": "Nowhere", "latitude": 41.5, "longitude": 1.5}
    ).json()["id"]
    client.post(
        "/sectors/",
        json={
            "name": "Poble", "style": "sport", "grade_min": "6a", "grade_max": "7a",
            "crag_id": elsewhere, "approach_notes": "Not Margalef's.",
        },
    )

    assert apply_notes(db_session) == (13, 0)

    assert notes_of(db_session, "Can Marges") == NOTES["Can Marges"]
    assert notes_of(db_session, "My Wall") == "Our own beta."
    elsewhere_poble = db_session.scalars(select(Sector).where(Sector.crag_id == elsewhere)).one()
    assert elsewhere_poble.approach_notes == "Not Margalef's."


def test_apply_notes_twice_changes_nothing(db_session):
    seed(db_session)
    apply_notes(db_session)
    notes_before = {s.name: s.approach_notes for s in db_session.scalars(select(Sector))}

    assert apply_notes(db_session) == (0, 13)

    notes_after = {s.name: s.approach_notes for s in db_session.scalars(select(Sector))}
    assert notes_after == notes_before


def test_index_sectors_upserts_by_stable_ids_in_one_call(db_session):
    seed(db_session)
    docs = SectorLoader(db_session).load()
    expected_ids = sorted(f"sector-{sector_id}" for sector_id in sector_ids(db_session))
    store = FakeStore()

    assert index_sectors(docs, store) == (13, 0)
    assert index_sectors(docs, store) == (0, 13)

    assert len(store.add_calls) == 2
    assert all(sorted(call) == expected_ids for call in store.add_calls)
    assert len(store.ids) == 13
