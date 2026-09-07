# SafePath Backend

Flask REST API for the SafePath personal safety app.

---

## Quick Setup

### 1. PostgreSQL Setup

Install PostgreSQL if not already installed:

**Windows:** Download from https://www.postgresql.org/download/windows/

**macOS (Homebrew):**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

Create the database and user:

```bash
# Enter PostgreSQL shell
psql -U postgres

# In the psql shell:
CREATE USER safepath_user WITH PASSWORD 'yourpassword';
CREATE DATABASE safepath_db OWNER safepath_user;
GRANT ALL PRIVILEGES ON DATABASE safepath_db TO safepath_user;
\q
```

### 2. Backend Environment

```bash
# Navigate to backend directory
cd SafePath-backend

# Create a virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy the example .env file
cp .env.example .env

# Edit .env and fill in your PostgreSQL credentials:
# DATABASE_URL=postgresql://safepath_user:yourpassword@localhost:5432/safepath_db
# SECRET_KEY=some-long-random-string
```

### 4. Run Database Migrations

```bash
# Initialize migrations (first time only — creates the migrations/ folder)
flask db init

# Generate the initial migration
flask db migrate -m "initial schema"

# Apply migrations to the database
flask db upgrade
```

### 5. Start the Backend

```bash
flask run --port 5000
# or:
python app.py
```

Backend runs at: http://127.0.0.1:5000

Test it: http://127.0.0.1:5000/api/health → should return `{"status": "ok"}`

---

## Start the Frontend

Open `SafePath-frontend/index.html` directly in your browser, or serve it
with any static server:

```bash
# Python built-in server (from the SafePath-frontend directory):
cd ../SafePath-frontend
python -m http.server 8080
```

Then open http://localhost:8080 in your browser.

The frontend calls `http://127.0.0.1:5000/api` — the backend must be running.

---

## API Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET | /api/health | Health check |
| POST | /api/journey/plan | Find safe routes |
| POST | /api/journey/start | Start journey session |
| GET | /api/journey/`<id>`/status | Journey status |
| POST | /api/journey/`<id>`/ping | Live location update |
| POST | /api/journey/`<id>`/complete | Mark journey safe |
| POST | /api/journey/`<id>`/sos | Trigger SOS on active journey |
| POST | /api/journey/reports | Submit safety report |
| GET | /api/journey/reports | List safety reports |
| GET | /api/safety/contacts | List emergency contacts |
| POST | /api/safety/contacts | Add emergency contact |
| DELETE | /api/safety/contacts/`<id>` | Delete emergency contact |
| POST | /api/safety/sos | Standalone SOS (no journey) |
| GET | /api/safe-places/ | List safe places |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | **Yes** | PostgreSQL connection string |
| `SECRET_KEY` | **Yes** | Flask session secret (any long random string) |
| `OSRM_URL` | No | OSRM routing server (defaults to public instance) |
| `USER_AGENT` | No | User-Agent for Nominatim/Overpass (update email) |

---

## Notes

- The SOS feature stores emergency records in PostgreSQL and returns your
  Safety Circle contacts list. Real SMS/email notifications require
  a third-party service (Twilio, SendGrid, etc.) — see the TODO comment
  in `blueprints/journey_monitoring.py`.
- Safe places (`/api/safe-places/`) are currently demo data.
  Production would query Overpass API or a real database.
- All external APIs (Nominatim, OSRM, Overpass) are free and require no API key.
