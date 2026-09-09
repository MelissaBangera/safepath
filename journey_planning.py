from flask import Blueprint, current_app, jsonify, request

from services.geocoding import geocode
from services.routing import get_routes
from services.safety_scoring import score_route, haversine_m

bp = Blueprint("journey_planning", __name__, url_prefix="/api/journey")

MAX_REASONABLE_DISTANCE_M = 300_000  # 300 km — beyond this, treat as a bad geocode match


def _resolve_point(payload_key, data, bias=None):
    """Accepts either {"lat": .., "lng": ..} or a free-text address string
    (matches how the frontend's 'Current Location' / 'Destination' inputs work)."""
    value = data.get(payload_key)
    if value is None:
        return None, f"'{payload_key}' is required"
    if isinstance(value, dict) and "lat" in value and "lng" in value:
        try:
            return {"lat": float(value["lat"]), "lng": float(value["lng"])}, None
        except (TypeError, ValueError):
            return None, f"'{payload_key}' lat/lng must be numbers"
    if isinstance(value, str) and value.strip():
        bias_lat, bias_lng = (bias["lat"], bias["lng"]) if bias else (None, None)
        result = geocode(value.strip(), bias_lat=bias_lat, bias_lng=bias_lng)
        if not result:
            return None, f"Could not find a location for '{value}'"
        return {"lat": result["lat"], "lng": result["lng"], "text": result.get("display_name", value)}, None
    return None, f"Invalid format for '{payload_key}' — provide a lat/lng object or an address string"


@bp.route("/geocode", methods=["GET"])
def geocode_lookup():
    """
    Query: ?q=<free text address>
    Used by the Community "Report an Issue" form to turn a typed location
    into coordinates before saving a SafetyReport.
    """
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "'q' query parameter is required"}), 400
    result = geocode(query)
    if not result:
        return jsonify({"error": f"Could not find a location for '{query}'"}), 404
    return jsonify(result)


@bp.route("/plan", methods=["POST"])
def plan_journey():
    """
    Body: { "origin": {"lat":.., "lng":..} | "address string",
            "destination": {"lat":.., "lng":..} | "address string" }

    Powers the "Find Safer Route" button. Returns up to two route options,
    each labeled "safer" or "fastest", with distance, ETA and a 0-100 safety
    score — this is exactly the shape of the .route-option cards in the UI.
    """
    data = request.get_json(silent=True) or {}

    origin, err = _resolve_point("origin", data)
    if err:
        return jsonify({"error": err}), 400
    destination, err = _resolve_point("destination", data, bias=origin)
    if err:
        return jsonify({"error": err}), 400

    # Sanity check: if geocoding matched something absurdly far away, it's almost
    # certainly the wrong place (e.g. a same-named location on another continent)
    # rather than a genuinely long journey request.
    straight_line_m = haversine_m(origin["lat"], origin["lng"], destination["lat"], destination["lng"])
    if straight_line_m > MAX_REASONABLE_DISTANCE_M:
        return jsonify({
            "error": (
                f"The destination matched a location {straight_line_m/1000:.0f} km away, "
                "which is probably not what you meant. Try being more specific, e.g. "
                "'Gateway of India, Mumbai' instead of 'gate of india'."
            )
        }), 400

    try:
        raw_routes = get_routes(origin, destination, alternatives=True)
    except Exception as exc:
        current_app.logger.exception("Routing failed")
        return jsonify({"error": f"Could not compute a route: {exc}"}), 502

    if not raw_routes:
        return jsonify({"error": "No route found between these points"}), 404

    scored = []
    for r in raw_routes:
        scored.append({
            "geometry": r["geometry"],
            "distance_m": round(r["distance_m"]),
            "duration_s": round(r["duration_s"]),
            "safety_score": score_route(r["geometry"]),
        })

    fastest = min(scored, key=lambda r: r["duration_s"])
    safest = max(scored, key=lambda r: r["safety_score"])

    options = []
    safest["label"] = "safer"
    options.append(safest)
    if safest is not fastest:
        fastest["label"] = "fastest"
        options.append(fastest)

    return jsonify({"origin": origin, "destination": destination, "routes": options})
