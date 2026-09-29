"""Import campsites, hostels and huts around every crag from OpenStreetMap.

A one-off command, never run per request:

    uv run python -m app.scripts.seed_stays     # curated list first
    uv run python -m app.scripts.import_stays   # then OSM

Safe to re-run: OSM rows are matched by external_id and updated, and
responses are cached for a week in backend/.cache/overpass/.
Add --no-cache to force fresh data.
"""

import sys
import time

from app.core.database import SessionLocal
from app.models import Crag, Stay, StaySource
from app.services.overpass import OverpassError, build_query, fetch_overpass, find_duplicate, parse_elements

RADIUS_M = 15_000  # the stays endpoint defaults to 10 km, so 15 km leaves margin


def main(use_cache: bool = True):
    db = SessionLocal()
    try:
        curated = db.query(Stay).filter(Stay.source == StaySource.CURATED.value).all()
        existing_osm = {s.external_id: s for s in db.query(Stay).filter(Stay.source == StaySource.OSM.value)}
        added = updated = duplicates = skipped = 0
        failed: list[str] = []

        for crag in db.query(Crag).order_by(Crag.id):
            query = build_query(crag.latitude, crag.longitude, RADIUS_M)
            try:
                data = fetch_overpass(query, use_cache=use_cache)
            except OverpassError as exc:
                # One unlucky crag shouldn't throw away the others: note it and
                # move on. Re-running retries it; the others come from the cache.
                print(f"{crag.name}: FAILED ({exc})")
                failed.append(crag.name)
                continue
            parsed, bad = parse_elements(data.get("elements", []))
            skipped += bad
            print(f"{crag.name}: {len(parsed)} usable places, {bad} skipped (no name/type/coordinates)")

            for p in parsed:
                row = existing_osm.get(p.external_id)
                if row is not None:
                    # Seen before (earlier run, or a nearby crag this run): refresh it.
                    row.name, row.type, row.url = p.name, p.type.value, p.url
                    row.latitude, row.longitude = p.latitude, p.longitude
                    updated += 1
                    continue
                if find_duplicate(p, curated) is not None:
                    duplicates += 1  # the hand-picked entry wins
                    continue
                row = Stay(
                    name=p.name, type=p.type.value, latitude=p.latitude, longitude=p.longitude,
                    url=p.url, source=StaySource.OSM.value, external_id=p.external_id,
                )
                db.add(row)
                existing_osm[p.external_id] = row
                added += 1

            time.sleep(2)  # be polite to a free, shared service

        db.commit()
        print(f"\nDone: {added} added, {updated} updated, {duplicates} skipped as duplicates of curated stays, "
              f"{skipped} skipped as unusable.")
        if failed:
            print(f"Not imported (Overpass busy): {', '.join(failed)}. Run the script again later.")
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main(use_cache="--no-cache" not in sys.argv)
