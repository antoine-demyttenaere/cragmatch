from pydantic import BaseModel, Field

from app.models import ClimbingStyle
from app.schemas.crag import CragSummary



class SectorBase(BaseModel):
    name: str = Field(description="The sector's name, e.g. 'Can Marges'.")
    style: ClimbingStyle = Field(description="Climbing style offered in this sector.")
    grade_min: str = Field(
        description="Easiest French grade in this sector, e.g. '6a'.",
        examples=["6a"],
    )
    grade_max: str = Field(
        description="Hardest French grade in this sector, e.g. '7a+'.",
        examples=["7a+"],
    )
    crag_id: int = Field(description="ID of the crag this sector belongs to.")


class SectorCreate(SectorBase):
    pass


class SectorRead(SectorBase):
    id: int
    crag: CragSummary
    model_config = {"from_attributes": True}

