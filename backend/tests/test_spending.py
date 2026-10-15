"""Daily spending cap: costs, the Madrid day, the stored total and the check.

Uses the test database and a clock the test controls. No network.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DailySpend
from app.services.spending import (
    DailyCapReached,
    Provider,
    claude_cost,
    current_day,
    ensure_under_cap,
    record_spend,
    spent,
    voyage_cost,
)


def utc(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# --- Costs and the day (pure) ----------------------------------------------


def test_claude_cost_uses_the_prices_in_settings(monkeypatch):
    monkeypatch.setattr(settings, "claude_input_usd_per_mtok", 3.0)
    monkeypatch.setattr(settings, "claude_output_usd_per_mtok", 15.0)

    assert claude_cost(1_000_000, 1_000_000) == pytest.approx(18.0)
    assert claude_cost(0, 0) == 0.0


def test_voyage_cost_counts_every_byte_of_the_text(monkeypatch):
    monkeypatch.setattr(settings, "voyage_usd_per_mtok", 1.0)

    assert voyage_cost("abcd") == pytest.approx(4e-6)
    assert voyage_cost("é") == pytest.approx(2e-6)  # two UTF-8 bytes


def test_day_follows_the_time_zone_in_settings(monkeypatch):
    monkeypatch.setattr(settings, "spending_timezone", "Europe/Madrid")
    # Summer time, UTC+2.
    assert current_day(utc(2026, 10, 13, 21, 59)) == date(2026, 10, 13)
    assert current_day(utc(2026, 10, 13, 22, 30)) == date(2026, 10, 14)
    # Winter time, UTC+1.
    assert current_day(utc(2026, 12, 31, 23, 30)) == date(2027, 1, 1)

    monkeypatch.setattr(settings, "spending_timezone", "Europe/London")
    assert current_day(utc(2026, 10, 13, 22, 30)) == date(2026, 10, 13)


# --- The stored total ---------------------------------------------------------


def test_nothing_spent_is_zero(db_session):
    assert spent(db_session, Provider.CLAUDE) == 0.0
    assert spent(db_session, Provider.VOYAGE) == 0.0


def test_spend_adds_up_per_day_and_provider(db_session):
    record_spend(db_session, Provider.CLAUDE, 0.2)
    record_spend(db_session, Provider.CLAUDE, 0.3)
    record_spend(db_session, Provider.VOYAGE, 0.1)

    assert spent(db_session, Provider.CLAUDE) == pytest.approx(0.5)
    assert spent(db_session, Provider.VOYAGE) == pytest.approx(0.1)
    claude_rows = db_session.scalars(
        select(DailySpend).where(DailySpend.provider == "claude")
    ).all()
    assert len(claude_rows) == 1


def test_zero_amount_writes_no_row(db_session):
    record_spend(db_session, Provider.CLAUDE, 0.0)

    assert db_session.scalars(select(DailySpend)).all() == []


def test_a_new_day_starts_from_zero(db_session, monkeypatch, set_clock):
    monkeypatch.setattr(settings, "claude_daily_cap_usd", 0.5)
    set_clock(utc(2026, 10, 13))
    record_spend(db_session, Provider.CLAUDE, 0.9)

    set_clock(utc(2026, 10, 14))

    assert spent(db_session, Provider.CLAUDE) == 0.0
    ensure_under_cap(db_session, Provider.CLAUDE)
    assert spent(db_session, Provider.CLAUDE, date(2026, 10, 13)) == pytest.approx(0.9)


def test_spend_survives_a_restart(db_session):
    record_spend(db_session, Provider.CLAUDE, 0.4)
    engine = db_session.get_bind()

    engine.dispose()  # every pooled connection is closed, as after a restart

    with Session(bind=engine) as fresh:
        assert spent(fresh, Provider.CLAUDE) == pytest.approx(0.4)


def test_records_at_the_same_time_lose_nothing(db_session):
    def record_many() -> None:
        for _ in range(25):
            record_spend(db_session, Provider.CLAUDE, 0.01)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in [pool.submit(record_many) for _ in range(4)]:
            future.result()

    assert spent(db_session, Provider.CLAUDE) == pytest.approx(1.0)


# --- The check ------------------------------------------------------------------


def test_under_the_cap_passes(db_session, monkeypatch):
    monkeypatch.setattr(settings, "claude_daily_cap_usd", 1.0)
    record_spend(db_session, Provider.CLAUDE, 0.99)

    ensure_under_cap(db_session, Provider.CLAUDE)


def test_reaching_the_cap_raises_for_that_provider(db_session, monkeypatch):
    monkeypatch.setattr(settings, "claude_daily_cap_usd", 1.0)
    monkeypatch.setattr(settings, "voyage_daily_cap_usd", 1.0)
    record_spend(db_session, Provider.CLAUDE, 1.0)

    with pytest.raises(DailyCapReached) as claude_over:
        ensure_under_cap(db_session, Provider.CLAUDE)
    assert claude_over.value.provider == Provider.CLAUDE

    with pytest.raises(DailyCapReached) as both_checked:
        ensure_under_cap(db_session, Provider.VOYAGE, Provider.CLAUDE)
    assert both_checked.value.provider == Provider.CLAUDE

    record_spend(db_session, Provider.VOYAGE, 1.0)
    monkeypatch.setattr(settings, "claude_daily_cap_usd", 5.0)
    with pytest.raises(DailyCapReached) as voyage_over:
        ensure_under_cap(db_session, Provider.VOYAGE, Provider.CLAUDE)
    assert voyage_over.value.provider == Provider.VOYAGE


def test_cap_of_zero_blocks_at_once(db_session, monkeypatch):
    monkeypatch.setattr(settings, "claude_daily_cap_usd", 0)

    with pytest.raises(DailyCapReached):
        ensure_under_cap(db_session, Provider.CLAUDE)


def test_free_endpoints_work_when_both_caps_are_reached(client, monkeypatch):
    monkeypatch.setattr(settings, "claude_daily_cap_usd", 0)
    monkeypatch.setattr(settings, "voyage_daily_cap_usd", 0)
    crag = client.post(
        "/crags/", json={"name": "C", "region": "R", "latitude": 41.4, "longitude": 2.0}
    )
    sector = client.post("/sectors/", json={
        "name": "S", "style": "sport", "grade_min": "6a", "grade_max": "7a",
        "crag_id": crag.json()["id"],
    })
    sector_id = sector.json()["id"]

    assert client.get("/sectors/search", params={"min_grade": "6a", "max_grade": "7a"}).status_code == 200

    group = client.post("/groups/", json={"name": "Trip"})
    assert group.status_code == 201
    code = group.json()["share_code"]
    assert client.post(f"/groups/{code}/members", json={"name": "Ana"}).status_code == 201

    assert client.get(f"/groups/{code}/search").status_code == 200
    assert client.get(f"/sectors/{sector_id}/stays").status_code == 200
    assert client.get(f"/groups/{code}/sectors/{sector_id}/stays").status_code == 200
    assert client.post(f"/groups/{code}/planner/runs", json={}).status_code == 201
