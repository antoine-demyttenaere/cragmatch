from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.member import Member


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    share_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)

    members: Mapped[list["Member"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
