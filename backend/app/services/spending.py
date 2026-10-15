"""Daily spending cap on the paid APIs (Claude and Voyage).

Every paid call is checked before (ensure_under_cap) and counted after
(record_spend). A check followed by a call can overshoot the cap by the
requests already running; that is accepted, the numbers are estimates.

Reads and writes use their own short connection, not the request's session:
committing the session would expire the objects the request has loaded, and
reading through it would keep a transaction open during the paid call.
"""

from datetime import UTC, date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DailySpend

TOKENS_PER_MTOK = 1_000_000


class Provider(StrEnum):
    CLAUDE = "claude"
    VOYAGE = "voyage"


class DailyCapReached(Exception):
    def __init__(self, provider: Provider) -> None:
        super().__init__(provider)
        self.provider = provider


def utc_now() -> datetime:
    # The one clock; tests replace it.
    return datetime.now(UTC)


def current_day(now: datetime | None = None) -> date:
    # Settings are read at call time, so a test can change the time zone.
    local = (now or utc_now()).astimezone(ZoneInfo(settings.spending_timezone))
    return local.date()


def claude_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * settings.claude_input_usd_per_mtok
        + output_tokens * settings.claude_output_usd_per_mtok
    ) / TOKENS_PER_MTOK


def voyage_cost(text: str) -> float:
    # Bytes, not tokens: Voyage's answer doesn't give its token count back, and
    # a token covers at least one byte, so this is an upper bound for any length.
    return len(text.encode("utf-8")) * settings.voyage_usd_per_mtok / TOKENS_PER_MTOK


def _cap(provider: Provider) -> float:
    if provider is Provider.CLAUDE:
        return settings.claude_daily_cap_usd
    return settings.voyage_daily_cap_usd


def spent(db: Session, provider: Provider, day: date | None = None) -> float:
    statement = select(DailySpend.amount_usd).where(
        DailySpend.day == (day or current_day()),
        DailySpend.provider == provider.value,
    )
    with db.get_bind().connect() as connection:
        amount = connection.scalar(statement)
    return amount if amount is not None else 0.0


def ensure_under_cap(db: Session, *providers: Provider) -> None:
    for provider in providers:
        if spent(db, provider) >= _cap(provider):
            raise DailyCapReached(provider)


def record_spend(db: Session, provider: Provider, amount_usd: float) -> None:
    if amount_usd <= 0:
        return
    insert_statement = insert(DailySpend).values(
        day=current_day(), provider=provider.value, amount_usd=amount_usd
    )
    # One atomic statement, so two requests at the same moment both count.
    statement = insert_statement.on_conflict_do_update(
        index_elements=[DailySpend.day, DailySpend.provider],
        set_={"amount_usd": DailySpend.amount_usd + insert_statement.excluded.amount_usd},
    )
    with db.get_bind().begin() as connection:
        connection.execute(statement)
