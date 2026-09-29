"""Tests for nearby stays: distance filtering, the two endpoints, deep links."""

from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from app.models import Stay
from app.services.geo import haversine_km
from app.services.stays import bounding_box, next_saturday

CRAG = {"latitude": 41.2436, "longitude": 0.9186}  # Siurana


def _add_stay(db_session, name, lat, lon, type="campsite"):
    db_session.add(Stay(name=name, type=type, latitude=lat, longitude=lon, source="curated"))
    db_session.commit()


def _sector_id(client, name="Can Marges"):
    crag = client.post("/crags/", json={"name": "Siurana", "region": "Priorat", **CRAG}).json()
    return client.post("/sectors/", json={
        "name": name, "style": "sport", "grade_min": "6a", "grade_max": "8a", "crag_id": crag["id"],
    }).json()["id"]


# --- Pure helpers ---------------------------------------------------------


def test_bounding_box_contains_the_whole_circle():
    lat, lon = CRAG["latitude"], CRAG["longitude"]
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, 10)

    # The box's edges are (about) 10 km from the centre, in every direction.
    assert round(haversine_km(lat, lon, max_lat, lon), 1) == 10.0
    assert round(haversine_km(lat, lon, lat, max_lon), 1) == 10.0


def test_next_saturday_is_always_in_the_future():
    assert next_saturday(date(2026, 10, 7)) == date(2026, 10, 10)   # Wednesday
    assert next_saturday(date(2026, 10, 10)) == date(2026, 10, 17)  # a Saturday -> the next one


# --- GET /sectors/{id}/stays ----------------------------------------------


def test_stays_are_filtered_by_distance_and_sorted(client, db_session):
    sector_id = _sector_id(client)
    _add_stay(db_session, "Far (~8 km)", 41.3150, 0.9186)
    _add_stay(db_session, "Near (~1 km)", 41.2526, 0.9186)
    _add_stay(db_session, "Too far (~20 km)", 41.4236, 0.9186)

    body = client.get(f"/sectors/{sector_id}/stays").json()  # default 10 km

    assert [s["stay"]["name"] for s in body] == ["Near (~1 km)", "Far (~8 km)"]
    assert body[0]["distance_km"] < body[1]["distance_km"]


def test_stays_max_distance_param(client, db_session):
    sector_id = _sector_id(client)
    _add_stay(db_session, "~20 km", 41.4236, 0.9186)

    assert client.get(f"/sectors/{sector_id}/stays").json() == []
    assert len(client.get(f"/sectors/{sector_id}/stays", params={"max_distance_km": 25}).json()) == 1


def test_stays_filter_by_type(client, db_session):
    sector_id = _sector_id(client)
    _add_stay(db_session, "Camp", 41.2526, 0.9186, type="campsite")
    _add_stay(db_session, "Hostel", 41.2526, 0.9190, type="hostel")

    body = client.get(f"/sectors/{sector_id}/stays", params={"type": "hostel"}).json()

    assert [s["stay"]["name"] for s in body] == ["Hostel"]


def test_stays_validation_and_404(client):
    sector_id = _sector_id(client)

    assert client.get("/sectors/999/stays").status_code == 404
    assert client.get(f"/sectors/{sector_id}/stays", params={"type": "castle"}).status_code == 422
    assert client.get(f"/sectors/{sector_id}/stays", params={"max_distance_km": 500}).status_code == 422


# --- GET /groups/{code}/sectors/{id}/stays --------------------------------


def _group_with_members(client, *names) -> str:
    code = client.post("/groups/", json={"name": "Trip"}).json()["share_code"]
    for name in names:
        client.post(f"/groups/{code}/members", json={"name": name})
    return code


def test_group_stays_defaults_guests_and_dates(client, db_session):
    sector_id = _sector_id(client)
    _add_stay(db_session, "Near", 41.2526, 0.9186)
    code = _group_with_members(client, "Ana", "Marc", "Lia")

    body = client.get(f"/groups/{code}/sectors/{sector_id}/stays").json()

    assert body["guests"] == 3  # the number of members
    checkin = date.fromisoformat(body["checkin"])
    assert checkin.weekday() == 5 and checkin > date.today()  # next Saturday
    assert date.fromisoformat(body["checkout"]) == checkin + timedelta(days=2)
    assert [s["stay"]["name"] for s in body["stays"]] == ["Near"]
    assert (body["sector_name"], body["crag_name"]) == ("Can Marges", "Siurana")


def test_group_stays_links_carry_dates_and_guests(client):
    sector_id = _sector_id(client)
    code = _group_with_members(client, "Ana")
    checkin = date.today() + timedelta(days=30)

    body = client.get(f"/groups/{code}/sectors/{sector_id}/stays",
                      params={"guests": 4, "nights": 3, "checkin": checkin.isoformat()}).json()

    checkout = (checkin + timedelta(days=3)).isoformat()
    airbnb = parse_qs(urlparse(body["links"]["airbnb"]).query)
    booking = parse_qs(urlparse(body["links"]["booking"]).query)
    assert airbnb["adults"] == ["4"] and airbnb["checkin"] == [checkin.isoformat()] and airbnb["checkout"] == [checkout]
    assert booking["group_adults"] == ["4"] and booking["checkout"] == [checkout]
    assert booking["ss"] == ["Siurana"]


def test_group_stays_rejects_past_checkin_and_unknowns(client):
    sector_id = _sector_id(client)
    code = _group_with_members(client, "Ana")
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    assert client.get(f"/groups/{code}/sectors/{sector_id}/stays", params={"checkin": yesterday}).status_code == 422
    assert client.get(f"/groups/NOPE2345/sectors/{sector_id}/stays").status_code == 404
    assert client.get(f"/groups/{code}/sectors/999/stays").status_code == 404
