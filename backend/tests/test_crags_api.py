def test_create_and_get_crag(client):
    response = client.post("/crags/", json={
        "name": "Test Crag",
        "region": "Test Region",
        "latitude": 41.0,
        "longitude": 1.0,
    })
    assert response.status_code == 201
    crag_id = response.json()["id"]

    response = client.get(f"/crags/{crag_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Crag"


def test_list_crags_starts_empty(client):
    # Confirms test isolation: no leftover data from the previous test,
    # and none of your real seeded dev data either.
    response = client.get("/crags/")
    assert response.json() == []


def test_get_nonexistent_crag_returns_404(client):
    response = client.get("/crags/999")
    assert response.status_code == 404
