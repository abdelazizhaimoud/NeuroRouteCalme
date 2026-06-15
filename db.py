"""db.py — NeuroRoute: Database models for NeuroRoute mobile app.

Models: User, FavoriteRoute, RouteHistory, PlaceHistory
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, text
from werkzeug.security import check_password_hash, generate_password_hash

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    profile_type = db.Column(db.String(30), nullable=False, default="normal")
    phone = db.Column(db.String(20))
    date_of_birth = db.Column(db.String(20))
    bio = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    favorite_routes = db.relationship("FavoriteRoute", back_populates="user", cascade="all, delete-orphan")
    route_history = db.relationship("RouteHistory", back_populates="user", cascade="all, delete-orphan")
    place_history = db.relationship("PlaceHistory", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "phone": self.phone,
            "bio": self.bio,
            "date_of_birth": self.date_of_birth,
            "profile_type": self.profile_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FavoriteRoute(db.Model):
    __tablename__ = "favorite_routes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(150))
    start_lat = db.Column(db.Float, nullable=False)
    start_lon = db.Column(db.Float, nullable=False)
    start_name = db.Column(db.String(200))
    end_lat = db.Column(db.Float, nullable=False)
    end_lon = db.Column(db.Float, nullable=False)
    end_name = db.Column(db.String(200))
    profile_type = db.Column(db.String(30))
    total_length_m = db.Column(db.Float)
    total_time_s = db.Column(db.Float)
    avg_score_calme = db.Column(db.Float)
    custom_name = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="favorite_routes")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "destination_name": self.name,
            "custom_name": self.custom_name,
            "start": {"lat": self.start_lat, "lon": self.start_lon, "name": self.start_name},
            "end": {"lat": self.end_lat, "lon": self.end_lon, "name": self.end_name},
            "profile_type": self.profile_type,
            "total_length_m": self.total_length_m,
            "total_time_s": self.total_time_s,
            "avg_score_calme": self.avg_score_calme,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RouteHistory(db.Model):
    __tablename__ = "route_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    start_lat = db.Column(db.Float, nullable=False)
    start_lon = db.Column(db.Float, nullable=False)
    start_name = db.Column(db.String(200))
    end_lat = db.Column(db.Float, nullable=False)
    end_lon = db.Column(db.Float, nullable=False)
    end_name = db.Column(db.String(200))
    profile_type = db.Column(db.String(30), nullable=False)
    total_length_m = db.Column(db.Float)
    total_time_s = db.Column(db.Float)
    avg_score_calme = db.Column(db.Float)
    distance_km = db.Column(db.Float)
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    was_navigated = db.Column(db.Boolean, default=False)

    user = db.relationship("User", back_populates="route_history")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "start": {"lat": self.start_lat, "lon": self.start_lon, "name": self.start_name},
            "end": {"lat": self.end_lat, "lon": self.end_lon, "name": self.end_name},
            "profile_type": self.profile_type,
            "total_length_m": self.total_length_m,
            "total_time_s": self.total_time_s,
            "avg_score_calme": self.avg_score_calme,
            "distance_km": self.distance_km,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "was_navigated": self.was_navigated,
        }


class PlaceHistory(db.Model):
    __tablename__ = "place_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(200))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="place_history")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def create_app(db_path: str = "neuroroute.db") -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NeuroRoute Database Manager")
    parser.add_argument("--change", metavar="FILE", default="neuroroute.db", help="Database file path (default: neuroroute.db)")
    parser.add_argument("--delete", action="store_true", help="Drop all tables before creating them")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.change).resolve()

    app = create_app(str(db_path))

    with app.app_context():
        if args.delete:
            print("Dropping all tables...")
            db.drop_all()
            print("  Done.")

        print(f"Creating tables in {db_path}...")
        db.create_all()

        engine = db.engine
        inspector = __import__("sqlalchemy", fromlist=["inspect"]).inspect(engine)
        tables = inspector.get_table_names()
        print(f"  Created {len(tables)} table(s): {', '.join(tables)}")
        print("\nDatabase ready.")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
