import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # PostgreSQL via DATABASE_URL env var (required in production).
    # Falls back to SQLite only for local dev convenience.
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///safepath.db")
    # SQLAlchemy 1.4+ requires postgresql:// not postgres:// (Heroku quirk fix)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- External services (all free, no API key required) ---
    NOMINATIM_URL = "https://nominatim.openstreetmap.org"      # geocoding
    OSRM_URL = os.environ.get("OSRM_URL", "https://routing.openstreetmap.de")  # routing (real foot/car/bike profiles)
    OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"    # OSM POI queries (lamps, police, etc.)
    # Nominatim/Overpass require a descriptive User-Agent per their usage policy.
    USER_AGENT = os.environ.get(
        "USER_AGENT",
        "SafePath-College-Project/1.0 (contact: your-email@example.com)"
    )

    # --- Safety scoring tunables ---
    NIGHT_START_HOUR = 20   # 8 PM
    NIGHT_END_HOUR = 6      # 6 AM
    INCIDENT_SEARCH_RADIUS_M = 150   # how close a community report must be to a route to count
    POI_SEARCH_BUFFER_M = 120        # how close a streetlamp/police/hospital must be to count
    GRACE_PERIOD_SECONDS = 5 * 60    # overdue grace before a journey is flagged
