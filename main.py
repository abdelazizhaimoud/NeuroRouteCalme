"""main.py — NeuroRoute Calme: simplified data pipeline.

Fetches the Casablanca pedestrian graph from OSM, extracts route features,
simulates missing data (noise, density), and exports a clean DataFrame.

Usage:
    python main.py
    python main.py --place-name "Casablanca, Morocco"
    python main.py --no-verdure-query   (skip spatial green query, use heuristic)
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

# Multiple high-density hotspots (lon, lat)
DENSITY_HOTSPOTS = [
    (-7.5999, 33.5758),
    (-7.6064, 33.5774),
    (-7.6042, 33.5708),
    (-7.6018, 33.5780),
    (-7.6088, 33.5762),
    (-7.6075, 33.5738),
    (-7.6030, 33.5748),
    (-7.6052, 33.5792),
    (-7.6010, 33.5715),
    (-7.6095, 33.5722),
    (-7.5720, 33.5565),
    (-7.5698, 33.5548),
    (-7.5745, 33.5575),
    (-7.5760, 33.5555),
    (-7.5682, 33.5572),
    (-7.5712, 33.5592),
    (-7.5748, 33.5538),
    (-7.5692, 33.5532),
    (-7.6022, 33.5822),
    (-7.6062, 33.5835),
    (-7.6082, 33.5848),
    (-7.5982, 33.5842),
    (-7.6048, 33.5858),
    (-7.6012, 33.5808),
    (-7.5872, 33.5683),
    (-7.5831, 33.5668),
    (-7.5902, 33.5712),
    (-7.5858, 33.5692),
    (-7.5918, 33.5732),
    (-7.5838, 33.5648),
    (-7.5812, 33.5638),
    (-7.5858, 33.5668),
    (-7.5882, 33.5658),
    (-7.5852, 33.5722),
    (-7.5228, 33.5818),
    (-7.5202, 33.5842),
    (-7.5262, 33.5798),
    (-7.5182, 33.5858),
    (-7.5238, 33.5862),
    (-7.5278, 33.5838),
    (-7.5158, 33.5878),
    (-7.5048, 33.5882),
    (-7.5082, 33.5858),
    (-7.5028, 33.5912),
    (-7.5102, 33.5838),
    (-7.5068, 33.5932),
    (-7.5018, 33.5868),
    (-7.5138, 33.5852),
    (-7.6606, 33.5629),
    (-7.6645, 33.5605),
    (-7.6680, 33.5594),
    (-7.6638, 33.5682),
    (-7.6651, 33.5774),
    (-7.6577, 33.5724),
    (-7.6493, 33.5683),
    (-7.5898, 33.5478),
    (-7.5868, 33.5502),
    (-7.5932, 33.5458),
    (-7.5848, 33.5482),
    (-7.5918, 33.5512),
    (-7.5972, 33.5488),
    (-7.5543, 33.5695),
    (-7.5452, 33.5675),
    (-7.5538, 33.5672),
    (-7.5558, 33.5652),
    (-7.5512, 33.5692),
    (-7.5570, 33.5840),
    (-7.5449, 33.5785),
    (-7.5510, 33.5898),
    (-7.5488, 33.5918),
    (-7.5385, 33.6058),
    (-7.6544, 33.5948),
    (-7.6639, 33.5889),
    (-7.6420, 33.5985),
    (-7.6502, 33.6043),
    (-7.6306, 33.5898),
    (-7.6405, 33.5895),
    (-7.6287, 33.5806),
    (-7.6480, 33.5769),
    (-7.6420, 33.5796),
    (-7.6369, 33.5747),
    (-7.6436, 33.5727),
    (-7.6487, 33.5871),
    (-7.6369, 33.5690),
    (-7.6463, 33.5639),
    (-7.6405, 33.5621),
    (-7.6352, 33.5569),
    (-7.6785, 33.5702),
    (-7.6812, 33.5688),
    (-7.6842, 33.5668),
    (-7.6178, 33.5738),
    (-7.6162, 33.5722),
    (-7.6198, 33.5748),
    (-7.6042, 33.5962),
    (-7.5998, 33.5945),
    (-7.6018, 33.5952),
    (-7.6118, 33.5778),
    (-7.6138, 33.5792),
    (-7.5958, 33.5912),
    (-7.5920, 33.5868),
    (-7.6058, 33.5978),
    (-7.5848, 33.5518),
]

MAJOR_HIGHWAY_TYPES = {
    "primary", "primary_link",
    "trunk", "trunk_link",
    "motorway", "motorway_link",
}

# Noise lookup: highway type → base noise level (0 = quiet, 1 = loud)
NOISE_BY_HIGHWAY: dict[str, float] = {
    "footway": 0.10,
    "pedestrian": 0.10,
    "path": 0.10,
    "steps": 0.10,
    "corridor": 0.10,
    "living_street": 0.20,
    "cycleway": 0.20,
    "residential": 0.35,
    "service": 0.35,
    "unclassified": 0.40,
    "track": 0.40,
    "tertiary": 0.55,
    "tertiary_link": 0.55,
    "secondary": 0.70,
    "secondary_link": 0.70,
    "primary": 0.85,
    "primary_link": 0.85,
    "trunk": 1.00,
    "trunk_link": 1.00,
    "motorway": 1.00,
    "motorway_link": 1.00,
}

NOISE_DEFAULT = 0.40

# Density bands: (max_distance_km, base_density)
DENSITY_BANDS: list[tuple[float, float]] = [
    (1.0,  0.85),
    (3.0,  0.60),
    (6.0,  0.40),
    (10.0, 0.25),
    (999,  0.10),
]

JITTER_AMPLITUDE = 0.05

# Green tags for spatial query
GREEN_TAGS: dict[str, list[str] | str | bool] = {
    "leisure": ["park", "garden", "nature_reserve"],
    "landuse": ["grass", "forest", "meadow", "recreation_ground"],
    "natural": ["tree", "wood", "scrub"],
}

GREEN_BUFFER_METERS = 50  # search radius around each edge midpoint

WALKING_SPEED_MS = 1.39  # 5 km/h ≈ 1.39 m/s

# Scoring weights (sum to 1.0) — Score de calme (higher = calmer)
DEFAULT_WEIGHTS = {
    "alpha": 0.15,  # temps (efficiency)
    "beta": 0.35,   # bruit (noise — biggest for neurodivergent users)
    "gamma": 0.30,  # densite (crowd avoidance)
    "delta": 0.20,  # verdure (greenery bonus)
}

# User profiles and their weights: {temps, bruit, densite, verdure}
USER_PROFILES = {
    "normal":    {"temps": 0.70, "bruit": 0.10, "densite": 0.10, "verdure": 0.10},
    "autiste":   {"temps": 0.10, "bruit": 0.50, "densite": 0.30, "verdure": 0.10},
    "fauteuil_roulant": {"temps": 0.20, "bruit": 0.10, "densite": 0.50, "verdure": 0.20},
    "equilibre": {"temps": 0.30, "bruit": 0.25, "densite": 0.25, "verdure": 0.20},
}

# How strongly discomfort should trade off against time in profile routing.
# Final per-edge cost uses: time_s * (1 + lambda_profile * discomfort)
DISCOMFORT_LAMBDA_BASE = 2.0

# Additional time multipliers for steps (physical / accessibility penalty).
# Used as: time_s * (1 + steps_factor) when type_route == "steps".
STEPS_TIME_FACTORS = {
    "normal": 0.5,
    "autiste": 0.75,
    "fauteuil_roulant": 2.5,
    "equilibre": 1.0,
}

# Extra tags to keep from OSM ways so future scoring can use them.
EXTRA_USEFUL_TAGS_WAY = [
    "sidewalk",
    "sidewalk:left",
    "sidewalk:right",
    "lit",
    "surface",
    "tactile_paving",
    "kerb",
    "crossing",
    "width",
]


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def flatten_highway(value) -> str:
    """Extract a single highway type string from possibly messy OSMnx data."""
    if isinstance(value, list):
        value = value[0] if value else "unknown"
    if isinstance(value, str) and value.startswith("["):
        # Handle stringified lists like "['residential']"
        import ast
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list) and parsed:
                value = parsed[0]
        except Exception:
            pass
    return str(value).strip().lower() if value else "unknown"


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km between two (lon, lat) points."""
    R = 6371.0
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def _ensure_crs_4326(gdf):
    """Ensure a GeoDataFrame has CRS set to EPSG:4326 when missing.

    OSMnx usually returns EPSG:4326, but cached/loaded files can sometimes
    lose CRS metadata. If CRS is missing, we assume lon/lat degrees.
    """
    try:
        if getattr(gdf, "crs", None) is None:
            return gdf.set_crs(epsg=4326, allow_override=True)
    except Exception:
        return gdf
    return gdf


