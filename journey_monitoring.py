from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

from extensions import db
from models import EmergencyContact, Journey, LocationPing, SafetyReport

bp = Blueprint("journey_monitoring", __name__, url_prefix="/api/journey")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_journey_or_404(journey_id):
    journey = db.session.get(Journey, journey_id)
    if journey is None:
        return None, (jsonify({"error": "Journey not found."}), 404)
    return journey, None


@bp.route("/start", methods=["POST"])
def start_journey():
    """
    Body: { "user_id": optional str,
            "origin": {"lat":.., "lng":.., "text":..},
            "destination": {"lat":.., "lng":.., "text":..},
            "route_geometry": [[lat,lng],...],
            "route_distance_m": number,
            "route_duration_s": number,
            "safety_score": int,
            "route_label": "safer" | "fastest" }

    Called when the user taps "Start Safer Journey". Creates an active session
    and starts the safety timer server-side (expected_arrival).
    """
    data = request.get_json(silent=True) or {}
    required = ["origin", "destination", "route_duration_s"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    origin = data["origin"]
    destination = data["destination"]

    # Validate origin/destination have lat and lng
    for key, point in [("origin", origin), ("destination", destination)]:
        if not isinstance(point, dict) or "lat" not in point or "lng" not in point:
            return jsonify({"error": f"'{key}' must have 'lat' and 'lng' fields."}), 400

    try:
        duration_s = float(data["route_duration_s"])
    except (TypeError, ValueError):
        return jsonify({"error": "'route_duration_s' must be a number."}), 400

    now = _now()
    journey = Journey(
        user_id=data.get("user_id"),
        origin_lat=float(origin["lat"]),
        origin_lng=float(origin["lng"]),
        origin_text=origin.get("text"),
        destination_lat=float(destination["lat"]),
        destination_lng=float(destination["lng"]),
        destination_text=destination.get("text"),
        route_geometry=data.get("route_geometry"),
        route_distance_m=data.get("route_distance_m"),
        route_duration_s=duration_s,
        safety_score=data.get("safety_score"),
        route_label=data.get("route_label", "safer"),
        status="active",
        started_at=now,
        expected_arrival=now + timedelta(seconds=duration_s),
    )
    db.session.add(journey)
    db.session.commit()
    return jsonify(journey.to_dict()), 201


@bp.route("/<journey_id>/status", methods=["GET"])
def journey_status(journey_id):
    """Poll this to drive the live journey panel (timer, ETA, overdue flag)."""
    journey, err = _get_journey_or_404(journey_id)
    if err:
        return err
    grace = current_app.config["GRACE_PERIOD_SECONDS"]
    return jsonify(journey.to_dict(grace_seconds=grace))


@bp.route("/<journey_id>/ping", methods=["POST"])
def ping_location(journey_id):
    """
    Body: { "lat": float, "lng": float }
    Call every 15-30s from frontend (navigator.geolocation.watchPosition)
    while a journey is active, to update live location and build a trail.
    """
    journey, err = _get_journey_or_404(journey_id)
    if err:
        return err

    if journey.status != "active":
        return jsonify({"error": f"Journey is not active (status={journey.status})"}), 409

    data = request.get_json(silent=True) or {}
    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "'lat' and 'lng' are required numbers."}), 400

    journey.last_lat = lat
    journey.last_lng = lng
    journey.last_ping_at = _now()
    db.session.add(LocationPing(journey_id=journey.id, latitude=lat, longitude=lng))
    db.session.commit()

    grace = current_app.config["GRACE_PERIOD_SECONDS"]
    return jsonify(journey.to_dict(grace_seconds=grace))


@bp.route("/<journey_id>/complete", methods=["POST"])
def complete_journey(journey_id):
    """Called when the user taps "I'm Safe"."""
    journey, err = _get_journey_or_404(journey_id)
    if err:
        return err

    journey.status = "completed"
    journey.completed_at = _now()
    db.session.commit()
    return jsonify(journey.to_dict())


@bp.route("/<journey_id>/sos", methods=["POST"])
def trigger_sos(journey_id):
    """
    Called when the safety timer hits zero, or the user taps the SOS button
    during an active journey.
    Marks the journey as SOS and returns the Safety Circle contacts to notify.
    Wire in a real SMS/email provider (Twilio, SendGrid, etc.) where marked below.
    """
    journey, err = _get_journey_or_404(journey_id)
    if err:
        return err

    # Allow re-triggering SOS on an already-SOS journey without error (idempotent)
    if journey.status not in ("active", "sos"):
        return jsonify({"error": f"Cannot trigger SOS on a journey with status '{journey.status}'."}), 409

    journey.status = "sos"
    if not journey.sos_triggered_at:
        journey.sos_triggered_at = _now()
    db.session.commit()

    contacts = []
    if journey.user_id:
        contacts = [
            c.to_dict()
            for c in db.session.execute(
                select(EmergencyContact).where(EmergencyContact.user_id == journey.user_id)
            ).scalars().all()
        ]

    # TODO: plug in a real notifier, e.g.:
    # for c in contacts:
    #     send_sms(c["phone"], f"SOS: {journey.user_id} may be in danger near "
    #                           f"({journey.last_lat}, {journey.last_lng})")

    return jsonify({"journey": journey.to_dict(), "notified_contacts": contacts})


@bp.route("/<journey_id>/overdue-check", methods=["GET"])
def overdue_check(journey_id):
    """
    Server-side backstop to the client-side countdown timer: true once a
    journey has passed expected_arrival + grace period without being marked safe.
    """
    journey, err = _get_journey_or_404(journey_id)
    if err:
        return err

    if journey.status != "active" or not journey.expected_arrival:
        return jsonify({"overdue": False})

    grace = current_app.config["GRACE_PERIOD_SECONDS"]
    now = _now()
    overdue = now > journey.expected_arrival + timedelta(seconds=grace)
    return jsonify({"overdue": overdue, "expected_arrival": journey.expected_arrival.isoformat()})


@bp.route("/reports", methods=["POST"])
def submit_safety_report():
    """
    Body: { "lat": float, "lng": float, "location_text": str,
            "issue_type": str, "comment": str, "severity": 1-5 }
    Powers the Community "Report an Issue" form. These reports directly lower
    the safety score of any future route that passes nearby.
    """
    data = request.get_json(silent=True) or {}
    required = ["lat", "lng", "issue_type"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (TypeError, ValueError):
        return jsonify({"error": "'lat' and 'lng' must be numbers."}), 400

    try:
        severity = int(data.get("severity", 2))
        severity = max(1, min(5, severity))
    except (TypeError, ValueError):
        severity = 2

    report = SafetyReport(
        latitude=lat,
        longitude=lng,
        location_text=data.get("location_text") or None,
        issue_type=str(data["issue_type"]).strip(),
        comment=data.get("comment") or None,
        severity=severity,
    )
    db.session.add(report)
    db.session.commit()
    return jsonify(report.to_dict()), 201


@bp.route("/reports", methods=["GET"])
def list_safety_reports():
    """Powers the Community reports feed."""
    reports = (
        db.session.execute(
            select(SafetyReport).order_by(SafetyReport.created_at.desc()).limit(100)
        )
        .scalars()
        .all()
    )
    return jsonify([r.to_dict() for r in reports])
