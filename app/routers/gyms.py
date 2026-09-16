from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def list_gyms():
    return [{"id": 1, "name": "placeholder gym"}]

@router.get("/{gym_id}")
def get_gym(gym_id: int):
    return {"id": gym_id, "name": "placeholder gym"}