from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.stay import BookingLinks, NearbyStay


class PlannerSector(BaseModel):
    # Same fields as Candidate in agent/state.py.
    sector_id: int
    sector_name: str
    crag_name: str
    style: str
    grade_min: str
    grade_max: str
    approach_minutes: int | None
    distance_km: float


class PlannerPlan(BaseModel):
    sector: PlannerSector
    checkin: date
    checkout: date
    nights: int
    guests: int
    stays: list[NearbyStay]
    links: BookingLinks


class TraceStep(BaseModel):
    node: str
    changed: list[str]


class RejectionRead(BaseModel):
    sector_id: int
    reason: str


class PlannerRunStart(BaseModel):
    # Same rules as the group stays endpoint and the trip_planner script.
    checkin: date | None = Field(default=None, description="Defaults to next Saturday.")
    nights: int = Field(default=2, ge=1, le=30)
    guests: int | None = Field(default=None, ge=1, le=30)

    @field_validator("checkin")
    @classmethod
    def checkin_not_in_the_past(cls, value: date | None) -> date | None:
        if value is not None and value < date.today():
            raise ValueError("checkin can't be in the past")
        return value


class PlannerRunRead(BaseModel):
    run_id: UUID
    share_code: str
    status: Literal["waiting_for_approval", "planned", "no_plan"]
    checkin: date
    nights: int
    guests: int | None
    proposal: PlannerSector | None
    plan: PlannerPlan | None
    message: str | None
    rejections: list[RejectionRead]
    trace: list[TraceStep]
    created_at: datetime


class PlannerEdge(BaseModel):
    source: str
    target: str
    conditional: bool


class PlannerGraphRead(BaseModel):
    nodes: list[str]
    edges: list[PlannerEdge]
