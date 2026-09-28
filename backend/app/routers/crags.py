from fastapi import APIRouter, HTTPException, Depends

from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.models import Crag
from app.schemas.crag import CragCreate, CragRead


router = APIRouter()


@router.get(
    "/",
    response_model=list[CragRead],
    summary="List all crags",
    description="Return every climbing crag in the database.",
)
def list_crags(db: Session = Depends(get_db)):
    return db.query(Crag).all()


@router.get(
    "/{crag_id}",
    response_model=CragRead,
    summary="Get a crag by ID",
    responses={404: {"description": "No crag exists with the given ID"}},
)
def get_crag(crag_id: int, db: Session = Depends(get_db)):
    crag = db.get(Crag, crag_id)
    if crag is None:
        raise HTTPException(status_code=404, detail="Crag not found")
    return crag


@router.post(
    "/",
    response_model=CragRead,
    status_code=201,
    summary="Create a crag",
    description="Create a new climbing crag with a name, region, and coordinates.",
)
def create_crag(crag: CragCreate, db: Session = Depends(get_db)):
    db_crag = Crag(**crag.model_dump())
    db.add(db_crag)
    db.commit()
    db.refresh(db_crag)
    return db_crag