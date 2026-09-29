"""Tests for the OpenStreetMap import helpers. The network is never used:
fetch_overpass() takes `post` and `sleep` as parameters, so tests pass fakes.
"""

from types import SimpleNamespace

import httpx
import pytest

from app.models import StayType
from app.services import overpass
from app.services.overpass import (
    OverpassError,
    ParsedStay,
    build_query,
    fetch_overpass,
    find_duplicate,
    parse_elements,
)


@pytest.fixture(autouse=True)
def temp_cache(tmp_path, monkeypatch):
    # Never read or write the real backend/.cache during tests.
    monkeypatch.setattr(overpass, "CACHE_DIR", tmp_path)


class FakePost:
    """Plays back a list of outcomes: a status code, or an exception to raise."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, url, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, json={"elements": []} if outcome == 200 else None,
                              request=httpx.Request("POST", url))


# --- fetch_overpass: retries and cache ------------------------------------


def test_fetch_retries_on_429_then_succeeds():
    post, waits = FakePost(429, 503, 200), []

    data = fetch_overpass("q", post=post, sleep=waits.append)

    assert data == {"elements": []}
    assert post.calls == 3
    assert waits == [5, 10]  # exponential backoff between attempts


def test_fetch_rotates_to_the_fallback_server():
    urls = []

    def post(url, **kwargs):
        urls.append(url)
        status = 503 if len(urls) == 1 else 200
        return httpx.Response(status, json={"elements": []}, request=httpx.Request("POST", url))

    fetch_overpass("q", post=post, sleep=lambda s: None)

    assert urls == overpass.OVERPASS_URLS[:2]  # main server failed, mirror answered


def test_fetch_retries_on_timeout():
    post = FakePost(httpx.ReadTimeout("slow"), 200)

    fetch_overpass("q", post=post, sleep=lambda s: None)

    assert post.calls == 2


def test_fetch_does_not_retry_a_bad_query():
    post = FakePost(400)

    with pytest.raises(OverpassError, match="400"):
        fetch_overpass("q", post=post, sleep=lambda s: None)
    assert post.calls == 1  # a 400 can't succeed on retry


def test_fetch_gives_up_after_retries():
    post = FakePost(503, 503, 503, 503)

    with pytest.raises(OverpassError, match="4 attempts"):
        fetch_overpass("q", retries=3, post=post, sleep=lambda s: None)


def test_fetch_uses_the_cache_on_second_call():
    post = FakePost(200)  # only ONE outcome: a second network call would fail

    fetch_overpass("same query", post=post, sleep=lambda s: None)
    fetch_overpass("same query", post=post, sleep=lambda s: None)

    assert post.calls == 1


def test_build_query_contains_the_point_and_radius():
    query = build_query(41.2436, 0.9186, 15000)

    assert "around:15000,41.24360,0.91860" in query
    assert "camp_site" in query and "out center" in query


# --- parse_elements: messy OSM data ---------------------------------------


def test_parse_node_and_way_with_center():
    elements = [
        {"type": "node", "id": 1, "lat": 41.25, "lon": 0.93,
         "tags": {"tourism": "camp_site", "name": "Càmping Siurana", "website": "https://example.org"}},
        {"type": "way", "id": 2, "center": {"lat": 41.26, "lon": 0.90},
         "tags": {"tourism": "alpine_hut", "name:ca": "Refugi"}},
    ]

    stays, skipped = parse_elements(elements)

    assert skipped == 0
    assert stays[0] == ParsedStay("Càmping Siurana", StayType.CAMPSITE, 41.25, 0.93,
                                  "https://example.org", "osm:node/1")
    # A way uses its centre; name falls back to name:ca; huts become refuges.
    assert (stays[1].latitude, stays[1].name, stays[1].type) == (41.26, "Refugi", StayType.REFUGE)
    assert stays[1].external_id == "osm:way/2"


def test_parse_skips_unusable_places():
    elements = [
        {"type": "node", "id": 1, "lat": 41.0, "lon": 1.0, "tags": {"tourism": "camp_site"}},           # no name
        {"type": "node", "id": 2, "lat": 41.0, "lon": 1.0, "tags": {"tourism": "hotel", "name": "H"}},  # not a stay type we keep
        {"type": "way", "id": 3, "tags": {"tourism": "hostel", "name": "No coords"}},                   # no center
        {"type": "node", "id": 4, "lat": 41.0, "lon": 1.0, "tags": {"tourism": "hostel", "name": "  "}}, # blank name
    ]

    stays, skipped = parse_elements(elements)

    assert stays == []
    assert skipped == 4


# --- find_duplicate: OSM vs curated ---------------------------------------


def _existing(name, lat, lon):
    return SimpleNamespace(name=name, latitude=lat, longitude=lon)


def _parsed(name, lat, lon):
    return ParsedStay(name, StayType.CAMPSITE, lat, lon, None, "osm:node/9")


def test_duplicate_when_same_spot_even_with_a_different_name():
    curated = [_existing("Siurana village campsite", 41.2560, 0.9310)]

    assert find_duplicate(_parsed("Camping Municipal", 41.2561, 0.9311), curated) is curated[0]  # ~15 m


def test_duplicate_when_nearby_and_similar_name_ignoring_accents():
    curated = [_existing("Càmping Siurana", 41.2560, 0.9310)]

    assert find_duplicate(_parsed("camping siurana", 41.2575, 0.9310), curated) is curated[0]  # ~170 m


def test_not_a_duplicate_when_far_or_unrelated():
    curated = [_existing("Càmping Siurana", 41.2560, 0.9310)]

    assert find_duplicate(_parsed("Càmping Siurana", 41.30, 0.93), curated) is None      # ~5 km away
    assert find_duplicate(_parsed("Alberg del Poble", 41.2575, 0.9310), curated) is None  # near, other name
