import math
from datetime import datetime, timezone

import requests
from flask import current_app
from sqlalchemy import select

from extensions import db
from models import SafetyReport


def haversine_m(lat1, lng1, lat2, lng2):
    """Distance in meters between two lat/lng points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _route_bbox(geometry, pad_deg=0.01):
    lats = [p[0] for p in geometry]
    lngs = [p[1] for p in geometry]
    return (min(lats) - pad_deg, min(lngs) - pad_deg, max(lats) + pad_deg, max(lngs) + pad_deg)


def _sample_points(geometry, every_n=5):
    """Routes can have hundreds of vertices — downsample so distance checks stay fast."""
    sampled = geometry[::every_n]
    return sampled or geometry

OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

def _fetch_safety_pois(geometry):
    south, west, north, east = _route_bbox(geometry)
    query = f"""
    [out:json][timeout:15];
    (
      node["highway"="street_lamp"]({south},{west},{north},{east});
      node["amenity"="police"]({south},{west},{north},{east});
      node["amenity"="hospital"]({south},{west},{north},{east});
      node["shop"]({south},{west},{north},{east});
    );
    out body;
    """
    headers = {
        "User-Agent": current_app.config["USER_AGENT"],
        "Accept-Encoding": "gzip, deflate, br",
    }
    for mirror_url in OVERPASS_MIRRORS:
        try:
            resp = requests.post(mirror_url, data={"data": query}, headers=headers, timeout=12)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception:
            continue
    # All mirrors failed — degrade gracefully (neutral score contribution)
    return []

def _poi_score(geometry, pois, buffer_m):
    if not pois:
        return 0  # no data available — stay neutral
    sample = _sample_points(geometry)
    lamp_hits = police_hits = hospital_hits = shop_hits = 0
    for lat, lng in sample:
        for poi in pois:
            if haversine_m(lat, lng, poi["lat"], poi["lon"]) <= buffer_m:
                tags = poi.get("tags", {})
                if tags.get("highway") == "street_lamp":
                    lamp_hits += 1
                elif tags.get("amenity") == "police":
                    police_hits += 1
                elif tags.get("amenity") == "hospital":
                    hospital_hits += 1
                elif "shop" in tags:
                    shop_hits += 1
    score = 0
    score += min(lamp_hits, 40) * 0.5     # up to +20 — lighting
    score += min(police_hits, 4) * 5      # up to +20 — nearby help
    score += min(hospital_hits, 4) * 3    # up to +12 — nearby help
    score += min(shop_hits, 30) * 0.2     # up to +6  — foot traffic
    return round(score, 1)


def _incident_penalty(geometry, buffer_m):
    """Penalize routes that pass near community-reported incidents, weighted
    by severity and recency."""
    reports = db.session.execute(select(SafetyReport)).scalars().all()
    if not reports:
        return 0
    sample = _sample_points(geometry)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    penalty = 0.0
    for report in reports:
        for lat, lng in sample:
            if haversine_m(lat, lng, report.latitude, report.longitude) <= buffer_m:
                age_days = max((now - report.created_at).days, 0)
                recency_factor = max(0.3, 1 - (age_days / 180))
                penalty += report.severity * 3 * recency_factor
                break  # count each report once per route
    return round(penalty, 1)


def _time_of_day_modifier():
    hour = datetime.now().hour
    night_start = current_app.config["NIGHT_START_HOUR"]
    night_end = current_app.config["NIGHT_END_HOUR"]
    is_night = hour >= night_start or hour < night_end
    return 0.85 if is_night else 1.0


def score_route(geometry):
    """
    0-100 safety score for a route:
        70 (base) + poi_bonus (lighting / police / hospitals / foot traffic)
                  - incident_penalty (community-reported issues near the route)
    scaled down slightly at night.
    """
    buffer_incidents = current_app.config["INCIDENT_SEARCH_RADIUS_M"]
    buffer_poi = current_app.config["POI_SEARCH_BUFFER_M"]

    pois = _fetch_safety_pois(geometry)
    poi_bonus = _poi_score(geometry, pois, buffer_poi) * _time_of_day_modifier()
    incident_penalty = _incident_penalty(geometry, buffer_incidents)

    score = 70 + poi_bonus - incident_penalty
    return max(0, min(100, round(score)))
