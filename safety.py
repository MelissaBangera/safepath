from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from extensions import db
from models import EmergencyContact, Journey

bp = Blueprint("safety", __name__, url_prefix="/api/safety")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------
# Emergency Contacts
# ---------------------------------------------------------

@bp.get("/contacts")
def get_contacts():
    user_id = request.args.get("user_id", "demo-user")
    contacts = db.session.execute(
        select(EmergencyContact).where(EmergencyContact.user_id == user_id)
    ).scalars().all()
    return jsonify({"contacts": [c.to_dict() for c in contacts]})


@bp.post("/contacts")
def add_contact():
    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Contact name is required."}), 400

    contact = EmergencyContact(
        user_id=data.get("user_id", "demo-user"),
        name=name,
        phone=data.get("phone") or None,
        email=data.get("email") or None,
        relation=data.get("relation") or None,
    )

    db.session.add(contact)
    db.session.commit()

    return jsonify({
        "message": "Emergency contact added successfully",
        "contact": contact.to_dict(),
    }), 201


@bp.delete("/contacts/<contact_id>")
def delete_contact(contact_id):
    contact = db.session.get(EmergencyContact, contact_id)
    if contact is None:
        return jsonify({"error": "Contact not found."}), 404

    db.session.delete(contact)
    db.session.commit()
    return jsonify({"message": "Emergency contact deleted successfully"})


# ---------------------------------------------------------
# Standalone SOS  (when there is no active journey)
# ---------------------------------------------------------

@bp.post("/sos")
def emergency_sos():
    """
    Called when the user taps SOS *outside* of an active journey.
    Body: { "user_id": str (optional), "lat": float, "lng": float }
    """
    data = request.get_json(silent=True) or {}

    user_id = data.get("user_id", "demo-user")

    try:
        latitude = float(data["lat"])
        longitude = float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Current latitude (lat) and longitude (lng) are required."}), 400

    now = _now()

    # Create an emergency journey record so the event is persisted.
    journey = Journey(
        user_id=user_id,
        origin_lat=latitude,
        origin_lng=longitude,
        origin_text="Current location",
        destination_lat=latitude,
        destination_lng=longitude,
        destination_text="Emergency SOS",
        route_geometry=None,
        route_distance_m=0,
        route_duration_s=0,
        safety_score=0,
        route_label="emergency",
        status="sos",
        started_at=now,
        expected_arrival=None,
        last_lat=latitude,
        last_lng=longitude,
        last_ping_at=now,
        sos_triggered_at=now,
    )

    db.session.add(journey)
    db.session.commit()

    contacts = db.session.execute(
        select(EmergencyContact).where(EmergencyContact.user_id == user_id)
    ).scalars().all()

    return jsonify({
        "message": "Emergency SOS activated successfully.",
        "journey_id": journey.id,
        "status": journey.status,
        "location": {"lat": latitude, "lng": longitude},
        "notified_contacts": [c.to_dict() for c in contacts],
    }), 201