def _project_to_meters(gdf):
    """Project GeoDataFrame to a metric CRS (meters).

    Uses GeoPandas' UTM estimator when available. Falls back to Web Mercator.
    Raises on failure (callers should catch and degrade gracefully).
    """
    gdf = _ensure_crs_4326(gdf)
    try:
        utm_crs = gdf.estimate_utm_crs()
        if utm_crs is None:
            raise ValueError("estimate_utm_crs returned None")
        return gdf.to_crs(utm_crs)
    except Exception:
        # Web Mercator is metric (meters) but distorts scale with latitude.
        return gdf.to_crs(epsg=3857)


# ---------------------------------------------------------------------------
#  Step 1 — Fetch graph
# ---------------------------------------------------------------------------

def fetch_graph(place_name: str, cache_dir: str = "cache"):
    """Download (or load from cache) the pedestrian walk graph."""
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(Path(cache_dir) / "osmnx_http")
    ox.settings.log_console = True

    # Ensure we keep extra tags in future downloads
    try:
        tags = list(getattr(ox.settings, "useful_tags_way", []))
        for t in EXTRA_USEFUL_TAGS_WAY:
            if t not in tags:
                tags.append(t)
        ox.settings.useful_tags_way = tags
    except Exception:
        # Not critical: continue with defaults
        pass

    cache_dir_path = Path(cache_dir)
    cache_dir_path.mkdir(parents=True, exist_ok=True)

    slug = slugify(place_name)
    graphml_path = cache_dir_path / f"{slug}_walk.graphml"

    # Backward-compat: accept older Casablanca cache filename
    legacy_candidates = []
    if "casablanca" in slug:
        legacy_candidates.append(cache_dir_path / "casablanca_walk.graphml")

    for candidate in [graphml_path, *legacy_candidates]:
        if candidate.exists():
            print(f"Loading walk graph from cache: {candidate}")
            graph = ox.load_graphml(candidate)
            print(f"  Nodes: {graph.number_of_nodes():,}  |  Edges: {graph.number_of_edges():,}")
            return graph

    print(f"Fetching walk graph for: {place_name}")
    graph = ox.graph_from_place(place_name, network_type="walk", retain_all=True, simplify=True)
    print(f"  Nodes: {graph.number_of_nodes():,}  |  Edges: {graph.number_of_edges():,}")

    try:
        ox.save_graphml(graph, graphml_path)
        print(f"  Saved graph cache: {graphml_path}")
        # Also save legacy name for Casablanca to keep older scripts fast
        if "casablanca" in slug:
            legacy_path = cache_dir_path / "casablanca_walk.graphml"
            if not legacy_path.exists():
                ox.save_graphml(graph, legacy_path)
    except Exception as exc:
        print(f"  WARNING: Could not save graphml cache ({exc})")

    return graph


