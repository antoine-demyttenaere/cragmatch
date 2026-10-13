"""Factories for the trip planner tests: build rows the way the nodes read them.

They sit on the `db_session` fixture of backend/conftest.py, which empties the
tables after each test.
"""

from typing import NamedTuple
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_trip_planner
from app.agent.state import PlannerContext
from app.models import ClimbingStyle, Crag, Group, Member, Sector, Stay
from app.services.groups import generate_share_code

# No distance limits: Far (Siurana, about 106 km out) must stay a candidate.
AGREEING_MEMBERS = [
    {"name": "Ana", "grade_min": "6a", "grade_max": "7a"},
    {"name": "Marc", "grade_min": "6b", "grade_max": "7b"},
]
DISAGREEING_MEMBERS = [
    {"name": "Ana", "grade_min": "5", "grade_max": "6a"},
    {"name": "Marc", "grade_min": "7a", "grade_max": "8a"},
]


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


@pytest.fixture()
def thread_config() -> dict:
    """A new thread per test, so checkpoints can't leak between tests."""
    return {"configurable": {"thread_id": str(uuid4())}}


@pytest.fixture()
def planner(db_session):
    # A new saver every time: the checkpoints live in it.
    return build_trip_planner(InMemorySaver()), PlannerContext(db=db_session)


class AgreeingGroup(NamedTuple):
    share_code: str
    near_id: int
    far_id: int


@pytest.fixture()
def agreeing_group(make_group, make_sector, make_stay) -> AgreeingGroup:
    # Two matching sectors at different crags (Near is closer to Barcelona), a stay
    # near each, and one sector nobody in the group can climb.
    group = make_group(members=AGREEING_MEMBERS)
    near = make_sector("Near", "6a", "7a")
    far = make_sector("Far", "6a", "7a", lat=41.26, lon=0.93, crag="Siurana")
    make_sector("Too hard", "8a", "9a")
    make_stay("Close", 41.61, 1.82)
    make_stay("Siurana camp", 41.27, 0.94)
    return AgreeingGroup(group.share_code, near.id, far.id)


@pytest.fixture()
def disagreeing_group(make_group) -> str:
    return make_group(members=DISAGREEING_MEMBERS).share_code
