"""server.py — NeuroRoute Calme: Flask API server.

Preloads the Casablanca pedestrian graph and scoring at startup,
then serves a Leaflet.js frontend and a routing API.

Usage:
    python server.py
    python server.py --port 5000
    python server.py --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS

from db import db
from routes_api import init_routes

from main import (
    USER_PROFILES,
    build_scored_graph,
    build_scoring_dataframe,
    fetch_graph,
    get_best_route,
)
import osmnx as ox

# ---------------------------------------------------------------------------
#  App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder=None)
CORS(app)

# --- Database ---
DB_PATH = str(Path(__file__).parent / "neuroroute.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

WEB_DIR = Path(__file__).parent / "web"
OUTPUTS_DIR = Path(__file__).parent / "outputs"

CITIES = {
    "casablanca": {
        "name": "Casablanca, Morocco",
        "label": "Casablanca",
        "csv_path": OUTPUTS_DIR / "routes_casablanca.csv",
        "center": [33.5731, -7.6114],
        "zoom": 13,
        "ml_predicted": False,
    },
    "mohammedia": {
        "name": "Mohammedia, Morocco",
        "label": "Mohammedia",
        "csv_path": OUTPUTS_DIR / "routes_mohammedia.csv",
        "center": [33.6931, -7.3871],
        "zoom": 14,
        "ml_predicted": True,
    },
}

# These are filled at startup by init_engine()
_scored_graphs = {}
_graphs = {}


def init_engine() -> None:
    """Load graph and build scored graph for all cities (called once at startup)."""
    global _scored_graphs, _graphs

    # Ensure database tables exist
    with app.app_context():
        db.create_all()

    print("=" * 60)
    print("  NeuroRoute Calme — Server Initialization")
    print("=" * 60)

    t0 = time.time()

    for city_id, city_info in CITIES.items():
        print(f"\nInitializing {city_id}...")
        
        # 1. Load Graph
        graph = fetch_graph(city_info["name"])
        _graphs[city_id] = graph
        print(f"  Nodes: {graph.number_of_nodes():,}  |  Edges: {graph.number_of_edges():,}")
        
        # 2. Load precomputed ML scores CSV
        csv_path = city_info["csv_path"]
        if not csv_path.exists():
            print(f"  WARNING: {csv_path} not found. Skipping {city_id}.")
            continue
            
        import pandas as pd
        df = pd.read_csv(csv_path)
        
        # build_scored_graph expects u, v, key as columns, not index
        
        # 3. Build scored graph
        scored_graph = build_scored_graph(graph, df)
        _scored_graphs[city_id] = scored_graph
        print(f"  Loaded {len(df):,} precomputed edges.")

    elapsed = time.time() - t0
    print(f"\n  Initialization complete in {elapsed:.1f}s")
    print(f"  Server ready for routing requests.")
    print("=" * 60)


# ---------------------------------------------------------------------------
#  Static file serving (frontend)
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main HTML page."""
    return send_file(WEB_DIR / "index.html")


@app.route("/web/<path:filename>")
def static_files(filename):
    """Serve CSS, JS, and other static assets."""
    return send_from_directory(WEB_DIR, filename)


# ---------------------------------------------------------------------------
#  Routing API
# ---------------------------------------------------------------------------

PROFILE_META = {
    "normal": {
        "label": "Normal",
        "description": "Priorité temps — itinéraire le plus rapide",
        "color": "#3498db",
        "icon": "🚶",
    },
    "equilibre": {
        "label": "Équilibre",
        "description": "Compromis entre temps, calme et confort",
        "color": "#f39c12",
        "icon": "⚖️",
    },
    "autiste": {
        "label": "Autiste",
        "description": "Évite le bruit et la foule — itinéraire le plus calme",
        "color": "#9b59b6",
        "icon": "🧠",
    },
    "fauteuil_roulant": {
        "label": "Fauteuil roulant",
        "description": "Évite la foule et les escaliers — itinéraire accessible",
        "color": "#2ecc71",
        "icon": "♿",
    },
}


