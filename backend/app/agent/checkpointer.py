"""The Postgres checkpointer for the trip planner (ticket 015).

It keeps paused runs in the project database, so they survive a server restart.

A pool and not one connection: FastAPI runs sync endpoints in parallel threads,
and a single psycopg connection is not safe to share between them.

setup() creates the checkpoint tables if they are missing and keeps its own
migration table, so calling it on every start is safe. That is why Alembic does
not know about these tables.
"""

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy.engine import make_url

POOL_MAX_SIZE = 5  # a few connections per server process, not one per request


def psycopg_conninfo(sqlalchemy_url: str) -> str:
    # SQLAlchemy names the driver (postgresql+psycopg://), psycopg wants plain postgresql://.
    url = make_url(sqlalchemy_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def open_postgres_saver(conninfo: str) -> PostgresSaver:
    pool = ConnectionPool(
        conninfo,
        max_size=POOL_MAX_SIZE,
        # The settings PostgresSaver.from_conn_string uses for its own connection.
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()
    return saver
