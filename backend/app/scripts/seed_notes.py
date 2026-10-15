"""Fill sectors.approach_notes from the NOTES dict below. No API calls.

    uv run python -m app.scripts.seed_notes

Run after seed and before index_sectors_langchain, because the index embeds
the notes. Safe to re-run.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal
from app.models import Sector
from app.scripts.seed import sample_sector_keys

# Illustrative notes for testing fuzzy search, not verified beta.
NOTES = {
    "Can Marges": "Popular, well-bolted sport wall with a short 5-minute approach from the parking. Can get crowded on weekends.",
    "Siuranella": "Long orange limestone wall with lots of mid-grade routes. 15-minute walk, sunny in the afternoon, great in winter.",
    "El Pati": "Home of the legendary La Rambla. Steep, serious atmosphere, for strong climbers. Busy with visiting pros.",
    "Camp de Tir": "Pocketed conglomerate right next to the road, almost no approach. Shady in the morning, good for a quick session.",
    "Regall": "Overhanging conglomerate caves with powerful, pumpy routes. 20-minute walk up a steep path. Stays dry in light rain.",
    "Poble": "Easy-going crag just above the village, 5 minutes from the car. Family-friendly base with flat ground, good for beginners and kids.",
    "Agulles": "Adventurous traditional climbing on Montserrat's conglomerate needles. Long approach, sparse protection, quiet and remote.",
    "Collbató": "Sunny south-facing slabs and walls above Collbató, short approach. Technical, vertical climbing, can be hot in summer.",
    "Roca Regina": "Tall grey limestone above the Noguera Pallaresa river, 10-minute approach. Shaded most of the day, good in summer.",
    "Paretot": "Steep, athletic limestone for strong climbers. Short but steep uphill approach. Quiet midweek.",
    "Aombra": "Shady, sheltered sector with moderate routes, 10 minutes from the car. Cool in summer, usually uncrowded.",
    "Congost": "Big limestone gorge walls in the Montsec, long multi-bolt routes. 30-minute approach, peaceful and remote.",
    "Serrat": "Relaxed sunny sector with plenty of moderate routes and a 10-minute approach. Quiet, good for a laid-back day.",
}


def apply_notes(db: Session) -> tuple[int, int]:
    """Set the listed notes on the sample sectors; return (set, already up to date)."""
    sample_keys = sample_sector_keys()
    changed = unchanged = 0
    for sector in db.scalars(select(Sector).options(joinedload(Sector.crag))):
        # Sectors made through the API keep their own notes (ticket 023).
        if (sector.crag.name, sector.name) not in sample_keys or sector.name not in NOTES:
            continue
        if sector.approach_notes == NOTES[sector.name]:
            unchanged += 1
        else:
            sector.approach_notes = NOTES[sector.name]
            changed += 1
    db.commit()
    return changed, unchanged


def main() -> None:
    with SessionLocal() as db:
        changed, unchanged = apply_notes(db)
    print(f"Approach notes: {changed} set, {unchanged} already up to date; other sectors left as they are.")


if __name__ == "__main__":
    main()