# ---------------------------------------------------------------------------
#  Step 2 — Extract route features
# ---------------------------------------------------------------------------

def build_edge_features(
    graph,
    place_name: str,
    use_verdure_query: bool = True,
    include_geometry: bool = False,
) -> pd.DataFrame:
    """Build a DataFrame with core edge features.

    Columns:
      u, v, key, segment_id, longueur, type_route, verdure, proximite_principales
      + geometry (optional)
    """
    edges = ox.graph_to_gdfs(graph, nodes=False, edges=True).reset_index()
    print(f"\nExtracting features for {len(edges):,} edges...")

    df = pd.DataFrame({
        "u": edges["u"].astype(int).to_numpy(),
        "v": edges["v"].astype(int).to_numpy(),
        "key": edges["key"].astype(int).to_numpy(),
    })
    df["segment_id"] = (
        df["u"].astype(str) + "_" + df["v"].astype(str) + "_" + df["key"].astype(str)
    )
    df["longueur"] = edges["length"].astype(float).to_numpy()
    df["type_route"] = edges["highway"].apply(flatten_highway).to_numpy()

    if include_geometry:
        df["geometry"] = edges["geometry"].to_numpy()

    print("  Computing verdure (greenery)...")
    if use_verdure_query:
        df["verdure"] = _compute_verdure_spatial(edges, place_name)
    else:
        df["verdure"] = df["type_route"].map(_verdure_heuristic)

    print("  Computing proximity to major roads...")
    df["proximite_principales"] = _compute_major_road_proximity(edges, df["type_route"])

    return df


def extract_route_features(
    graph,
    place_name: str,
    use_verdure_query: bool = True,
) -> pd.DataFrame:
    """Backward-compatible wrapper (kept for older scripts)."""
    return build_edge_features(graph, place_name, use_verdure_query=use_verdure_query, include_geometry=False)


def _compute_verdure_spatial(edges, place_name: str) -> pd.Series:
    """Query OSM for green features and compute proximity for each edge."""
    try:
        green_gdf = ox.features_from_place(place_name, tags=GREEN_TAGS)
        print(f"    Found {len(green_gdf):,} green features")
    except Exception as exc:
        print(f"    WARNING: Green features query failed ({exc}), falling back to heuristic")
        highway_series = edges["highway"].apply(flatten_highway)
        return highway_series.map(_verdure_heuristic)

    if green_gdf.empty:
        print("    No green features found, using heuristic")
        highway_series = edges["highway"].apply(flatten_highway)
        return highway_series.map(_verdure_heuristic)

    # Project to a metric CRS for distance calculation (meters)
    try:
        green_projected = _project_to_meters(green_gdf)
        edges_projected = _project_to_meters(edges)
    except Exception as exc:
        print(f"    WARNING: Could not project geometries to meters ({exc}); using heuristic")
        highway_series = edges["highway"].apply(flatten_highway)
        return highway_series.map(_verdure_heuristic)

    green_union = green_projected.geometry.union_all()
    centroids = edges_projected.geometry.centroid
    dists = centroids.distance(green_union).to_numpy()

    # Piecewise score from distance
    near = dists <= GREEN_BUFFER_METERS
    mid = (dists > GREEN_BUFFER_METERS) & (dists <= GREEN_BUFFER_METERS * 4)

    scores = np.full(len(dists), 0.05, dtype=float)
    scores[near] = 1.0 - (dists[near] / GREEN_BUFFER_METERS) * 0.5
    scores[mid] = 0.3 - (dists[mid] / (GREEN_BUFFER_METERS * 4)) * 0.2

    scores = np.clip(scores, 0.0, 1.0)
    return pd.Series(np.round(scores, 3), index=edges.index)


