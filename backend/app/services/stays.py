"""Finding stays near a point, and building booking-site search links."""

import math
from datetime import date, timedelta
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.models import Stay
from app.services.geo import haversine_km

KM_PER_DEGREE_LAT = 111.32


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lon, max_lon) of a square around a point.

    A degree of latitude is always ~111 km, but a degree of longitude shrinks
    towards the poles (by cos(latitude)), so the box is wider in degrees of
    longitude than of latitude.
    """
    dlat = radius_km / KM_PER_DEGREE_LAT
    dlon = radius_km / (KM_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def find_stays_near(
    db: Session,
    lat: float,
    lon: float,
    max_distance_km: float,
    stay_type: str | None = None,
) -> list[tuple[Stay, float]]:
    """Stays within max_distance_km of (lat, lon), closest first.

    Two steps: a cheap bounding-box filter in SQL (can use indexes, and cuts
    thousands of rows down to a handful), then the exact haversine distance
    in Python on what's left. The box's corners are further away than the
    radius, which is why the exact check is still needed.
    """
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, max_distance_km)
    query = db.query(Stay).filter(
        Stay.latitude.between(min_lat, max_lat),
        Stay.longitude.between(min_lon, max_lon),
    )
    if stay_type is not None:
        query = query.filter(Stay.type == stay_type)

    nearby = []
    for stay in query.all():
        distance = haversine_km(lat, lon, stay.latitude, stay.longitude)
        if distance <= max_distance_km:
            nearby.append((stay, distance))
    nearby.sort(key=lambda pair: pair[1])
    return nearby


def next_saturday(today: date | None = None) -> date:
    """Default check-in for a climbing weekend. Always in the future."""
    today = today or date.today()
    days_ahead = (5 - today.weekday()) % 7 or 7  # Monday=0 ... Saturday=5
    return today + timedelta(days=days_ahead)


def airbnb_url(lat: float, lon: float, checkin: date, checkout: date, guests: int, radius_km: float = 10) -> str:
    # Airbnb's own search page, limited to a map box around the crag.
    # These parameters aren't a documented API: sites can change them, so
    # check the links by hand now and then.
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)
    params = {
        "search_by_map": "true",
        "sw_lat": f"{min_lat:.5f}", "sw_lng": f"{min_lon:.5f}",
        "ne_lat": f"{max_lat:.5f}", "ne_lng": f"{max_lon:.5f}",
        "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
        "adults": guests,
    }
    return f"https://www.airbnb.com/s/homes?{urlencode(params)}"


def booking_url(place: str, lat: float, lon: float, checkin: date, checkout: date, guests: int) -> str:
    # Booking.com search around a coordinate. Same caveat as airbnb_url().
    params = {
        "ss": place,
        "latitude": f"{lat:.5f}", "longitude": f"{lon:.5f}",
        "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
        "group_adults": guests, "no_rooms": 1, "group_children": 0,
    }
    return f"https://www.booking.com/searchresults.html?{urlencode(params)}"
