"""Factories for the trip planner tests: build rows the way the nodes read them.

They sit on the `db_session` fixture of backend/conftest.py, which empties the
tables after each test.
"""

import pytest

from app.models import ClimbingStyle, Crag, Group, Member, Sector, Stay
from app.services.groups import generate_share_code


@pytest.fixture()
def make_group(db_session):
    def factory(name: str = "Trip", members: list[dict] | None = None) -> Group:
        group = Group(name=name, share_code=generate_share_code(db_session))
        for member in members or []:
            group.members.append(Member(**member))
        db_session.add(group)
        db_session.commit()
        return group

    return factory


@pytest.fixture()
def make_sector(db_session):
    def factory(
        name: str,
        grade_min: str,
        grade_max: str,
        style: str = "sport",
        lat: float = 41.60,
        lon: float = 1.81,
        approach: int | None = None,
        crag: str = "Montserrat",
    ) -> Sector:
        # One crag per distinct crag name.
        crag_row = db_session.query(Crag).filter(Crag.name == crag).first()
        if crag_row is None:
            crag_row = Crag(name=crag, region="Catalonia", latitude=lat, longitude=lon)
            db_session.add(crag_row)
            db_session.flush()
        sector = Sector(
            name=name, style=ClimbingStyle(style), grade_min=grade_min, grade_max=grade_max,
            crag_id=crag_row.id, approach_minutes=approach,
        )
        db_session.add(sector)
        db_session.commit()
        return sector

    return factory


@pytest.fixture()
def make_stay(db_session):
    def factory(name: str, lat: float, lon: float, type: str = "campsite") -> Stay:
        stay = Stay(name=name, type=type, latitude=lat, longitude=lon, source="curated")
        db_session.add(stay)
        db_session.commit()
        return stay

    return factory
