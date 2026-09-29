from enum import Enum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StayType(str, Enum):
    CAMPSITE = "campsite"
    HOSTEL = "hostel"
    REFUGE = "refuge"          # mountain huts (OSM alpine_hut / wilderness_hut)
    GUESTHOUSE = "guesthouse"
    APARTMENT = "apartment"


class StaySource(str, Enum):
    CURATED = "curated"  # hand-picked list in scripts/seed_stays.py
    OSM = "osm"          # imported from OpenStreetMap by scripts/import_stays.py


class Stay(Base):
    __tablename__ = "stays"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # Stored as plain strings (validated through the enums above in the
    # schemas), for the same reason as Member.styles: no Postgres enum type
    # for Alembic to trip over.
    type: Mapped[str] = mapped_column(String(20), index=True)
    latitude: Mapped[float]
    longitude: Mapped[float]
    price_range: Mapped[str | None] = mapped_column(String(10))  # "€", "€€", "€€€"
    source: Mapped[str] = mapped_column(String(20))
    url: Mapped[str | None] = mapped_column(String(500))
    # Where an imported row came from, e.g. "osm:node/123456". Unique, so
    # re-running the import updates rows instead of duplicating them.
    # NULL for curated rows (Postgres allows many NULLs in a unique column).
    external_id: Mapped[str | None] = mapped_column(String(50), unique=True)
