from fastapi import APIRouter, HTTPException, Depends, Query

from app.grades import ranges_overlap, GRADE_ORDER
from app.geo import haversine_km

from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Sector
from app.schemas.sector import SectorCreate, SectorRead

from app.models import ClimbingStyle
from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import joinedload


router = APIRouter()

@router.get(
    "/",
    response_model=list[SectorRead],
    summary="List all sectors",
    description="Return every climbing sector in the database, across all crags.",
)
def list_sectors(db: Session = Depends(get_db)):
    return db.query(Sector).options(joinedload(Sector.crag)).all()



@router.get(
    "/search",
    response_model=list[SectorRead],
    summary="Search sectors by grade, style, and distance",
    description=(
        "Find sectors whose own grade range overlaps the requested "
        "min_grade-max_grade range (a sector matches if it offers ANY "
        "climbable routes within that range, even if its full range is "
        "wider). Optionally narrow by style, and by straight-line "
        "distance from an origin point."
    ),
)
def search_sectors(
    min_grade: str = Query(description="Easiest French grade to search for, e.g. '6a'.", examples=["6a"]),
    max_grade: str = Query(description="Hardest French grade to search for, e.g. '7a'.", examples=["7a"]),
    style: ClimbingStyle | None = Query(default=None, description="Restrict results to a single climbing style."),
    origin_lat: float | None = Query(
        default=None, description="Latitude of the search origin, in decimal degrees. Required together with origin_lon and max_distance_km to filter by distance."
    ),
    origin_lon: float | None = Query(
        default=None, description="Longitude of the search origin, in decimal degrees. Required together with origin_lat and max_distance_km to filter by distance."
    ),
    max_distance_km: float | None = Query(
        default=None, description="Maximum straight-line distance in km from the origin. Ignored unless origin_lat and origin_lon are also given."
    ),
    db: Session = Depends(get_db),
):
    if min_grade not in GRADE_ORDER or max_grade not in GRADE_ORDER:
        raise HTTPException(status_code=400, detail="Invalid grade")

    sectors = db.query(Sector).options(joinedload(Sector.crag)).all()

    filtered_sectors = [
        sector for sector in sectors
        if ranges_overlap(sector.grade_min, sector.grade_max, min_grade, max_grade)
    ]
    if style is not None:
        filtered_sectors = [s for s in filtered_sectors if s.style == style]

    if origin_lat is not None and origin_lon is not None and max_distance_km is not None:
        filtered_sectors = [
            sector for sector in filtered_sectors
            if haversine_km(sector.crag.latitude, sector.crag.longitude, origin_lat, origin_lon) <= max_distance_km
        ]

    return filtered_sectors


@router.get(
    "/{sector_id}",
    response_model=SectorRead,
    summary="Get a sector by ID",
    responses={404: {"description": "No sector exists with the given ID"}},
)
def get_sector(sector_id: int, db: Session = Depends(get_db)):
    sector = db.get(Sector, sector_id)
    if sector is None:
        raise HTTPException(status_code=404, detail="Sector not found")
    return sector


@router.post(
    "/",
    response_model=SectorRead,
    status_code=201,
    summary="Create a sector",
    description="Create a new sector within an existing crag (crag_id must reference a real crag).",
    responses={400: {"description": "crag_id does not reference an existing crag"}},
)
def create_sector(sector: SectorCreate, db: Session = Depends(get_db)):
    db_sector = Sector(**sector.model_dump())
    db.add(db_sector)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()   # required — the failed transaction must be rolled
                         # back before this session can run anything else
        raise HTTPException(status_code=400, detail="Invalid crag_id")
    db.refresh(db_sector)
    return db_sector
