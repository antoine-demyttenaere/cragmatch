from pydantic import BaseModel, Field


class CragBase(BaseModel):
    name: str = Field(description="The crag's name, e.g. 'Siurana'.")
    region: str = Field(description="The region or comarca the crag is in, e.g. 'Priorat'.")
    latitude: float = Field(description="Latitude in decimal degrees.")
    longitude: float = Field(description="Longitude in decimal degrees.")


class CragCreate(CragBase):
    pass


class CragRead(CragBase):
    id: int
    model_config = {"from_attributes": True}
    # ^ lets FastAPI build a CragRead directly from a SQLAlchemy Crag
    # instance (attribute access), not just from a dict — needed since
    # your endpoints will now return ORM objects, not hand-built dicts.
