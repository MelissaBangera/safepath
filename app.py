from dotenv import load_dotenv
load_dotenv()  # Must be first — loads .env before any config reads os.environ

from flask import Flask
from flask_cors import CORS

from config import Config
from extensions import db, migrate
from blueprints.journey_planning import bp as journey_planning_bp
from blueprints.journey_monitoring import bp as journey_monitoring_bp
from blueprints.safety import bp as safety_bp
from blueprints.safe_places import bp as safe_places_bp
from blueprints.auth import bp as auth_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    # Allow the static frontend (index.html / home.html opened from file:// or
    # a dev server) to call this API from a different origin.
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.register_blueprint(journey_planning_bp)
    app.register_blueprint(journey_monitoring_bp)
    app.register_blueprint(safety_bp)
    app.register_blueprint(safe_places_bp)
    app.register_blueprint(auth_bp)

    @app.route("/api/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
