from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/")
def list_crags():
    return CRAGS


@router.get("/{crag_id}")
def get_crag(crag_id: int):
    for crag in CRAGS:
        if crag["id"] == crag_id:
            return crag
    raise HTTPException(status_code=404, detail="Crag not found")
