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
    {"id": 5, "name": "Vilanova de Meià", "region": "Noguera"}
]


@router.get("/")
def list_crags():
    return CRAGS


@router.get("/{crag_id}")
def get_crag(crag_id: int):
    # TODO: loop over CRAGS and return the crag whose "id" equals crag_id

    # If the loop finishes without returning, the crag doesn't exist.
    # Note: you RAISE HTTPException, you don't return it. Raising stops the
    # function immediately, and FastAPI turns it into a response with
    # that status code and {"detail": "..."} as the body.
    raise HTTPException(status_code=404, detail="Crag not found")
