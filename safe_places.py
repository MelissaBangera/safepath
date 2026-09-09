import requests
from flask import current_app
from services.safety_scoring import haversine_m

# Fallback data used only when the caller doesn't have a location yet
# (e.g. geolocation permission hasn't been granted), or when every public
# Overpass mirror is down/unreachable. Real results come from
# find_nearby_places() below otherwise.
DEMO_PLACES = [
    {
        "id": "demo-1",
        "name": "Central Police Station",
        "type": "police",
        "distance": "1.2 km",
        "status": "Open 24 hours",
        "latitude": 19.0760,
        "longitude": 72.8777
    },
    {
        "id": "demo-2",
        "name": "City General Hospital",
        "type": "hospital",
        "distance": "2.1 km",
        "status": "Emergency available",
        "latitude": 19.0820,
        "longitude": 72.8840
    },
    {
        "id": "demo-3",
        "name": "Community Pharmacy",
        "type": "pharmacy",
        "distance": "800 m",
        "status": "Open until 11 PM",
        "latitude": 19.0720,
        "longitude": 72.8710
    },
    {
        "id": "demo-4",
        "name": "Safe Community Centre",
        "type": "safe-place",
        "distance": "1.7 km",
        "status": "Public help point",
        "latitude": 19.0800,
        "longitude": 72.8740
    }
]

# type -> OSM (key, value) tag to search for
_TYPE_TAGS = {
    "police": ("amenity", "police"),
    "hospital": ("amenity", "hospital"),
    "pharmacy": ("amenity", "pharmacy"),
    "safe-place": ("amenity", "community_centre"),
}

# Tried in order; first mirror that responds successfully wins. Public
# Overpass infrastructure is volunteer-run and can be flaky/overloaded or
# 406/timeout intermittently, so we don't depend on any single one.
OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def _format_distance(distance_m):
    if distance_m < 1000:
        return f"{round(distance_m / 10) * 10} m"
    return f"{distance_m / 1000:.1f} km"


def find_nearby_places(lat, lng, radius=3000, place_type=None):
    """Query Overpass for real police/hospital/pharmacy/community-centre
    points near (lat, lng) and return them sorted by actual distance.
    Falls back to DEMO_PLACES if every mirror fails."""
    types_to_query = (
        [place_type] if place_type and place_type in _TYPE_TAGS
        else list(_TYPE_TAGS.keys())
    )
    filters = "".join(
        f'node["{_TYPE_TAGS[t][0]}"="{_TYPE_TAGS[t][1]}"](around:{radius},{lat},{lng});'
        for t in types_to_query
    )
    query = f"[out:json][timeout:15];({filters});out body;"

    headers = {
        "User-Agent": current_app.config["USER_AGENT"],
        "Accept-Encoding": "gzip, deflate, br",
    }

    resp = None
    last_exc = None
    for mirror_url in OVERPASS_MIRRORS:
        try:
            resp = requests.post(mirror_url, data={"data": query}, headers=headers, timeout=12)
            resp.raise_for_status()
            break  # success — stop trying other mirrors
        except Exception as exc:
            last_exc = exc
            resp = None
            continue

    if resp is None:
        current_app.logger.warning(
            f"All Overpass mirrors failed, falling back to demo data: {last_exc}"
        )
        return [p for p in DEMO_PLACES if not place_type or p["type"] == place_type]

    elements = resp.json().get("elements", [])
    scored = []
    for el in elements:
        tags = el.get("tags", {})
        p_type = next(
            (t for t, (k, v) in _TYPE_TAGS.items() if tags.get(k) == v),
            "safe-place",
        )
        distance_m = haversine_m(lat, lng, el["lat"], el["lon"])
        scored.append((distance_m, {
            "id": el["id"],
            "name": tags.get("name") or p_type.replace("-", " ").title(),
            "type": p_type,
            "distance": _format_distance(distance_m),
            "status": tags.get("opening_hours") or "Hours not listed",
            "latitude": el["lat"],
            "longitude": el["lon"],
        }))
    scored.sort(key=lambda pair: pair[0])
    return [place for _, place in scored]
