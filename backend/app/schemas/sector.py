from pydantic import BaseModel

from app.models import ClimbingStyle

class SectorBase(BaseModel):
    name: str
    style: ClimbingStyle
    grade_min: str
    grade_max: str
    crag_id: int

class SectorCreate(SectorBase):
    pass


class SectorRead(SectorBase):
    id: int
    model_config = {"from_attributes": True}