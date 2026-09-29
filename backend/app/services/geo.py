import math

EARTH_RADIUS_KM = 6371.0

# Everyone searches from Barcelona for now (lat, lon).
BARCELONA = (41.3874, 2.1686)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line ('as the crow flies') distance in km between two
    points given in decimal  degrees."""
    # TODO: convert all four inputs from degrees to radians using math.radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = EARTH_RADIUS_KM * c
    return distance
