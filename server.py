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

WEB_DIR = Path(__file__).parent / "web"
PLACE_NAME = "Casablanca, Morocco"

# These are filled at startup by init_engine()
_scored_graph = None
_graph = None


def init_engine() -> None:
    """Load graph and build scored graph (called once at startup)."""
    global _scored_graph, _graph

    print("=" * 60)
    print("  NeuroRoute Calme — Server Initialization")
    print("=" * 60)

    t0 = time.time()

    print("\n[1/3] Loading graph...")
    _graph = fetch_graph(PLACE_NAME)
    print(f"  Nodes: {_graph.number_of_nodes():,}  |  Edges: {_graph.number_of_edges():,}")

    print("\n[2/3] Building scoring DataFrame...")
    df = build_scoring_dataframe(
        _graph,
        place_name=PLACE_NAME,
        use_verdure_query=False,
        seed=42,
        include_geometry=False,
        compute_ml=False,
    )
    print(f"  {len(df):,} edges scored")
    print(f"  score_calme: median={df['score_calme'].median():.3f}")

    print("\n[3/3] Building scored graph...")
    _scored_graph = build_scored_graph(_graph, df)

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
    """Health check for mobile apps."""
    return jsonify({
        "status": "ready" if _scored_graph is not None else "loading",
        "profiles": list(USER_PROFILES.keys())
    })


@app.route("/api/route", methods=["POST"])
def api_route():
    """Compute routes for all 4 profiles.

    Request JSON:
        { "start_lat": float, "start_lon": float,
          "end_lat": float,   "end_lon": float }

    Response JSON:
        { "routes": { "<profile>": { "coords", "total_length_m", ... } },
          "profiles": { "<profile>": { "label", "description", "color" } } }
    """
    if _scored_graph is None:
        return jsonify({"error": "Server not ready — graph still loading"}), 503

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    try:
        start_lat = float(data["start_lat"])
        start_lon = float(data["start_lon"])
        end_lat = float(data["end_lat"])
        end_lon = float(data["end_lon"])
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid coordinates: {exc}"}), 400

    start_point = (start_lat, start_lon)
    end_point = (end_lat, end_lon)

    # Resolve nearest nodes once (avoid doing it 4 times)
    try:
        start_node = ox.nearest_nodes(_scored_graph, X=start_lon, Y=start_lat)
        end_node = ox.nearest_nodes(_scored_graph, X=end_lon, Y=end_lat)
    except Exception as exc:
        return jsonify({"error": f"Could not find nearest nodes: {exc}"}), 400

    routes = {}
    for profile in USER_PROFILES:
        t0 = time.time()
        result = get_best_route(_scored_graph, start_node, end_node, profile=profile)
        elapsed_ms = (time.time() - t0) * 1000

        if "error" in result:
            routes[profile] = {"error": result["error"]}
            continue

        # Convert node IDs to [lat, lon] coordinates for the frontend
        coords = []
        for node_id in result["path"]:
            if node_id in _scored_graph.nodes:
                nd = _scored_graph.nodes[node_id]
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
        "start": {"lat": start_lat, "lon": start_lon},
        "end": {"lat": end_lat, "lon": end_lon},
    })


@app.route("/api/route/<profile>", methods=["POST"])
def api_route_single(profile):
    """Compute route for a single profile. Optimized for mobile apps."""
    if _scored_graph is None:
        return jsonify({"error": "Server not ready — graph still loading"}), 503

    if profile not in USER_PROFILES:
        return jsonify({"error": f"Unknown profile '{profile}'."}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    try:
        start_lat = float(data["start_lat"])
        start_lon = float(data["start_lon"])
        end_lat = float(data["end_lat"])
        end_lon = float(data["end_lon"])
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid coordinates: {exc}"}), 400

    try:
        start_node = ox.nearest_nodes(_scored_graph, X=start_lon, Y=start_lat)
        end_node = ox.nearest_nodes(_scored_graph, X=end_lon, Y=end_lat)
    except Exception as exc:
        return jsonify({"error": f"Could not find nearest nodes: {exc}"}), 400

    t0 = time.time()
    result = get_best_route(_scored_graph, start_node, end_node, profile=profile)
    elapsed_ms = (time.time() - t0) * 1000

    if "error" in result:
        return jsonify({"error": result["error"]}), 400

    coords = []
    for node_id in result["path"]:
        if node_id in _scored_graph.nodes:
            nd = _scored_graph.nodes[node_id]
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
        "start": {"lat": start_lat, "lon": start_lon},
        "end": {"lat": end_lat, "lon": end_lon},
    })


@app.route("/api/profiles", methods=["GET"])
def api_profiles():
    """Return available profile metadata."""
    return jsonify({"profiles": PROFILE_META})


# ---------------------------------------------------------------------------
#  CLI + main
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="NeuroRoute Calme — Web Server")
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
