"""API tests for /groups: CRUD for groups and members, and group search.

The matching rules themselves are unit-tested in test_group_matching.py;
these tests check the HTTP layer and the full flow end to end.
"""

import pytest

SIURANA = {"latitude": 41.2436, "longitude": 0.9186}      # 106 km from Barcelona
MONTSERRAT = {"latitude": 41.6047, "longitude": 1.8302}   # ~37 km from Barcelona


# --- Helpers ---------------------------------------------------------------


def _create_group(client, name="Trip") -> str:
    response = client.post("/groups/", json={"name": name})
    assert response.status_code == 201
    return response.json()["share_code"]


def _add_member(client, code, name, **prefs) -> dict:
    response = client.post(f"/groups/{code}/members", json={"name": name, **prefs})
    assert response.status_code == 201, response.json()
    return response.json()


def _add_sector(client, name, grade_min, grade_max, style="sport", coords=MONTSERRAT, approach=None):
    crag = client.post("/crags/", json={"name": f"Crag of {name}", "region": "R", **coords}).json()
    client.post("/sectors/", json={
        "name": name, "style": style, "grade_min": grade_min, "grade_max": grade_max,
        "crag_id": crag["id"], "approach_minutes": approach,
    })


# --- Groups and members ----------------------------------------------------


def test_create_group_returns_share_code(client):
    response = client.post("/groups/", json={"name": "Siurana trip"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Siurana trip"
    assert len(body["share_code"]) == 8
    assert body["members"] == []
    assert "id" not in body  # the share code is the public identifier


def test_get_group_is_case_insensitive(client):
    code = _create_group(client)

    assert client.get(f"/groups/{code.lower()}").status_code == 200


def test_unknown_group_is_404(client):
    assert client.get("/groups/NOPE2345").status_code == 404
    assert client.post("/groups/NOPE2345/members", json={"name": "Ana"}).status_code == 404


def test_add_member_and_read_group(client):
    code = _create_group(client)
    _add_member(client, code, "Ana", grade_min="6a", grade_max="7a", max_distance_km=150, styles=["sport"])

    members = client.get(f"/groups/{code}").json()["members"]

    assert len(members) == 1
    assert members[0]["name"] == "Ana"
    assert members[0]["styles"] == ["sport"]


def test_member_can_join_without_preferences(client):
    code = _create_group(client)

    member = _add_member(client, code, "Lia")

    assert member["grade_min"] is None
    assert member["max_approach_minutes"] is None
    assert member["styles"] == []


def test_member_max_approach_round_trips(client):
    code = _create_group(client)
    member = _add_member(client, code, "Ana", max_approach_minutes=20)

    members = client.get(f"/groups/{code}").json()["members"]
    assert members[0]["max_approach_minutes"] == 20

    response = client.put(f"/groups/{code}/members/{member['id']}", json={"name": "Ana", "max_approach_minutes": 35})
    assert response.status_code == 200

    members = client.get(f"/groups/{code}").json()["members"]
    assert members[0]["max_approach_minutes"] == 35


@pytest.mark.parametrize("value", [0, -5, 181, "abc"])
def test_invalid_max_approach_is_422(client, value):
    code = _create_group(client)

    response = client.post(f"/groups/{code}/members", json={"name": "Ana", "max_approach_minutes": value})

    assert response.status_code == 422
    assert client.get(f"/groups/{code}").json()["members"] == []


def test_invalid_preferences_are_422(client):
    code = _create_group(client)

    bad = [
        {"name": "Ana", "grade_min": "7a", "grade_max": "6a"},   # min harder than max
        {"name": "Ana", "grade_min": "6z", "grade_max": "7a"},   # not a grade
        {"name": "Ana", "grade_min": "6a"},                      # half a range
        {"name": "Ana", "styles": ["climbing"]},                 # unknown style
        {"name": "Ana", "max_distance_km": 0},                   # must be > 0
        {"name": ""},                                            # empty name
    ]
    for body in bad:
        assert client.post(f"/groups/{code}/members", json=body).status_code == 422, body


def test_update_member_replaces_everything(client):
    code = _create_group(client)
    ana = _add_member(client, code, "Ana", grade_min="6a", grade_max="7a", styles=["sport"])

    response = client.put(f"/groups/{code}/members/{ana['id']}", json={"name": "Ana B.", "max_distance_km": 80})

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Ana B."
    assert updated["max_distance_km"] == 80
    # PUT is a full replacement: fields left out are cleared, not kept.
    assert updated["grade_min"] is None
    assert updated["styles"] == []


def test_delete_member(client):
    code = _create_group(client)
    ana = _add_member(client, code, "Ana")

    assert client.delete(f"/groups/{code}/members/{ana['id']}").status_code == 204
    assert client.get(f"/groups/{code}").json()["members"] == []


def test_cannot_touch_a_member_of_another_group(client):
    # Knowing group A's code must not let you edit or delete group B's members.
    code_a = _create_group(client, "A")
    code_b = _create_group(client, "B")
    marc = _add_member(client, code_b, "Marc")

    assert client.put(f"/groups/{code_a}/members/{marc['id']}", json={"name": "Hacked"}).status_code == 404
    assert client.delete(f"/groups/{code_a}/members/{marc['id']}").status_code == 404
    assert client.get(f"/groups/{code_b}").json()["members"][0]["name"] == "Marc"


# --- Group search ----------------------------------------------------------


def test_search_with_no_members_explains_why(client):
    code = _create_group(client)

    body = client.get(f"/groups/{code}/search").json()

    assert body["results"] == []
    assert body["common_ground"] is False
    assert "member" in body["message"].lower()


def test_search_rejects_unknown_mode_and_fit(client):
    code = _create_group(client)

    assert client.get(f"/groups/{code}/search", params={"mode": "loose"}).status_code == 422
    assert client.get(f"/groups/{code}/search", params={"fit": "maybe"}).status_code == 422


def test_checkpoint_three_friends_scored(client):
    # The Stage 4 checkpoint: three friends, different grades and distances,
    # and a ranked list showing who each sector fits.
    _add_sector(client, "Easy Near", "5", "6b", coords=MONTSERRAT)
    _add_sector(client, "Mid Near", "6a", "7b", coords=MONTSERRAT)
    _add_sector(client, "Hard Far", "7a", "8c", coords=SIURANA)
    code = _create_group(client)
    _add_member(client, code, "Ana", grade_min="5+", grade_max="6b", max_distance_km=150)
    _add_member(client, code, "Marc", grade_min="6c", grade_max="7c", max_distance_km=60)
    _add_member(client, code, "Lia", grade_min="6a", grade_max="7a", max_distance_km=200)

    body = client.get(f"/groups/{code}/search", params={"mode": "scored"}).json()

    ranked = [(r["sector"]["name"], r["fit_count"]) for r in body["results"]]
    assert ranked == [("Mid Near", 3), ("Easy Near", 2), ("Hard Far", 1)]
    easy_near = body["results"][1]
    assert easy_near["misfits"] == [{"name": "Marc", "reason": "too easy"}]
    hard_far = body["results"][2]
    assert {m["name"]: m["reason"] for m in hard_far["misfits"]} == {
        "Ana": "too hard",
        "Marc": "too far (106 km > 60 km)",  # haversine Barcelona -> Siurana
    }
    assert body["common_ground"] is True  # Mid Near fits everyone


def test_strict_returns_only_sectors_for_everyone(client):
    _add_sector(client, "Mid Near", "6a", "7b")
    _add_sector(client, "Easy Near", "5", "6a")
    _add_sector(client, "Trad Near", "6a", "7b", style="trad")
    code = _create_group(client)
    _add_member(client, code, "Ana", grade_min="6a", grade_max="7a", styles=["sport", "trad"])
    _add_member(client, code, "Marc", grade_min="6b", grade_max="7b", styles=["sport"])

    body = client.get(f"/groups/{code}/search", params={"mode": "strict"}).json()

    assert [r["sector"]["name"] for r in body["results"]] == ["Mid Near"]
    assert body["filters"] == {
        "grade_min": "6b", "grade_max": "7a", "max_distance_km": None,
        "max_approach_minutes": None, "styles": ["sport"],
    }
    assert body["results"][0]["fits"] == ["Ana", "Marc"]


def test_strict_respects_shortest_approach_limit(client):
    _add_sector(client, "Short", "6a", "7a", approach=10)
    _add_sector(client, "Long", "6a", "7a", approach=30)
    _add_sector(client, "Unknown", "6a", "7a", approach=None)
    code = _create_group(client)
    _add_member(client, code, "Ana", max_approach_minutes=15)
    _add_member(client, code, "Ben", max_approach_minutes=30)

    body = client.get(f"/groups/{code}/search", params={"mode": "strict"}).json()

    assert sorted(r["sector"]["name"] for r in body["results"]) == ["Short", "Unknown"]
    assert body["filters"]["max_approach_minutes"] == 15


def test_scored_explains_approach_too_long(client):
    _add_sector(client, "Long", "6a", "7a", approach=30)
    code = _create_group(client)
    _add_member(client, code, "Ana", max_approach_minutes=15)
    _add_member(client, code, "Ben", max_approach_minutes=30)

    [result] = client.get(f"/groups/{code}/search", params={"mode": "scored"}).json()["results"]

    assert (result["fit_count"], result["member_count"]) == (1, 2)
    [misfit] = result["misfits"]
    assert misfit["name"] == "Ana"
    assert misfit["reason"].startswith("approach too long")


def test_strict_every_sector_has_too_long_an_approach(client):
    _add_sector(client, "Long", "6a", "7a", approach=30)
    _add_sector(client, "Longer", "6a", "7a", approach=45)
    code = _create_group(client)
    _add_member(client, code, "Ana", max_approach_minutes=15)

    response = client.get(f"/groups/{code}/search", params={"mode": "strict"})

    assert response.status_code == 200
    body = response.json()
    assert body["common_ground"] is True
    assert body["results"] == []
    assert body["message"] == "The group agrees on filters, but no sector matches them."


def test_strict_no_common_ground(client):
    _add_sector(client, "Anything", "4", "9a")
    code = _create_group(client)
    _add_member(client, code, "Ana", grade_min="5", grade_max="6a")
    _add_member(client, code, "Marc", grade_min="7a", grade_max="8a")

    response = client.get(f"/groups/{code}/search", params={"mode": "strict"})

    assert response.status_code == 200  # a result, not an error
    body = response.json()
    assert body["common_ground"] is False
    assert body["results"] == []
    assert "Ana" in body["message"] and "Marc" in body["message"]


def test_fit_cover_is_stricter_than_overlap(client):
    _add_sector(client, "Partial", "6c", "8a")
    code = _create_group(client)
    _add_member(client, code, "Ana", grade_min="6a", grade_max="7a")

    overlap = client.get(f"/groups/{code}/search", params={"fit": "overlap"}).json()
    cover = client.get(f"/groups/{code}/search", params={"fit": "cover"}).json()

    assert overlap["results"][0]["fits"] == ["Ana"]
    assert cover["results"][0]["fits"] == []