@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check."""
    return jsonify({
        "status": "ready" if _scored_graphs else "loading",
        "profiles": list(USER_PROFILES.keys()),
        "cities": list(CITIES.keys())
    })


@app.route("/api/cities", methods=["GET"])
def api_cities():
    """Return available cities with metadata (center, zoom, ML badge)."""
    cities_meta = {
        city_id: {
            "label": info["label"],
            "center": info["center"],
            "zoom": info["zoom"],
            "ml_predicted": info["ml_predicted"],
            "available": city_id in _scored_graphs,
        }
        for city_id, info in CITIES.items()
    }
    return jsonify({"cities": cities_meta})


@app.route("/api/route", methods=["POST"])
def api_route():
    """Compute routes for all 4 profiles.

    Request JSON:
        { "city": str,
          "start_lat": float, "start_lon": float,
          "end_lat": float,   "end_lon": float }

    Response JSON:
        { "routes": { "<profile>": { "coords", "total_length_m", ... } },
          "profiles": { "<profile>": { "label", "description", "color" } } }
    """
    if not _scored_graphs:
        return jsonify({"error": "Graph not yet loaded"}), 503

    data = request.json
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    city_id = data.get("city", "casablanca")
    if city_id not in _scored_graphs:
        return jsonify({"error": f"Unknown city: {city_id}"}), 400

    start_lat = data.get("start_lat")
    start_lon = data.get("start_lon")
    end_lat = data.get("end_lat")
    end_lon = data.get("end_lon")

    if None in (start_lat, start_lon, end_lat, end_lon):
        return jsonify({"error": "Missing coordinates"}), 400

    start_point = (float(start_lat), float(start_lon))
    end_point = (float(end_lat), float(end_lon))

    scored_graph = _scored_graphs[city_id]

    # Resolve nearest nodes once
    try:
        start_node = ox.nearest_nodes(scored_graph, X=start_lon, Y=start_lat)
        end_node = ox.nearest_nodes(scored_graph, X=end_lon, Y=end_lat)
    except Exception as exc:
        return jsonify({"error": f"Could not find nearest nodes: {exc}"}), 400

    routes = {}
    for profile in USER_PROFILES:
        t0 = time.time()
        result = get_best_route(scored_graph, start_node, end_node, profile=profile)
        elapsed_ms = (time.time() - t0) * 1000

        if "error" in result:
            routes[profile] = {"error": result["error"]}
            continue

        # Convert node IDs to [lat, lon] coordinates for the frontend
        coords = []
        for node_id in result["path"]:
            if node_id in scored_graph.nodes:
                nd = scored_graph.nodes[node_id]
                coords.append([float(nd["y"]), float(nd["x"])])

        routes[profile] = {
            "coords": coords,
            "total_length_m": result["total_length_m"],
            "total_time_s": result["total_time_s"],
            "total_time_min": result["total_time_min"],
            "avg_score_calme": result["avg_score_calme"],
            "n_edges": result["n_edges"],
            "n_nodes": result["n_nodes"],
            "compute_ms": round(elapsed_ms, 1),
        }

    return jsonify({
        "routes": routes,
        "profiles": PROFILE_META,
        "city": city_id,
        "ml_predicted": CITIES[city_id]["ml_predicted"],
        "start": {"lat": start_lat, "lon": start_lon},
        "end": {"lat": end_lat, "lon": end_lon},
    })


@app.route("/api/route/<profile>", methods=["POST"])
def api_route_single(profile):
    """Compute route for a single profile. Supports city param."""
    if not _scored_graphs:
        return jsonify({"error": "Server not ready — graph still loading"}), 503

    if profile not in USER_PROFILES:
        return jsonify({"error": f"Unknown profile '{profile}'."}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    city_id = data.get("city", "casablanca")
    if city_id not in _scored_graphs:
        return jsonify({"error": f"Unknown city: {city_id}"}), 400

    try:
        start_lat = float(data["start_lat"])
        start_lon = float(data["start_lon"])
        end_lat = float(data["end_lat"])
        end_lon = float(data["end_lon"])
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid coordinates: {exc}"}), 400

    scored_graph = _scored_graphs[city_id]
    try:
        start_node = ox.nearest_nodes(scored_graph, X=start_lon, Y=start_lat)
        end_node = ox.nearest_nodes(scored_graph, X=end_lon, Y=end_lat)
    except Exception as exc:
        return jsonify({"error": f"Could not find nearest nodes: {exc}"}), 400

    t0 = time.time()
    result = get_best_route(scored_graph, start_node, end_node, profile=profile)
    elapsed_ms = (time.time() - t0) * 1000

    if "error" in result:
        return jsonify({"error": result["error"]}), 400

    coords = []
    for node_id in result["path"]:
        if node_id in scored_graph.nodes:
            nd = scored_graph.nodes[node_id]
            coords.append([float(nd["y"]), float(nd["x"])])

    return jsonify({
        "route": {
            "coords": coords,
            "total_length_m": result["total_length_m"],
            "total_time_s": result["total_time_s"],
            "total_time_min": result["total_time_min"],
            "avg_score_calme": result["avg_score_calme"],
            "n_edges": result["n_edges"],
            "n_nodes": result["n_nodes"],
            "compute_ms": round(elapsed_ms, 1),
        },
        "profile": PROFILE_META.get(profile, {}),
        "city": city_id,
        "ml_predicted": CITIES[city_id]["ml_predicted"],
        "start": {"lat": start_lat, "lon": start_lon},
        "end": {"lat": end_lat, "lon": end_lon},
    })


@app.route("/api/profiles", methods=["GET"])
def api_profiles():
    """Return available profile metadata."""
    return jsonify({"profiles": PROFILE_META})


# ---------------------------------------------------------------------------
#  Auth, Favorites, History, Place History API routes
# ---------------------------------------------------------------------------

init_routes(app)


# ---------------------------------------------------------------------------
#  CLI + main
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="NeuroRoute Calime — Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    parser.add_argument("--mobile", action="store_true", help="Bind to 0.0.0.0 for mobile access")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    host = "0.0.0.0" if args.mobile else args.host
    init_engine()
    print(f"\n  Open http://{host}:{args.port} in your browser\n")
    app.run(host=host, port=args.port, debug=args.debug)
