from fastapi import APIRouter, HTTPException, Depends

from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Sector
from app.schemas.sector import SectorCreate, SectorRead

from sqlalchemy.exc import IntegrityError

router = APIRouter()

@router.get("/", response_model=list[SectorRead])
def list_sectors(db: Session = Depends(get_db)):
    return db.query(Sector).all()

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