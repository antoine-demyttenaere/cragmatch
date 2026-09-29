from datetime import date

from pydantic import BaseModel, Field

from app.models import StaySource, StayType


class StayRead(BaseModel):
    id: int
    name: str
    type: StayType
    latitude: float
    longitude: float
    price_range: str | None
    source: StaySource
    url: str | None = Field(description="The place's own website, when known.")
    model_config = {"from_attributes": True}


class NearbyStay(BaseModel):
    stay: StayRead
    distance_km: float = Field(description="Straight-line distance from the sector's crag.")


class BookingLinks(BaseModel):
    """Prefilled searches on sites we can't query directly (no public API)."""
    airbnb: str
    booking: str


class GroupStaysResponse(BaseModel):
    sector_id: int
    sector_name: str
    crag_name: str
    guests: int
    checkin: date
    checkout: date
    stays: list[NearbyStay]
    links: BookingLinks
