import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.agent.graph import build_trip_planner
from app.core.config import settings
from app.core.database import Base
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.main import app
from app.routers.planner import get_trip_planner

# Same connection, different database name — swap "cragmatch" for
# "cragmatch_test" in the URL your app already builds.
TEST_DATABASE_URL = (
    f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/cragmatch_test"
)


test_engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def setup_schema():
    # Runs once before any test, and once after the whole suite finishes.

    # Every TestClient request comes from the same "IP", so with the limiter
    # on, tests would start getting 429s once they add up to 10 calls to a
    # limited endpoint, depending on test order. Off for the whole run;
    # test_similar_is_rate_limited switches it back on for itself.
    limiter.enabled = False

    with test_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db_session():
    """A fresh, empty session for a single test."""
    session = TestingSessionLocal()
    yield session
    # Clear all tables
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()




@pytest.fixture()
def client(db_session):
    """A TestClient whose requests use db_session instead of the real DB."""
    def override_get_db():
        yield db_session

    # A new in-memory planner per test: no API test can open a Postgres saver.
    graph = build_trip_planner(InMemorySaver())

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_trip_planner] = lambda: graph
    yield TestClient(app)
    app.dependency_overrides.clear()