def _verdure_heuristic(highway_type: str) -> float:
    """Fallback: estimate greenery from road type alone."""
    mapping = {
        "path": 0.7, "footway": 0.5, "pedestrian": 0.4,
        "living_street": 0.35, "residential": 0.3, "cycleway": 0.4,
        "track": 0.6, "steps": 0.2,
        "service": 0.15, "unclassified": 0.2,
        "tertiary": 0.15, "secondary": 0.1,
        "primary": 0.05, "trunk": 0.02, "motorway": 0.0,
    }
    return mapping.get(highway_type, 0.2)


def _compute_major_road_proximity(edges, type_route: pd.Series) -> pd.Series:
    """Compute how close each edge is to a major road (0=far, 1=adjacent)."""

    is_major = type_route.isin(MAJOR_HIGHWAY_TYPES)

    try:
        edges_proj = _project_to_meters(edges)
    except Exception as exc:
        print(f"    WARNING: Could not project edges to meters ({exc}); returning 0 proximity")
        return pd.Series(0.0, index=edges.index)

    if not is_major.any():
        return pd.Series(0.0, index=edges.index)

    major_union = edges_proj.loc[is_major, "geometry"].union_all()
    centroids = edges_proj.geometry.centroid
    dists = centroids.distance(major_union).to_numpy()

    scores = np.full(len(dists), 0.05, dtype=float)
    scores[dists <= 1000] = 0.2
    scores[dists <= 500] = 0.4
    scores[dists <= 200] = 0.7
    scores[dists <= 50] = 1.0
    # Major roads themselves are 1.0
    scores[is_major.to_numpy()] = 1.0

    return pd.Series(scores, index=edges.index)


# ---------------------------------------------------------------------------
#  Step 3 — Simulate missing data
# ---------------------------------------------------------------------------

def simulate_missing_data(df: pd.DataFrame, rng_seed: int = 42) -> pd.DataFrame:
    """Add simulated bruit (noise) and densite (density) columns."""

    rng = np.random.default_rng(rng_seed)
    n = len(df)

    print(f"\nSimulating missing data for {n:,} rows...")

    # --- bruit (noise from road type + jitter) ---
    base_noise = df["type_route"].map(NOISE_BY_HIGHWAY).fillna(NOISE_DEFAULT)
    jitter = rng.uniform(-JITTER_AMPLITUDE, JITTER_AMPLITUDE, size=n)
    df["bruit"] = np.clip(base_noise + jitter, 0.0, 1.0).round(3)

    # --- densite (density from distance to centre-ville + jitter) ---
    # We need edge midpoints in geographic coords. Reconstruct from u,v if needed.
    # Since we don't have geometry here, we'll use the graph nodes approach
    print("  Computing density from distance to centre-ville...")
    df["densite"] = _simulate_density(df, rng)

    return df


