from pydantic import BaseModel

from app.models import ClimbingStyle

class CragBase(BaseModel):
    name: str
    region: str
    latitude: float
    longitude: float

class CragCreate(CragBase):
    pass

class CragRead(CragBase):
    id: int
    model_config = {"from_attributes": True}
    # ^ lets FastAPI build a CragRead directly from a SQLAlchemy Crag
    # instance (attribute access), not just from a dict — needed since
    # your endpoints will now return ORM objects, not hand-built dicts.

