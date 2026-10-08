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



def seed():
    db = SessionLocal()
    try:
        # TODO: for each crag dict in CRAGS:
        #   1. build a Crag(...) instance from its own fields (not "sectors")
        #   2. for each sector dict, build a Sector(...) and append it to
        #      crag.sectors (SQLAlchemy will wire up crag_id automatically
        #      via the relationship when you commit)
        #   3. db.add( crag)
        # then db.commit()
        for crag_data in CRAGS:
            crag_fields = {k: v for k, v in crag_data.items() if k != "sectors"}
            crag = Crag(**crag_fields)
            db.add(crag)
            db.commit()
            db.refresh(crag)

            for sector_data in crag_data["sectors"]:
                sector = Sector(**sector_data, crag_id=crag.id)
                db.add(sector)
        db.commit()

    finally:
        db.close()

if __name__ == "__main__":
    seed()
