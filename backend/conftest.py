from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.agent.graph import build_trip_planner
from app.core.config import Settings, settings
from app.core.database import Base
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.main import app
from app.routers.planner import get_trip_planner
from app.services import spending

# Same connection, different database name: take the URL the app builds
# (the five parts or CRAGMATCH_POSTGRES_URL) and swap the database.
TEST_DATABASE_URL = (
    make_url(settings.database_url)
    .set(database="cragmatch_test")
    .render_as_string(hide_password=False)
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


SPENDING_SETTINGS = (
    "claude_daily_cap_usd",
    "voyage_daily_cap_usd",
    "claude_input_usd_per_mtok",
    "claude_output_usd_per_mtok",
    "voyage_usd_per_mtok",
    "spending_timezone",
)


@pytest.fixture(autouse=True)
def pin_spending_settings(monkeypatch):
    # A cap in a developer's backend/.env must not change the suite's results.
    for name in SPENDING_SETTINGS:
        monkeypatch.setattr(settings, name, Settings.model_fields[name].default)


@pytest.fixture()
def set_clock(monkeypatch):
    """Returns a function that freezes spending.utc_now at the given aware datetime."""

    def set_to(moment: datetime) -> None:
        monkeypatch.setattr(spending, "utc_now", lambda: moment)

    return set_to


@pytest.fixture()
def report_claude_usage():
    """Returns a function that reports tokens to the callbacks in a chain's config."""

    def report(config: dict, input_tokens: int, output_tokens: int) -> None:
        message = AIMessage(
            content="{}",
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )
        result = LLMResult(generations=[[ChatGeneration(message=message)]])
        for handler in config["callbacks"]:
            handler.on_llm_end(result, run_id=uuid4())

    return report


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