def _simulate_density(df: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    """Density based on approximate distance to centre-ville."""
    # If we don't have coordinates directly, assign density based on
    # type_route as a proxy (major roads tend to be more central)
    # But better: we should have passed coords in. Let's use a column if available.

    # We'll compute this in main() where we have access to the graph.
    # For now, this is a placeholder that gets overridden.
    return pd.Series(0.5, index=df.index)


def compute_density_from_graph(graph, df: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    """Compute density using node coordinates from the graph.

    If the graph seems to match Casablanca (near the provided hotspots), uses
    the hotspot heat approach. Otherwise, falls back to a generic "distance to
    graph center" banding, so the pipeline stays portable.
    """
    nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False)

    # Get midpoint coords for each edge (average of u and v node coords)
    u_coords = nodes.loc[df["u"].values, ["x", "y"]].values
    v_coords = nodes.loc[df["v"].values, ["x", "y"]].values
    mid_lon = (u_coords[:, 0] + v_coords[:, 0]) / 2
    mid_lat = (u_coords[:, 1] + v_coords[:, 1]) / 2

    # Decide whether Casablanca hotspots make sense for this graph
    center_lon = float(nodes["x"].median())
    center_lat = float(nodes["y"].median())
    min_center_to_hotspot_km = min(
        haversine_km(center_lon, center_lat, h_lon, h_lat) for h_lon, h_lat in DENSITY_HOTSPOTS
    )
    use_hotspots = min_center_to_hotspot_km < 30.0

    if use_hotspots:
        raw_densities = np.zeros(len(df))
        for h_lon, h_lat in DENSITY_HOTSPOTS:
            dists_km = haversine_km(mid_lon, mid_lat, h_lon, h_lat)
            influence = np.exp(-dists_km / 1.5)
            raw_densities += influence

        min_heat = raw_densities.min()
        max_heat = raw_densities.max()
        if max_heat > min_heat:
            normalized = (raw_densities - min_heat) / (max_heat - min_heat)
            base_density = 0.10 + (normalized * 0.80)
        else:
            base_density = np.full(len(df), 0.5)
    else:
        # Generic: distance to graph center, mapped by DENSITY_BANDS
        d_center_km = haversine_km(mid_lon, mid_lat, center_lon, center_lat)
        base_density = np.full(len(df), float(DENSITY_BANDS[-1][1]), dtype=float)
        prev_max = 0.0
        for max_km, base in DENSITY_BANDS:
            mask = (d_center_km > prev_max) & (d_center_km <= max_km)
            base_density[mask] = base
            prev_max = float(max_km)

    jitter = rng.uniform(-JITTER_AMPLITUDE, JITTER_AMPLITUDE, size=len(df))
    density = np.clip(base_density + jitter, 0.0, 1.0).round(3)

    return pd.Series(density, index=df.index)


# ---------------------------------------------------------------------------
#  Step 4 — Scoring (Phase 2 : Score de calme)
# ---------------------------------------------------------------------------

def normalize_minmax(series: pd.Series) -> pd.Series:
    """Normalize a series to [0, 1] using min-max scaling."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


def normalize_robust_minmax(series: pd.Series, q_low: float = 0.05, q_high: float = 0.95) -> pd.Series:
    """Robust min-max normalization using quantile clipping.

    This avoids extreme outliers dominating the scale.
    """
    lo = float(series.quantile(q_low))
    hi = float(series.quantile(q_high))
    if hi == lo:
        return pd.Series(0.5, index=series.index)
    clipped = series.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo)


def compute_score_fixed(df: pd.DataFrame, weights: dict | None = None) -> pd.Series:
    """Score de calme with fixed weights (Task 4).

    Formula: Score = α·(1-temps_norm) + β·(1-bruit) + γ·(1-densite) + δ·verdure

    Higher score = calmer route.
    All variables normalized to [0,1], weights sum to 1.0 → score ∈ [0,1].
    """
    w = weights or DEFAULT_WEIGHTS
    temps_norm = normalize_robust_minmax(df["temps"])

    # Integrate proximity to major roads: treat it as additional "traffic stress"
    if "proximite_principales" in df.columns:
        traffic_stress = np.maximum(df["bruit"].to_numpy(), df["proximite_principales"].to_numpy())
        traffic_stress = pd.Series(traffic_stress, index=df.index)
    else:
        traffic_stress = df["bruit"]

    score = (
        w["alpha"] * (1 - temps_norm) +
        w["beta"] * (1 - traffic_stress) +
        w["gamma"] * (1 - df["densite"]) +
        w["delta"] * df["verdure"]
    )

    return score.round(4)


def compute_profile_costs(df: pd.DataFrame) -> pd.DataFrame:
    """Compute specific routing costs for each user profile.
    
    Additive-safe formula (seconds-based):

      discomfort = weighted average of {traffic_stress, densite, (1-verdure)} in [0,1]
      lambda_profile = DISCOMFORT_LAMBDA_BASE * (1 - w_time)
      time_eff = temps * (1 + steps_factor) for steps
      cost = time_eff * (1 + lambda_profile * discomfort)

    Lower cost = better route.
    """
    required = {"temps", "bruit", "densite", "verdure", "type_route"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"compute_profile_costs missing columns: {missing}")

    proximite = df["proximite_principales"] if "proximite_principales" in df.columns else 0.0
    traffic_stress = np.maximum(df["bruit"].to_numpy(), np.asarray(proximite))
    traffic_stress = pd.Series(traffic_stress, index=df.index)

    is_steps = df["type_route"].astype(str).str.lower().eq("steps")

    for profile_name, w in USER_PROFILES.items():
        w_time = float(w.get("temps", 0.0))
        w_noise = float(w.get("bruit", 0.0))
        w_density = float(w.get("densite", 0.0))
        w_green = float(w.get("verdure", 0.0))

        non_time_sum = w_noise + w_density + w_green
        if non_time_sum <= 0:
            # Pure time minimization
            discomfort = 0.0
        else:
            discomfort = (
                (w_noise / non_time_sum) * traffic_stress
                + (w_density / non_time_sum) * df["densite"]
                + (w_green / non_time_sum) * (1.0 - df["verdure"])
            )

        lambda_profile = DISCOMFORT_LAMBDA_BASE * (1.0 - w_time)
        steps_factor = float(STEPS_TIME_FACTORS.get(profile_name, 1.0))
        time_eff = df["temps"] * (1.0 + steps_factor * is_steps.astype(float))

        cost = time_eff * (1.0 + lambda_profile * discomfort)
        df[f"cost_{profile_name}"] = cost.astype(float).round(4)

    return df


def compute_score_ml(df: pd.DataFrame, rng_seed: int = 42) -> tuple[pd.Series, dict]:
    """Learn scoring weights via ML regression (Task 5 — version avancée).

    Approach:
    1. Generate synthetic expert calm scores using a non-linear heuristic
       (simulates real-world expert annotations or user surveys).
    2. Train a Ridge regression to learn a linear approximation.
    3. Return predictions and learned weights.

    In production, synthetic labels would be replaced by real user feedback.
    """
    from sklearn.linear_model import Ridge
    from sklearn.metrics import r2_score, mean_absolute_error
    from sklearn.model_selection import train_test_split

    rng = np.random.default_rng(rng_seed)

    # Prepare normalized features (robust)
    temps_norm = normalize_robust_minmax(df["temps"])

    proximite = df["proximite_principales"] if "proximite_principales" in df.columns else 0.0
    traffic_stress = np.maximum(df["bruit"].to_numpy(), np.asarray(proximite))
    traffic_stress = pd.Series(traffic_stress, index=df.index)

    X = pd.DataFrame({
        "temps_inv":    1 - temps_norm,
        "calme_sonore": 1 - traffic_stress,
        "espace":       1 - df["densite"],
        "verdure":      df["verdure"],
    })

    # Synthetic expert labels (non-linear heuristic + noise)
    y_expert = (
        0.10 * (1 - temps_norm)
        + 0.30 * (1 - traffic_stress) ** 1.5        # penalize high traffic stress more
        + 0.25 * (1 - df["densite"]) ** 1.3        # penalize high density more
        + 0.20 * np.sqrt(df["verdure"])            # diminishing returns on green
        + 0.15 * df["verdure"] * (1 - traffic_stress)  # interaction: green+quiet bonus
    )
    noise = rng.normal(0, 0.03, size=len(df))
    y_train = np.clip(y_expert + noise, 0, 1)

    # Train/test split (still synthetic labels, but avoids in-sample metrics)
    idx = np.arange(len(df))
    idx_train, idx_test = train_test_split(idx, test_size=0.2, random_state=rng_seed, shuffle=True)

    model = Ridge(alpha=1.0)
    model.fit(X.iloc[idx_train], y_train[idx_train])

    y_pred = np.clip(model.predict(X), 0, 1).round(4)

    r2 = r2_score(y_train[idx_test], y_pred[idx_test])
    mae = mean_absolute_error(y_train[idx_test], y_pred[idx_test])

    # Learned weights
    feature_names = list(X.columns)
    learned = {name: round(coef, 4) for name, coef in zip(feature_names, model.coef_)}
    learned["intercept"] = round(float(model.intercept_), 4)

    print(f"\n  ML Scoring (Ridge Regression):")
    print(f"    R2 = {r2:.4f}  |  MAE = {mae:.4f}")
    print(f"    Learned weights: {learned}")
    print(f"    Fixed weights:   a={DEFAULT_WEIGHTS['alpha']}, b={DEFAULT_WEIGHTS['beta']}, "
          f"g={DEFAULT_WEIGHTS['gamma']}, d={DEFAULT_WEIGHTS['delta']}")

    return pd.Series(y_pred, index=df.index), learned


# ---------------------------------------------------------------------------
#  Step 5 — Routing (Phase 3 : Trouver le meilleur chemin)
# ---------------------------------------------------------------------------

import networkx as nx

# Routing profiles are now defined in USER_PROFILES and handled via compute_profile_costs.


def build_scored_graph(graph, df: pd.DataFrame) -> nx.MultiDiGraph:
    """Assign calm scores and profile costs as edge weights on the networkx graph."""
    scored = graph.copy()

    required = ["u", "v", "score_calme", "temps"] + [f"cost_{p}" for p in USER_PROFILES.keys()]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "build_scored_graph: DataFrame missing required columns: " + ", ".join(missing)
        )

    has_key = "key" in df.columns

    # Build a lookup: (u, v, key) -> dict of costs
    cost_lookup: dict[tuple[int, int, int], dict[str, float]] = {}
    for row in df.itertuples(index=False):
        u = int(getattr(row, "u"))
        v = int(getattr(row, "v"))
        k = int(getattr(row, "key")) if has_key else 0
        costs = {f"cost_{p}": float(getattr(row, f"cost_{p}")) for p in USER_PROFILES.keys()}
        costs["score_calme"] = float(getattr(row, "score_calme"))
        costs["temps"] = float(getattr(row, "temps"))
        cost_lookup[(u, v, k)] = costs

    for u, v, key, data in scored.edges(keys=True, data=True):
        edge_costs = cost_lookup.get((u, v, key))
        if edge_costs is None:
            continue
        data.update(edge_costs)
        data["cost_calme"] = 1.0 - edge_costs["score_calme"]

    return scored


def _heuristic(u_node, v_node) -> float:
    """A* heuristic: haversine distance (admissible for geographic graphs)."""
    # networkx passes node IDs; we need coords from the graph.
    # This is set up as a closure in get_best_route.
    return 0  # fallback (makes A* behave like Dijkstra)


def get_best_route(
    scored_graph: nx.MultiDiGraph,
    start: int | tuple[float, float],
    end: int | tuple[float, float],
    profile: str = "normal",
) -> dict:
    """Find the best route using Dijkstra with profile-specific edge weights.

    Args:
        scored_graph: Graph with cost_<profile> on edges
        start: Node ID (int) or (lat, lon) tuple
        end: Node ID (int) or (lat, lon) tuple
        profile: 'normal', 'autiste', 'fauteuil_roulant', 'equilibre'

    Returns:
        dict with path (node list) and statistics
    """
    if profile not in USER_PROFILES:
        raise ValueError(f"Unknown profile '{profile}'. Expected one of: {sorted(USER_PROFILES.keys())}")

    weight_attr = f"cost_{profile}"
    try:
        test_edge = list(scored_graph.edges(data=True))[0][2]
    except IndexError:
        return {"error": "Graph has no edges", "path": []}
    if weight_attr not in test_edge:
        raise KeyError(
            f"Graph edges are missing '{weight_attr}'. Did you call compute_profile_costs() + build_scored_graph()?"
        )

    # If start/end are (lat, lon), find nearest nodes
    if isinstance(start, (list, tuple)):
        start = ox.nearest_nodes(scored_graph, X=start[1], Y=start[0])
    if isinstance(end, (list, tuple)):
        end = ox.nearest_nodes(scored_graph, X=end[1], Y=end[0])

    # Run Dijkstra (handles MultiDiGraph reliably)
    try:
        path = nx.shortest_path(scored_graph, start, end, weight=weight_attr)
    except nx.NetworkXNoPath:
        return {"error": f"No path found from {start} to {end}", "path": []}

    # Compute route statistics
    total_length = 0.0
    total_time = 0.0
    total_cost = 0.0
    total_score_edge_mean = 0.0
    total_score_len_weighted = 0.0
    n_edges = 0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        # Get the best edge (lowest cost) between u and v
        edge_data = min(scored_graph[u][v].values(), key=lambda d: d.get(weight_attr, 1))
        edge_len = float(edge_data.get("length", 0.0) or 0.0)
        edge_time = float(edge_data.get("temps", edge_len / WALKING_SPEED_MS) or 0.0)
        edge_cost = float(edge_data.get(weight_attr, 0.0) or 0.0)
        edge_score = float(edge_data.get("score_calme", 0.5) or 0.5)

        total_length += edge_len
        total_time += edge_time
        total_cost += edge_cost
        total_score_edge_mean += edge_score
        total_score_len_weighted += edge_score * edge_len
        n_edges += 1

    avg_score_edges = total_score_edge_mean / n_edges if n_edges > 0 else 0.0
    avg_score_length = (total_score_len_weighted / total_length) if total_length > 0 else avg_score_edges

    return {
        "path": path,
        "n_edges": n_edges,
        "n_nodes": len(path),
        "total_length_m": round(total_length, 1),
        "total_time_s": round(total_time, 1),
        "total_time_min": round(total_time / 60, 1),
        "total_cost": round(total_cost, 4),
        "avg_score_calme": round(avg_score_length, 4),
        "avg_score_calme_edges": round(avg_score_edges, 4),
        "profile": profile,
    }


def build_scoring_dataframe(
    graph,
    place_name: str,
    *,
    use_verdure_query: bool = True,
    seed: int = 42,
    include_geometry: bool = False,
    compute_ml: bool = True,
) -> pd.DataFrame:
    """Canonical builder: graph -> edge dataframe with features, simulation, scores, costs."""
    df = build_edge_features(
        graph,
        place_name=place_name,
        use_verdure_query=use_verdure_query,
        include_geometry=include_geometry,
    )

    rng = np.random.default_rng(seed)

    # Simulate bruit (noise)
    base_noise = df["type_route"].map(NOISE_BY_HIGHWAY).fillna(NOISE_DEFAULT)
    jitter_noise = rng.uniform(-JITTER_AMPLITUDE, JITTER_AMPLITUDE, size=len(df))
    df["bruit"] = np.clip(base_noise + jitter_noise, 0.0, 1.0).round(3)

    # Density
    df["densite"] = compute_density_from_graph(graph, df, rng)

    # Time
    df["temps"] = (df["longueur"] / WALKING_SPEED_MS).round(2)

    # Scores + costs
    print("\n[Phase 2] Computing calme scores...")
    df["score_calme"] = compute_score_fixed(df)
    df = compute_profile_costs(df)

    if compute_ml:
        try:
            df["score_ml"], _learned = compute_score_ml(df, rng_seed=seed)
        except ImportError:
            print("  score_ml: skipped (install scikit-learn for ML scoring)")
            df["score_ml"] = df["score_calme"]
    else:
        df["score_ml"] = df["score_calme"]

    return df


def demo_routing(scored_graph: nx.MultiDiGraph) -> None:
    """Run a demo route to show routing works."""
    print("\n[Phase 3] Routing demo...")

    # Pick two well-known Casablanca locations (lat, lon)
    # Casa Voyageurs station -> Hassan II Mosque (a classic cross-city walk)
    start_point = (33.5886, -7.5891)   # Casa Voyageurs
    end_point = (33.6086, -7.6325)     # Hassan II Mosque

    print(f"  From: Casa Voyageurs ({start_point[0]}, {start_point[1]})")
    print(f"  To:   Hassan II Mosque ({end_point[0]}, {end_point[1]})")
    print()

    for profile in ["normal", "autiste", "fauteuil_roulant", "equilibre"]:
        result = get_best_route(scored_graph, start_point, end_point, profile=profile)

        if "error" in result:
            print(f"  [{profile:>10s}] {result['error']}")
            continue

        print(f"  [{profile:>10s}]  "
              f"{result['total_length_m']:,.0f}m  "
              f"({result['total_time_min']:.1f} min)  "
              f"calme={result['avg_score_calme']:.3f}  "
              f"edges={result['n_edges']}")


# ---------------------------------------------------------------------------
#  Step 6 — Export
# ---------------------------------------------------------------------------

def export_dataframe(df: pd.DataFrame, output_dir: str = "outputs", place_name: str = "") -> Path:
    """Write the final DataFrame to CSV (+ parquet if available)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(place_name) if place_name else "casablanca"

    # Select and order final columns
    final_columns = [
        "segment_id", "u", "v", "key",
        "longueur", "temps", "type_route", "verdure",
        "proximite_principales", "bruit", "densite",
        "score_calme", "score_ml",
    ]
    for p in USER_PROFILES.keys():
        col = f"cost_{p}"
        if col in df.columns:
            final_columns.append(col)
    df_out = df[final_columns].copy()

    # CSV
    csv_path = out_dir / f"routes_{slug}.csv"
    df_out.to_csv(csv_path, index=False)
    print(f"\n  CSV: {csv_path}")

    # Parquet (optional)
    try:
        parquet_path = out_dir / f"routes_{slug}.parquet"
        df_out.to_parquet(parquet_path, index=False)
        print(f"  Parquet: {parquet_path}")
    except Exception:
        print("  Parquet: skipped (install pyarrow for parquet support)")

    # Summary
    print(f"\n{'='*55}")
    print("  PIPELINE SUMMARY")
    print(f"{'='*55}")
    print(f"  Total routes: {len(df_out):,}")
    print()
    stat_cols = ["longueur", "temps", "verdure", "proximite_principales",
                 "bruit", "densite", "score_calme", "score_ml"]
    for p in USER_PROFILES.keys():
        col = f"cost_{p}"
        if col in df_out.columns:
            stat_cols.append(col)
    for col in stat_cols:
        mn = df_out[col].min()
        md = df_out[col].median()
        mx = df_out[col].max()
        print(f"  {col:<25s}  min={mn:.3f}  median={md:.3f}  max={mx:.3f}")

    top_types = df_out["type_route"].value_counts().head(5)
    print(f"\n  Top road types:")
    for t, c in top_types.items():
        print(f"    {t:<20s} {c:>7,}")
    print(f"{'='*55}")

    return csv_path


# ---------------------------------------------------------------------------
#  CLI + main
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NeuroRoute Calme — extract route features + simulate missing data"
    )
    parser.add_argument(
        "--place-name", default="Casablanca, Morocco",
        help="OSM place query (default: Casablanca, Morocco)",
    )
    parser.add_argument(
        "--output-dir", default="outputs",
        help="Output directory (default: outputs)",
    )
    parser.add_argument(
        "--cache-dir", default="cache",
        help="OSMnx cache directory (default: cache)",
    )
    parser.add_argument(
        "--no-verdure-query", action="store_true",
        help="Skip spatial green features query, use heuristic instead",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for simulation jitter (default: 42)",
    )
    parser.add_argument(
        "--no-routing", action="store_true",
        help="Skip routing demo",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        # Step 1 — Fetch graph
        graph = fetch_graph(args.place_name, cache_dir=args.cache_dir)

        df = build_scoring_dataframe(
            graph,
            place_name=args.place_name,
            use_verdure_query=not args.no_verdure_query,
            seed=args.seed,
            include_geometry=False,
            compute_ml=True,
        )
        print(f"  score_calme (fixed weights): median={df['score_calme'].median():.3f}")

        # Step 5 — Routing (Phase 3)
        if not args.no_routing:
            scored_graph = build_scored_graph(graph, df)
            demo_routing(scored_graph)

        # Step 6 — Export
        csv_path = export_dataframe(df, output_dir=args.output_dir, place_name=args.place_name)
        print(f"\nDone! Output: {csv_path}")
        return 0

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
