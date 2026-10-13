import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlannerRun(Base):
    __tablename__ = "planner_runs"

    # The id doubles as the LangGraph thread_id, so a run row and its checkpoints
    # always find each other.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # The node-by-node trace lives here, not in the graph state: it is a record of
    # the run, not planner data, and no node has to know about it.
    trace: Mapped[list[dict]] = mapped_column(JSONB, default=list)
