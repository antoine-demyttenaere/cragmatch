from fastapi import APIRouter, HTTPException, Depends

from app.grades import ranges_overlap, GRADE_ORDER
from app.geo import haversine_km

from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Sector
from app.schemas.sector import SectorCreate, SectorRead

from app.models import ClimbingStyle
from sqlalchemy.exc import IntegrityError

router = APIRouter()

@router.get("/", response_model=list[SectorRead])
def list_sectors(db: Session = Depends(get_db)):
    return db.query(Sector).all()


@router.get("/search", response_model=list[SectorRead])
def search_sectors(
    min_grade: str,
    max_grade: str,
    style: ClimbingStyle | None = None,
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    max_distance_km: float | None = None,
    db: Session = Depends(get_db),
):
    if min_grade not in GRADE_ORDER or max_grade not in GRADE_ORDER:
        raise HTTPException(status_code=400, detail="Invalid grade")

    sectors = db.query(Sector).all()
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



@router.get("/{sector_id}", response_model=SectorRead)
def get_sector(sector_id: int, db: Session = Depends(get_db)):
    sector = db.get(Sector, sector_id)
    if sector is None:
        raise HTTPException(status_code=404, detail="Sector not found")
    return sector


@router.post("/", response_model=SectorRead, status_code=201)
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

