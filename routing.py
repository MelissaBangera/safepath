import requests
from flask import current_app

# OSRM profile -> path prefix on the FOSSGIS-hosted routing.openstreetmap.de
# demo server. Unlike the default router.project-osrm.org deployment (which
# only actually runs the car profile and silently answers every profile with
# driving-mode data), this server runs genuinely separate car/bike/foot
# profiles, each under its own "/routed-<mode>" prefix.
_PROFILE_PREFIXES = {
    "foot": "routed-foot",
    "driving": "routed-car",
    "bike": "routed-bike",
}


def get_routes(origin, destination, alternatives=True, profile="foot"):
    """
    origin/destination: {"lat": float, "lng": float}
    profile: "foot" (default, since this is a personal-safety walking/commute
             app), "driving", or "bike".

    Returns a list of route dicts: {geometry: [[lat, lng], ...], distance_m, duration_s}
    using OSRM's free public routing engine.
    """
    coords = f"{origin['lng']},{origin['lat']};{destination['lng']},{destination['lat']}"
    prefix = _PROFILE_PREFIXES.get(profile, "routed-foot")
    url = f"{current_app.config['OSRM_URL']}/{prefix}/route/v1/{profile}/{coords}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "true" if alternatives else "false",
        "steps": "false",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM error: {data.get('message', data.get('code'))}")

    routes = []
    for r in data["routes"]:
        # GeoJSON coordinates come as [lng, lat] — flip to [lat, lng] to match
        # the {lat, lng} convention the rest of this API (and Leaflet/Google
        # Maps JS on the frontend) expects.
        coords_latlng = [[pt[1], pt[0]] for pt in r["geometry"]["coordinates"]]
        routes.append({
            "geometry": coords_latlng,
            "distance_m": r["distance"],
            "duration_s": r["duration"],
        })
    return routes
