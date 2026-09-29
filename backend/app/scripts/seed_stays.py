"""Insert the small hand-picked list of stays (source="curated").

Run BEFORE import_stays.py, so the import can skip OSM entries that
duplicate these.

    uv run python -m app.scripts.seed_stays

ILLUSTRATIVE sample data, like the sector notes in embed_sectors.py: names,
positions and prices are placeholders near each crag, not verified
listings. Replace them with places you actually know before relying on them.
"""

from app.core.database import SessionLocal
from app.models import Stay, StaySource, StayType

CURATED = [
    {"name": "Siurana village campsite", "type": StayType.CAMPSITE, "latitude": 41.2560, "longitude": 0.9310, "price_range": "€"},
    {"name": "Cornudella de Montsant climbers' hostel", "type": StayType.HOSTEL, "latitude": 41.2640, "longitude": 0.9050, "price_range": "€"},
    {"name": "Margalef climbers' campsite", "type": StayType.CAMPSITE, "latitude": 41.2870, "longitude": 0.7550, "price_range": "€"},
    {"name": "Montserrat mountain refuge", "type": StayType.REFUGE, "latitude": 41.6010, "longitude": 1.8150, "price_range": "€"},
    {"name": "Terradets gorge guesthouse", "type": StayType.GUESTHOUSE, "latitude": 42.0450, "longitude": 0.8720, "price_range": "€€"},
]


def main():
    db = SessionLocal()
    try:
        added = 0
        for entry in CURATED:
            exists = db.query(Stay).filter(Stay.source == StaySource.CURATED.value, Stay.name == entry["name"]).first()
            if exists:
                continue  # re-running the script is safe
            db.add(Stay(**{**entry, "type": entry["type"].value}, source=StaySource.CURATED.value))
            added += 1
        db.commit()
        print(f"Curated stays: {added} added, {len(CURATED) - added} already present.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
