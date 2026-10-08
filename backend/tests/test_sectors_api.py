def _create_crag(client, **overrides):
    """Helper: create a crag via the API and return its id.
    Defaults describe a crag near Barcelona; override any field as needed.
    """
    payload = {
        "name": "Test Crag",
        "region": "Test Region",
        "latitude": 41.3874,
        "longitude": 2.1686,
    }
    payload.update(overrides)
    response = client.post("/crags/", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _create_sector(client, crag_id, **overrides):
    payload = {
        "name": "Test Sector",
        "style": "sport",
        "grade_min": "6a",
        "grade_max": "7a",
        "crag_id": crag_id,
    }
    payload.update(overrides)
    return client.post("/sectors/", json=payload)


def test_create_sector_with_valid_crag_id(client):
    crag_id = _create_crag(client)
    response = _create_sector(client, crag_id)
    assert response.status_code == 201
    body = response.json()
    assert body["crag_id"] == crag_id
    assert body["name"] == "Test Sector"


def test_create_sector_with_invalid_crag_id_returns_400(client):
    response = _create_sector(client, crag_id=999)
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid crag_id"


def test_search_by_grade_range_matches_overlapping_sector(client):
    crag_id = _create_crag(client)
    _create_sector(client, crag_id, name="Easy-ish", grade_min="5+", grade_max="6b")

    response = client.get("/sectors/search", params={"min_grade": "6a", "max_grade": "7a"})
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert "Easy-ish" in names


def test_search_by_grade_range_excludes_non_overlapping_sector(client):
    crag_id = _create_crag(client)
    _create_sector(client, crag_id, name="Way Too Hard", grade_min="8a", grade_max="9a")

    response = client.get("/sectors/search", params={"min_grade": "6a", "max_grade": "7a"})
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert "Way Too Hard" not in names


def test_search_with_invalid_grade_returns_400(client):
    response = client.get("/sectors/search", params={"min_grade": "6a", "max_grade": "7z"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid grade"


def test_search_filters_by_style(client):
    crag_id = _create_crag(client)
    _create_sector(client, crag_id, name="Sport Sector", style="sport", grade_min="6a", grade_max="7a")
    _create_sector(client, crag_id, name="Trad Sector", style="trad", grade_min="6a", grade_max="7a")

    response = client.get(
        "/sectors/search",
        params={"min_grade": "6a", "max_grade": "7a", "style": "trad"},
    )
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert names == ["Trad Sector"]


def test_search_filters_by_distance(client):
    # A crag right in Barcelona (near the search origin)...
    close_crag_id = _create_crag(client, name="Close Crag", latitude=41.3874, longitude=2.1686)
    _create_sector(client, close_crag_id, name="Close Sector", grade_min="6a", grade_max="7a")

    # ...and one far away (Siurana's real coordinates, ~110km out).
    far_crag_id = _create_crag(client, name="Far Crag", latitude=41.2436, longitude=0.9186)
    _create_sector(client, far_crag_id, name="Far Sector", grade_min="6a", grade_max="7a")

    response = client.get(
        "/sectors/search",
        params={
            "min_grade": "6a",
            "max_grade": "7a",
            "origin_lat": 41.3874,
            "origin_lon": 2.1686,
            "max_distance_km": 50,
        },
    )
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert "Close Sector" in names
    assert "Far Sector" not in names


def test_search_without_distance_params_ignores_distance(client):
    far_crag_id = _create_crag(client, name="Far Crag", latitude=41.2436, longitude=0.9186)
    _create_sector(client, far_crag_id, name="Far Sector", grade_min="6a", grade_max="7a")

    response = client.get("/sectors/search", params={"min_grade": "6a", "max_grade": "7a"})
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert "Far Sector" in names


def test_create_sector_with_approach_minutes(client):
    crag_id = _create_crag(client)
    response = _create_sector(client, crag_id, approach_minutes=20)
    assert response.status_code == 201
    assert response.json()["approach_minutes"] == 20

    fetched = client.get(f"/sectors/{response.json()['id']}")
    assert fetched.json()["approach_minutes"] == 20


def test_approach_minutes_defaults_to_unknown(client):
    crag_id = _create_crag(client)
    response = _create_sector(client, crag_id)
    assert response.status_code == 201
    assert response.json()["approach_minutes"] is None


def test_negative_approach_minutes_is_422(client):
    crag_id = _create_crag(client)
    response = _create_sector(client, crag_id, approach_minutes=-1)
    assert response.status_code == 422
