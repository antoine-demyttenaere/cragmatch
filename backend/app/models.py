from enum import Enum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class ClimbingStyle(str, Enum):
    SPORT = "sport"
    TRAD = "trad"
    BOULDER = "boulder"
    MULTI_PITCH = "multi-pitch"


class Crag(Base):
    __tablename__ = "crags"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[float]
    longitude: Mapped[float]
    sectors: Mapped[list["Sector"]] = relationship(back_populates="crag")


class Sector(Base):
    __tablename__ = "sectors"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    style: Mapped[ClimbingStyle]
    grade_min: Mapped[str] = mapped_column(String(10))
    grade_max: Mapped[str] = mapped_column(String(10))
    crag_id: Mapped[int] = mapped_column(ForeignKey("crags.id"))
    crag: Mapped["Crag"] = relationship(back_populates="sectors")
    