from uuid import uuid4

from langgraph.types import Command

from app.agent.checkpointer import open_postgres_saver, psycopg_conninfo
from app.agent.graph import build_trip_planner
from app.agent.state import Approval, PlannerContext, initial_state


def test_psycopg_conninfo_drops_the_driver_name():
    assert psycopg_conninfo("postgresql+psycopg://u:p@h:5433/db") == "postgresql://u:p@h:5433/db"


def test_psycopg_conninfo_keeps_ssl_options():
    url = "postgresql+psycopg://u:p@h:5432/db?sslmode=require"
    assert psycopg_conninfo(url) == "postgresql://u:p@h:5432/db?sslmode=require"


def test_postgres_saver_resumes_a_run_after_reopening(db_session, agreeing_group):
    # db_session is bound to the cragmatch_test engine: never the dev database.
    test_url = db_session.get_bind().url.render_as_string(hide_password=False)
    conninfo = psycopg_conninfo(test_url)
    config = {"configurable": {"thread_id": str(uuid4())}}
    context = PlannerContext(db=db_session)

    # Close the read transaction the fixtures left open: on a fresh database the
    # first setup() builds its indexes CONCURRENTLY, which waits for every open
    # transaction in the database.
    db_session.rollback()

    first = open_postgres_saver(conninfo)
    try:
        graph = build_trip_planner(first)
        graph.invoke(initial_state(agreeing_group.share_code), config, context=context)
        assert graph.get_state(config).next == ("approve_sector",)
    finally:
        first.conn.close()

    # The nodes left a read transaction open; end it before the restart.
    db_session.rollback()

    # A new saver and graph, as after a restart: the pause is read from Postgres.
    second = open_postgres_saver(conninfo)
    try:
        graph = build_trip_planner(second)
        resume = Command(resume=Approval(approved=True).model_dump())
        state = graph.invoke(resume, config, context=context)
        assert state["plan"]["sector"]["sector_name"] == "Near"
    finally:
        second.delete_thread(config["configurable"]["thread_id"])
        second.conn.close()
