import requests
from flask import current_app


def geocode(address_text, bias_lat=None, bias_lng=None):
    """Turn free text ('Thakur College, Kandivali') into {lat, lng, display_name}.
    Tries Photon (Komoot's free OSM-based geocoder, no key required) first,
    then falls back to Nominatim. Nominatim's public demo server can 403
    automated requests during busy periods, so Photon is the more reliable
    default for a student project hitting these free services directly."""
    result = _geocode_photon(address_text, bias_lat, bias_lng)
    if result:
        return result
    return _geocode_nominatim(address_text, bias_lat, bias_lng)

def _geocode_photon(address_text, bias_lat=None, bias_lng=None):
    try:
        params = {"q": address_text, "limit": 1}
        if bias_lat is not None and bias_lng is not None:
            params["lat"] = bias_lat
            params["lon"] = bias_lng
        resp = requests.get(
            "https://photon.komoot.io/api/",
            params=params,
            headers={"User-Agent": current_app.config["USER_AGENT"]},
            timeout=8,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            return None
        top = features[0]
        lng, lat = top["geometry"]["coordinates"]
        props = top.get("properties", {})
        name_parts = [props.get(k) for k in ("name", "city", "state", "country") if props.get(k)]
        return {"lat": lat, "lng": lng, "display_name": ", ".join(name_parts) or address_text}
    except Exception:
        return None


def _geocode_nominatim(address_text, bias_lat=None, bias_lng=None):
    params = {"q": address_text, "format": "json", "limit": 1}
    if bias_lat is not None and bias_lng is not None:
        # Rough ~2 degree box around the bias point, ~200km
        params["viewbox"] = f"{bias_lng-2},{bias_lat+2},{bias_lng+2},{bias_lat-2}"
        params["bounded"] = 1
    headers = {"User-Agent": current_app.config["USER_AGENT"], "Accept-Language": "en"}
    try:
        resp = requests.get(
            f"{current_app.config['NOMINATIM_URL']}/search", params=params, headers=headers, timeout=8
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        top = results[0]
        return {
            "lat": float(top["lat"]),
            "lng": float(top["lon"]),
            "display_name": top.get("display_name", address_text),
        }
    except Exception:
        return None


def reverse_geocode(lat, lng):
    """Turn coordinates back into a human-readable address (used by 'Use current location')."""
    params = {"lat": lat, "lon": lng, "format": "json"}
    headers = {"User-Agent": current_app.config["USER_AGENT"], "Accept-Language": "en"}
    resp = requests.get(
        f"{current_app.config['NOMINATIM_URL']}/reverse", params=params, headers=headers, timeout=8
    )
    resp.raise_for_status()
    return resp.json().get("display_name")
