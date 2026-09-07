import uuid
from datetime import datetime, timezone

from extensions import db


def gen_id():
    return uuid.uuid4().hex


def _now():
    """Timezone-aware UTC now — compatible with Python 3.9+ and avoids the
    DeprecationWarning for datetime.utcnow() in Python 3.12+."""
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored as naive UTC


class User(db.Model):
    """A registered SafePath user (phone + password login)."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(32), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    age = db.Column(db.Integer)
    college = db.Column(db.String(255))
    blood_group = db.Column(db.String(8))
    created_at = db.Column(db.DateTime, default=_now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "age": self.age,
            "college": self.college,
            "blood_group": self.blood_group,
        }


class SafetyReport(db.Model):
    """Community-submitted safety reports (maps to the 'Community' section's
    report form). These feed directly into the route safety-scoring algorithm."""
    __tablename__ = "safety_reports"

    id = db.Column(db.String(32), primary_key=True, default=gen_id)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    location_text = db.Column(db.String(255))
    issue_type = db.Column(db.String(64), nullable=False)  # e.g. "Poor lighting", "Harassment"
    comment = db.Column(db.Text)
    severity = db.Column(db.Integer, default=2)  # 1 (minor) .. 5 (severe)
    created_at = db.Column(db.DateTime, default=_now)

    def to_dict(self):
        return {
            "id": self.id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_text": self.location_text,
            "issue_type": self.issue_type,
            "comment": self.comment,
            "severity": self.severity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EmergencyContact(db.Model):
    """A user's Safety Circle contact."""
    __tablename__ = "emergency_contacts"

    id = db.Column(db.String(32), primary_key=True, default=gen_id)
    user_id = db.Column(db.String(32), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(32))
    email = db.Column(db.String(120))
    relation = db.Column(db.String(64))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "relation": self.relation,
        }


class Journey(db.Model):
    """One 'trip' session: created when the user taps Start Safer Journey,
    updated by live location pings, closed by 'I'm Safe' or SOS."""
    __tablename__ = "journeys"

    id = db.Column(db.String(32), primary_key=True, default=gen_id)
    user_id = db.Column(db.String(32), nullable=True, index=True)

    origin_lat = db.Column(db.Float, nullable=False)
    origin_lng = db.Column(db.Float, nullable=False)
    origin_text = db.Column(db.String(255))

    destination_lat = db.Column(db.Float, nullable=False)
    destination_lng = db.Column(db.Float, nullable=False)
    destination_text = db.Column(db.String(255))

    # JSON column — PostgreSQL natively supports JSON; SQLite stores as text.
    route_geometry = db.Column(db.JSON)
    route_distance_m = db.Column(db.Float)
    route_duration_s = db.Column(db.Float)
    safety_score = db.Column(db.Integer)
    route_label = db.Column(db.String(32))  # "safer" | "fastest" | "emergency"

    status = db.Column(db.String(16), default="active")  # active | completed | sos
    started_at = db.Column(db.DateTime, default=_now)
    expected_arrival = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    last_lat = db.Column(db.Float)
    last_lng = db.Column(db.Float)
    last_ping_at = db.Column(db.DateTime)

    sos_triggered_at = db.Column(db.DateTime)

    def to_dict(self, grace_seconds=300):
        from datetime import timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        seconds_remaining, overdue = None, False
        if self.status == "active" and self.expected_arrival:
            seconds_remaining = int((self.expected_arrival - now).total_seconds())
            overdue = seconds_remaining < -grace_seconds
        return {
            "id": self.id,
            "origin": {"lat": self.origin_lat, "lng": self.origin_lng, "text": self.origin_text},
            "destination": {
                "lat": self.destination_lat, "lng": self.destination_lng, "text": self.destination_text
            },
            "route_geometry": self.route_geometry,
            "route_distance_m": self.route_distance_m,
            "route_duration_s": self.route_duration_s,
            "safety_score": self.safety_score,
            "route_label": self.route_label,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "expected_arrival": self.expected_arrival.isoformat() if self.expected_arrival else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_location": {"lat": self.last_lat, "lng": self.last_lng} if self.last_lat is not None else None,
            "last_ping_at": self.last_ping_at.isoformat() if self.last_ping_at else None,
            "seconds_remaining": seconds_remaining,
            "overdue": overdue,
        }


class LocationPing(db.Model):
    """History of live-location updates for a journey (useful for a replay/audit trail)."""
    __tablename__ = "location_pings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    journey_id = db.Column(db.String(32), db.ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=_now)
