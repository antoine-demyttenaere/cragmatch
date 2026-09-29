from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.group import Group


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    group: Mapped["Group"] = relationship(back_populates="members")

    # Preferences: all optional, a member can join before filling them in.
    # `| None` is what makes these columns nullable.
    grade_min: Mapped[str | None] = mapped_column(String(10))
    grade_max: Mapped[str | None] = mapped_column(String(10))
    max_distance_km: Mapped[float | None]  # DOUBLE PRECISION, like Crag's lat/lon

    styles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
