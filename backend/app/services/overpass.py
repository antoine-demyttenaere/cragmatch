"""OpenStreetMap stays via the Overpass API.

Everything that talks to Overpass or interprets its data lives here, so the
import script stays short and the pieces can be tested without the network.

The HTTP call follows the same habits as the Anthropic/Voyage calls in
Stage 3 (Step 5.6): a timeout, retries with backoff for errors that can
succeed on a second try, and an on-disk cache so re-running the import
doesn't hit a free, shared service again.
"""

import hashlib
import json
import logging
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from app.models import StayType
from app.services.geo import haversine_km

logger = logging.getLogger(__name__)

# Free public instances. They're often busy (429/504), so retries rotate
# through them: attempt 1 -> first, attempt 2 -> second, attempt 3 -> first...
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
# Overpass asks clients to identify themselves.
USER_AGENT = "CragMatch/0.1 (learning project; one-off imports)"

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "overpass"  # backend/.cache/overpass
CACHE_TTL_SECONDS = 7 * 24 * 3600

# OSM tourism=* tag -> our StayType.
TOURISM_TO_TYPE = {
    "camp_site": StayType.CAMPSITE,
    "hostel": StayType.HOSTEL,
    "alpine_hut": StayType.REFUGE,
    "wilderness_hut": StayType.REFUGE,
    "guest_house": StayType.GUESTHOUSE,
    "apartment": StayType.APARTMENT,
}

# Retrying these can succeed: rate limited, or the server is busy/down.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OverpassError(Exception):
    pass


def build_query(lat: float, lon: float, radius_m: int) -> str:
    """Overpass QL: every stay-like place within radius_m of a point.

    `nwr` = nodes, ways and relations (a campsite can be a single point or
    an outlined area). `out center` gives areas a centre coordinate.
    """
    tourism = "|".join(TOURISM_TO_TYPE)
    return (
        "[out:json][timeout:50];"
        f'nwr["tourism"~"^({tourism})$"](around:{radius_m},{lat:.5f},{lon:.5f});'
        "out center tags;"
    )


def _cache_path(query: str) -> Path:
    return CACHE_DIR / f"{hashlib.sha256(query.encode()).hexdigest()[:16]}.json"


def fetch_overpass(
    query: str,
    *,
    retries: int = 3,
    timeout: float = 60.0,
    use_cache: bool = True,
    post: Callable[..., httpx.Response] = httpx.post,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Run an Overpass query, with cache, timeout and retries.

    `post` and `sleep` are parameters so tests can pass fakes: no network,
    no real waiting.
    """
    path = _cache_path(query)
    if use_cache and path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL_SECONDS:
        logger.info("Overpass cache hit: %s", path.name)
        return json.loads(path.read_text(encoding="utf-8"))

    for attempt in range(retries + 1):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            response = post(
                url, data={"data": query}, timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        else:
            if response.status_code == 200:
                data = response.json()
                if use_cache:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data), encoding="utf-8")
                return data
            if response.status_code not in RETRYABLE_STATUS:
                # A 400 means our query is wrong: retrying can't fix that.
                raise OverpassError(f"Overpass returned {response.status_code}: {response.text[:200]}")
            error = f"HTTP {response.status_code}"

        if attempt < retries:
            # 5s, 10s, 20s, capped at 30s. A 429 from a shared server means
            # "slow down"; a 1-2 second pause is too short to help.
            wait = min(5 * 2 ** attempt, 30)
            logger.warning("Overpass attempt %d at %s failed (%s), retrying in %ds", attempt + 1, url, error, wait)
            sleep(wait)

    raise OverpassError(f"Overpass failed after {retries + 1} attempts: {error}")


@dataclass
class ParsedStay:
    name: str
    type: StayType
    latitude: float
    longitude: float
    url: str | None
    external_id: str


def parse_elements(elements: list[dict]) -> tuple[list[ParsedStay], int]:
    """Turn raw Overpass elements into ParsedStays. Returns (stays, skipped).

    OSM data is messy: skip places with no usable name (useless in a list)
    or no coordinates, and try several tags for names and websites.
    """
    stays, skipped = [], 0
    for el in elements:
        tags = el.get("tags", {})
        stay_type = TOURISM_TO_TYPE.get(tags.get("tourism"))
        name = next(
            (tags[k].strip() for k in ("name", "name:ca", "name:es", "name:en") if tags.get(k, "").strip()),
            None,
        )
        # Nodes have lat/lon; ways and relations have a "center" (out center).
        point = el if "lat" in el else el.get("center", {})
        lat, lon = point.get("lat"), point.get("lon")

        if stay_type is None or name is None or lat is None or lon is None:
            skipped += 1
            continue

        url = tags.get("website") or tags.get("contact:website") or tags.get("url")
        stays.append(ParsedStay(
            name=name[:200], type=stay_type, latitude=lat, longitude=lon,
            url=url[:500] if url else None,
            external_id=f"osm:{el['type']}/{el['id']}",
        ))
    return stays, skipped


def _normalize(name: str) -> str:
    # "Càmping Siurana" -> "camping siurana": no accents, lower case.
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(ascii_name.lower().split())


def find_duplicate(parsed: ParsedStay, existing: list, same_place_m: float = 50, similar_name_m: float = 300):
    """An existing stay that is probably the same place, or None.

    Same place if it's within 50 m (almost certainly the same spot), or
    within 300 m with a similar name (one name contains the other).
    """
    new_name = _normalize(parsed.name)
    for stay in existing:
        distance_m = haversine_km(parsed.latitude, parsed.longitude, stay.latitude, stay.longitude) * 1000
        if distance_m <= same_place_m:
            return stay
        old_name = _normalize(stay.name)
        if distance_m <= similar_name_m and (new_name in old_name or old_name in new_name):
            return stay
    return None
