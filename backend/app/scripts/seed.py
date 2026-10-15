"""Insert the sample Catalan crags and sectors.

    uv run python -m app.scripts.seed

Safe to re-run: it looks crags up by name and sectors by crag and name, and only
adds what is missing. Duplicates would also double the vector index, because the
vector ids are sector-{id}.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Crag, Sector, ClimbingStyle

CRAGS = [
    {
        "name": "Siurana",
        "region": "Priorat",
        "latitude": 41.2436,
        "longitude": 0.9186,
        "sectors": [
            {"name": "Can Marges", "style": ClimbingStyle.SPORT, "grade_min": "6a", "grade_max": "8a", "approach_minutes": 5},
            {"name": "Siuranella", "style": ClimbingStyle.SPORT, "grade_min": "6a", "grade_max": "8c", "approach_minutes": 15},
            {"name": "El Pati", "style": ClimbingStyle.SPORT, "grade_min": "7a", "grade_max": "9a+"},  # home of La Rambla
        ],
    },
    {
        "name": "Margalef",
        "region": "Priorat",
        "latitude": 41.1650,
        "longitude": 0.7820,
        "sectors": [
            {"name": "Camp de Tir", "style": ClimbingStyle.SPORT, "grade_min": "6a", "grade_max": "8b", "approach_minutes": 2},
            {"name": "Regall", "style": ClimbingStyle.SPORT, "grade_min": "6b", "grade_max": "8c+", "approach_minutes": 20},
            {"name": "Poble", "style": ClimbingStyle.SPORT, "grade_min": "5+", "grade_max": "7b", "approach_minutes": 5},
        ],
    },
    {
        "name": "Montserrat",
        "region": "Bages/Baix Llobregat",
        "latitude": 41.6047,
        "longitude": 1.8302,
        "sectors": [
            {"name": "Agulles", "style": ClimbingStyle.TRAD, "grade_min": "4", "grade_max": "7a", "approach_minutes": 45},
            {"name": "Collbató", "style": ClimbingStyle.SPORT, "grade_min": "5", "grade_max": "7c+", "approach_minutes": 10},
        ],
    },
    {
        "name": "Terradets",
        "region": "Pallars Jussà, Lleida",
        "latitude": 42.0170,
        "longitude": 0.8660,
        "sectors": [
            {"name": "Roca Regina", "style": ClimbingStyle.SPORT, "grade_min": "6b", "grade_max": "8b+", "approach_minutes": 10},
            {"name": "Paretot", "style": ClimbingStyle.SPORT, "grade_min": "7a", "grade_max": "8c", "approach_minutes": 10},
            {"name": "Aombra", "style": ClimbingStyle.SPORT, "grade_min": "6a", "grade_max": "7c", "approach_minutes": 10},
        ],
    },
    {
        "name": "Vilanova de Meià",
        "region": "La Noguera, Lleida",
        "latitude": 42.0330,
        "longitude": 1.0010,
        "sectors": [
            {"name": "Congost", "style": ClimbingStyle.SPORT, "grade_min": "6a", "grade_max": "8a", "approach_minutes": 30},
            {"name": "Serrat", "style": ClimbingStyle.SPORT, "grade_min": "5+", "grade_max": "7b+", "approach_minutes": 10},
        ],
    },
]


def sample_sector_keys() -> set[tuple[str, str]]:
    """The (crag name, sector name) pairs that are sample data; seed_notes only touches these."""
    return {(crag["name"], sector["name"]) for crag in CRAGS for sector in crag["sectors"]}


def seed(db: Session) -> tuple[int, int]:
    """Add the crags and sectors that are missing; return how many of each were added."""
    crags_added = sectors_added = 0
    for crag_data in CRAGS:
        crag_fields = {k: v for k, v in crag_data.items() if k != "sectors"}
        # Oldest first, so a database that already holds duplicates always picks the same row.
        crag = db.scalars(select(Crag).where(Crag.name == crag_data["name"]).order_by(Crag.id)).first()
        if crag is None:
            crag = Crag(**crag_fields)
            db.add(crag)
            # SessionLocal has autoflush=False: flush to get crag.id for the sectors below.
            db.flush()
            crags_added += 1

        for sector_data in crag_data["sectors"]:
            exists = db.scalars(
                select(Sector).where(Sector.crag_id == crag.id, Sector.name == sector_data["name"])
            ).first()
            if exists is None:
                db.add(Sector(**sector_data, crag_id=crag.id))
                sectors_added += 1
    db.commit()
    return crags_added, sectors_added


def main() -> None:
    with SessionLocal() as db:
        crags_added, sectors_added = seed(db)
    crags_total = len(CRAGS)
    sectors_total = sum(len(crag["sectors"]) for crag in CRAGS)
    print(
        f"Crags: {crags_added} added, {crags_total - crags_added} already present. "
        f"Sectors: {sectors_added} added, {sectors_total - sectors_added} already present."
    )


if __name__ == "__main__":
    main()
