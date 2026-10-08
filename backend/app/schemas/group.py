from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import ClimbingStyle
from app.schemas.sector import SectorRead
from app.services.grades import GRADE_ORDER, grade_rank


class MemberBase(BaseModel):
    # use_enum_values: after validation, store "sport" instead of
    # ClimbingStyle.SPORT, so styles can go straight into the ARRAY(String) column.
    model_config = {"use_enum_values": True}

    name: str = Field(min_length=1, max_length=100)
    grade_min: str | None = None
    grade_max: str | None = None
    max_distance_km: float | None = Field(default=None, gt=0)
    max_approach_minutes: int | None = Field(default=None, ge=1, le=180)
    styles: list[ClimbingStyle] = []

    @field_validator("grade_min", "grade_max")
    @classmethod
    def grade_must_exist(cls, value: str | None) -> str | None:
        # Runs on each grade field on its own: is it a real French grade?
        if value is not None and value not in GRADE_ORDER:
            raise ValueError("This is not a Grade in climbing")
        return value

    @model_validator(mode="after")
    def grade_range_is_valid(self):
        # Runs after all fields are validated, so it can compare them.
        # 1. Both grades set, or neither: half a range makes no sense for matching.
        #    `!=` between the two booleans is True when exactly one is missing.
        if (self.grade_min is None) != (self.grade_max is None):
            raise ValueError("Half a range makes no sense for matching: set both grades or neither")
        # 2. min can't be harder than max. Equal is fine: 6a to 6a is a valid range.
        if self.grade_min is not None and self.grade_max is not None:
            if grade_rank(self.grade_min) > grade_rank(self.grade_max):
                raise ValueError("grade_min can't be harder than grade_max")
        return self


class MemberCreate(MemberBase):
    pass


class MemberRead(MemberBase):
    id: int
    model_config = {"from_attributes": True, "use_enum_values": True}


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GroupRead(BaseModel):
    name: str
    share_code: str
    members: list[MemberRead]
    model_config = {"from_attributes": True}


# --- Group search ---------------------------------------------------------


class MergedFilters(BaseModel):
    """Strict mode only: the filters the whole group agreed on."""
    grade_min: str
    grade_max: str
    max_distance_km: float | None = Field(description="None = no distance limit.")
    styles: list[str] | None = Field(description="None = any style.")


class MemberMisfit(BaseModel):
    name: str
    reason: str = Field(description="e.g. 'too easy', 'too far (112 km > 80 km)'.")


class GroupSectorMatch(BaseModel):
    sector: SectorRead
    distance_km: float = Field(description="Straight-line distance from Barcelona.")
    fit_count: int
    member_count: int
    fits: list[str] = Field(description="Names of the members this sector fits.")
    misfits: list[MemberMisfit] = Field(description="Members it doesn't fit, and why.")


class GroupSearchResponse(BaseModel):
    mode: str
    fit: str
    member_count: int
    common_ground: bool = Field(
        description="strict: the group's preferences overlap. scored: at least one sector fits everyone."
    )
    message: str | None = Field(default=None, description="Why there are no results, when there are none.")
    filters: MergedFilters | None = None
    results: list[GroupSectorMatch]
