from fastapi import APIRouter, HTTPException

router = APIRouter()

# Temporary hardcoded data. In Step 1.2 these become validated Pydantic
# objects, and in Step 1.3 they move into a database.
# Uppercase name = Python convention for a module-level constant.
CRAGS = [
    {"id": 1, "name": "Siurana", "region": "Priorat"},
    {"id": 2, "name": "Margalef", "region": "Priorat"},
    {"id": 3, "name": "Montserrat", "region": "Bages"},
    {"id": 4, "name": "Terradets", "region": "Pallars Jussà"},
    {"id": 5, "name": "Vilanova de Meià", "region": "Noguera"},
]



@router.get("/")
def list_crags():
    return CRAGS


@router.get("/{crag_id}")
def get_crag(crag_id: int):
    for crag in CRAGS:
        if crag["id"] == crag_id:
            return crag
    raise HTTPException(status_code=404, detail="Crag not found")
