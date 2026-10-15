from datetime import date

from sqlalchemy import Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailySpend(Base):
    __tablename__ = "daily_spend"

    # One row per day and provider, so the total survives a restart, and a new
    # day simply has no row yet.
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
