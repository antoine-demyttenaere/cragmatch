from sqlalchemy.orm import Session, joinedload

from app.models import Sector, ClimbingStyle
from app.services.grades import GRADE_ORDER, ranges_overlap
from app.services.geo import haversine_km


def find_matching_sectors(
    db: Session,
    min_grade: str,
    max_grade: str,
    style: ClimbingStyle | None = None,
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    max_distance_km: float | None = None,
) -> list[Sector]:

    if min_grade not in GRADE_ORDER or max_grade not in GRADE_ORDER:
        raise ValueError(f"Invalid grade range: {min_grade}-{max_grade}")

    sectors = db.query(Sector).options(joinedload(Sector.crag)).all()

    filtered_sectors = [
        sector for sector in sectors
        if ranges_overlap(sector.grade_min, sector.grade_max, min_grade, max_grade)
    ]
    if style is not None:
        filtered_sectors = [s for s in filtered_sectors if s.style == style]

    if origin_lat is not None and origin_lon is not None and max_distance_km is not None:
        filtered_sectors = [
            sector for sector in filtered_sectors
            if haversine_km(sector.crag.latitude, sector.crag.longitude, origin_lat, origin_lon) <= max_distance_km
        ]

    return filtered_sectors
