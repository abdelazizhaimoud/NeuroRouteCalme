"""routes_api.py — NeuroRoute: Auth, Favorites, History, Place History API routes.

All routes are registered via init_routes(app) and use JWT auth where needed.
Database models are imported from db.py.
"""

from __future__ import annotations

import functools
from datetime import datetime, timedelta, timezone

import jwt
from flask import g, jsonify, request
from werkzeug.security import check_password_hash

from db import (
    FavoriteRoute,
    PlaceHistory,
    RouteHistory,
    User,
    db,
)

JWT_SECRET = "neuroroute-secret-key-change-in-production"
JWT_EXPIRATION_HOURS = 72


# ---------------------------------------------------------------------------
#  JWT auth decorator
# ---------------------------------------------------------------------------

def require_auth(f):
    """Decorator that validates the JWT Bearer token and sets g.current_user."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            user = User.query.get(payload["user_id"])
            if not user:
                return jsonify({"error": "User not found"}), 401
            g.current_user = user
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
#  Token helper
# ---------------------------------------------------------------------------

def _make_token(user_id: int) -> str:
    return jwt.encode(
        {
            "user_id": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


# ---------------------------------------------------------------------------
#  Route registration
# ---------------------------------------------------------------------------

def init_routes(app):
    # ======================================================================
    #  AUTH
    # ======================================================================

    @app.route("/api/auth/register", methods=["POST"])
    def register():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Missing JSON body"}), 400

        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password", "")
        profile_type = data.get("profile_type", "normal")

        if not name or not email or not password:
            return jsonify({"error": "Name, email, and password are required"}), 400
        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Email already registered"}), 409

        user = User(name=name, email=email, profile_type=profile_type)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        token = _make_token(user.id)
        return jsonify({"token": token, "user": user.to_dict()}), 201

    @app.route("/api/auth/login", methods=["POST"])
    def login():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Missing JSON body"}), 400

        email = (data.get("email") or "").strip().lower()
        password = data.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"error": "Invalid email or password"}), 401

        token = _make_token(user.id)
        return jsonify({"token": token, "user": user.to_dict()})

    @app.route("/api/auth/logout", methods=["POST"])
    @require_auth
    def logout():
        return jsonify({"success": True})

    @app.route("/api/auth/me", methods=["GET"])
    @require_auth
    def get_me():
        return jsonify({"user": g.current_user.to_dict()})

    @app.route("/api/auth/profile", methods=["PUT"])
    @require_auth
    def update_profile():
        data = request.get_json(silent=True) or {}
        user = g.current_user

        if "name" in data:
            val = (data["name"] or "").strip()
            if val:
                user.name = val
        if "phone" in data:
            user.phone = (data["phone"] or "").strip() or None
        if "date_of_birth" in data:
            user.date_of_birth = (data["date_of_birth"] or "").strip() or None
        if "bio" in data:
            user.bio = (data["bio"] or "").strip() or None
        if "profile_type" in data:
            user.profile_type = data["profile_type"]

        db.session.commit()
        return jsonify({"user": user.to_dict()})

    @app.route("/api/auth/password", methods=["PUT"])
    @require_auth
    def change_password():
        data = request.get_json(silent=True) or {}
        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")

        if not current_password or not new_password:
            return jsonify({"error": "Current and new password are required"}), 400
        if len(new_password) < 6:
            return jsonify({"error": "New password must be at least 6 characters"}), 400
        if not g.current_user.check_password(current_password):
            return jsonify({"error": "Current password is incorrect"}), 403

        g.current_user.set_password(new_password)
        db.session.commit()
        return jsonify({"success": True})

    # ======================================================================
    #  FAVORITES
    # ======================================================================

    @app.route("/api/favorites", methods=["GET"])
    @require_auth
    def list_favorites():
        limit = request.args.get("limit", type=int)
        query = (
            FavoriteRoute.query.filter_by(user_id=g.current_user.id)
            .order_by(FavoriteRoute.created_at.desc())
        )
        if limit and limit > 0:
            query = query.limit(limit)
        return jsonify({"favorites": [f.to_dict() for f in query.all()]})

    @app.route("/api/favorites", methods=["POST"])
    @require_auth
    def create_favorite():
        data = request.get_json(silent=True) or {}
        start_lat = data.get("start_lat")
        start_lon = data.get("start_lon")
        end_lat = data.get("end_lat", start_lat)
        end_lon = data.get("end_lon", start_lon)

        if start_lat is None or start_lon is None:
            return jsonify({"error": "start_lat and start_lon are required"}), 400

        fav = FavoriteRoute(
            user_id=g.current_user.id,
            name=data.get("name"),
            start_lat=float(start_lat),
            start_lon=float(start_lon),
            start_name=data.get("start_name"),
            end_lat=float(end_lat),
            end_lon=float(end_lon),
            end_name=data.get("end_name"),
            profile_type=data.get("profile_type"),
            total_length_m=data.get("total_length_m"),
            total_time_s=data.get("total_time_s"),
            avg_score_calme=data.get("avg_score_calme"),
        )
        db.session.add(fav)
        db.session.commit()
        return jsonify({"favorite": fav.to_dict()}), 201

    @app.route("/api/favorites/<int:fav_id>", methods=["PUT"])
    @require_auth
    def update_favorite(fav_id):
        fav = FavoriteRoute.query.filter_by(
            id=fav_id, user_id=g.current_user.id
        ).first()
        if not fav:
            return jsonify({"error": "Favorite not found"}), 404

        data = request.get_json(silent=True) or {}
        if "name" in data:
            fav.name = data["name"]
        if "custom_name" in data:
            fav.custom_name = data["custom_name"]

        db.session.commit()
        return jsonify({"favorite": fav.to_dict()})

    @app.route("/api/favorites/<int:fav_id>", methods=["DELETE"])
    @require_auth
    def delete_favorite(fav_id):
        fav = FavoriteRoute.query.filter_by(
            id=fav_id, user_id=g.current_user.id
        ).first()
        if not fav:
            return jsonify({"error": "Favorite not found"}), 404
        db.session.delete(fav)
        db.session.commit()
        return jsonify({"success": True})

    # ======================================================================
    #  ROUTE HISTORY
    # ======================================================================

    @app.route("/api/history", methods=["GET"])
    @require_auth
    def list_history():
        entries = (
            RouteHistory.query.filter_by(user_id=g.current_user.id)
            .order_by(RouteHistory.completed_at.desc())
            .all()
        )
        return jsonify({"history": [e.to_dict() for e in entries]})

    @app.route("/api/history", methods=["POST"])
    @require_auth
    def create_history():
        data = request.get_json(silent=True) or {}
        entry = RouteHistory(
            user_id=g.current_user.id,
            start_lat=float(data.get("start_lat", 0)),
            start_lon=float(data.get("start_lon", 0)),
            start_name=data.get("start_name"),
            end_lat=float(data.get("end_lat", 0)),
            end_lon=float(data.get("end_lon", 0)),
            end_name=data.get("end_name"),
            profile_type=data.get("profile_type", "normal"),
            total_length_m=data.get("total_length_m"),
            total_time_s=data.get("total_time_s"),
            avg_score_calme=data.get("avg_score_calme"),
            distance_km=data.get("distance_km"),
            was_navigated=data.get("was_navigated", False),
        )
        db.session.add(entry)
        db.session.commit()
        return jsonify({"history": entry.to_dict()}), 201

    @app.route("/api/history/<int:history_id>", methods=["DELETE"])
    @require_auth
    def delete_history(history_id):
        entry = RouteHistory.query.filter_by(
            id=history_id, user_id=g.current_user.id
        ).first()
        if not entry:
            return jsonify({"error": "History entry not found"}), 404
        db.session.delete(entry)
        db.session.commit()
        return jsonify({"success": True})

    # ======================================================================
    #  PLACE HISTORY
    # ======================================================================

    @app.route("/api/places/history", methods=["GET"])
    @require_auth
    def list_places():
        places = (
            PlaceHistory.query.filter_by(user_id=g.current_user.id)
            .order_by(PlaceHistory.created_at.desc())
            .all()
        )
        return jsonify({"places": [p.to_dict() for p in places]})

    @app.route("/api/places/history", methods=["POST"])
    @require_auth
    def create_place():
        data = request.get_json(silent=True) or {}
        lat = data.get("latitude")
        lon = data.get("longitude")
        if lat is None or lon is None:
            return jsonify({"error": "latitude and longitude are required"}), 400

        existing = PlaceHistory.query.filter_by(
            user_id=g.current_user.id,
            latitude=float(lat),
            longitude=float(lon),
        ).first()
        if existing:
            existing.created_at = datetime.now(timezone.utc)
            db.session.commit()
            return jsonify({"place": existing.to_dict()})

        place = PlaceHistory(
            user_id=g.current_user.id,
            name=data.get("name"),
            latitude=float(lat),
            longitude=float(lon),
        )
        db.session.add(place)
        db.session.commit()
        return jsonify({"place": place.to_dict()}), 201

    @app.route("/api/places/history/<int:place_id>", methods=["DELETE"])
    @require_auth
    def delete_place(place_id):
        place = PlaceHistory.query.filter_by(
            id=place_id, user_id=g.current_user.id
        ).first()
        if not place:
            return jsonify({"error": "Place not found"}), 404
        db.session.delete(place)
        db.session.commit()
        return jsonify({"success": True})
