from app.geo import haversine_km


def test_known_distance_barcelona_to_siurana():
    d = haversine_km(41.3874, 2.1686, 41.2436, 0.9186)
    assert 100 < d < 120   # loose bounds — we're checking it's in the right
                           # ballpark, not pinning an exact float


def test_zero_distance_same_point():
    assert haversine_km(41.3874, 2.1686, 41.3874, 2.1686) == 0
