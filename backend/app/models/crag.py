from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.sector import Sector


class Crag(Base):
    __tablename__ = "crags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[float]
    longitude: Mapped[float]
    sectors: Mapped[list["Sector"]] = relationship(back_populates="crag")
