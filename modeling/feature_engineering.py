"""modeling/feature_engineering.py — Extract transferable features from any OSMnx graph.

This module builds a DataFrame of ML-ready features that can be computed
on *any* city's OSM graph, making the trained model portable.

It reuses `build_edge_features()` from main.py for the base features
(longueur, type_route, verdure, proximite_principales) and adds:
  - road_hierarchy, noise_proxy   (ordinal encoding of highway type)
  - poi_density_100m/200m         (replaces hardcoded densite)
  - maxspeed_kph, lanes_count     (from OSM tags, with imputation)
  - has_sidewalk, is_lit          (boolean OSM tags)
  - surface_quality               (ordinal surface encoding)
  - log_length, walking_time_s    (derived)
  - connectivity                  (node degree)

Usage:
    from modeling.feature_engineering import extract_transferable_features
    df = extract_transferable_features(graph, "Mohammedia, Morocco")
"""

from __future__ import annotations

import ast
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import Point

# Add project root to path so we can import main.py helpers
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from main import (
    build_edge_features,
    flatten_highway,
    _ensure_crs_4326,
    _project_to_meters,
)

from modeling.config import (
    DEFAULT_MAXSPEED,
    DEFAULT_MAXSPEED_FALLBACK,
    FEATURE_COLS,
    POI_BUFFER_METERS,
    POI_TAGS,
    ROAD_HIERARCHY,
    ROAD_HIERARCHY_DEFAULT,
    SURFACE_QUALITY,
    SURFACE_QUALITY_DEFAULT,
    WALKING_SPEED_MS,
)


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def extract_transferable_features(
    graph,
    place_name: str,
    *,
    use_verdure_query: bool = True,
    include_base_columns: bool = True,
) -> pd.DataFrame:
    """Extract all transferable features from an OSMnx pedestrian graph.

    This is the single entry point for feature extraction.  It produces a
    DataFrame with exactly the columns listed in ``FEATURE_COLS`` (plus
    base columns u, v, key, segment_id, longueur, type_route when
    *include_base_columns* is True).

    Parameters
    ----------
    graph : networkx.MultiDiGraph
        An OSMnx pedestrian graph (``network_type="walk"``).
    place_name : str
        OSM place name (e.g. ``"Casablanca, Morocco"``).  Used for spatial
        queries (green features, POI density).
    use_verdure_query : bool
        If True, query OSM for green features.  If False, use a heuristic
        based on highway type (faster, less accurate).
    include_base_columns : bool
        If True, keep ``u, v, key, segment_id, longueur, type_route`` in the
        output alongside the ML feature columns.

    Returns
    -------
    pd.DataFrame
        DataFrame with one row per edge.  Contains at minimum all columns
        in ``FEATURE_COLS``.
    """
    print(f"\n{'='*60}")
    print(f"  Feature Engineering — {place_name}")
    print(f"{'='*60}")

    # --- Step 1: Base features from main.py ---
    print("\n[1/7] Extracting base features (longueur, type_route, verdure, proximité)...")
    df = build_edge_features(
        graph,
        place_name=place_name,
        use_verdure_query=use_verdure_query,
        include_geometry=False,
    )

    # Get the raw edges GeoDataFrame for additional tag extraction
    edges_gdf = ox.graph_to_gdfs(graph, nodes=False, edges=True).reset_index()

    # --- Step 2: Road hierarchy + noise proxy ---
    print("[2/7] Encoding road hierarchy and noise proxy...")
    df["road_hierarchy"] = _encode_road_hierarchy(df["type_route"])
    df["noise_proxy"] = (df["road_hierarchy"] / 10.0).round(4)

    # --- Step 3: POI density ---
    print("[3/7] Computing POI density...")
    for buffer_m in POI_BUFFER_METERS:
        col_name = f"poi_density_{buffer_m}m"
        df[col_name] = _compute_poi_density(graph, df, place_name, buffer_m)

    # --- Step 4: maxspeed + lanes ---
    print("[4/7] Extracting maxspeed and lanes...")
    df["maxspeed_kph"] = _extract_maxspeed(edges_gdf, df["type_route"])
    df["lanes_count"] = _extract_lanes(edges_gdf)

    # --- Step 5: Boolean tags (sidewalk, lit) + surface quality ---
    print("[5/7] Extracting sidewalk, lit, surface quality...")
    df["has_sidewalk"] = _extract_has_sidewalk(edges_gdf)
    df["is_lit"] = _extract_is_lit(edges_gdf)
    df["surface_quality"] = _extract_surface_quality(edges_gdf)

    # --- Step 6: Derived features ---
    print("[6/7] Computing derived features (log_length, walking_time, connectivity)...")
    df["log_length"] = np.log1p(df["longueur"]).round(4)
    df["walking_time_s"] = (df["longueur"] / WALKING_SPEED_MS).round(2)
    df["connectivity"] = _compute_connectivity(graph, df)

    # --- Step 7: Final validation ---
    print("[7/7] Validating features...")
    _validate_features(df)

    # Summary
    print(f"\n  Features extracted: {len(FEATURE_COLS)} columns")
    print(f"  Total edges: {len(df):,}")
    for col in FEATURE_COLS:
        if col in df.columns:
            mn = df[col].min()
            md = df[col].median()
            mx = df[col].max()
            na = df[col].isna().sum()
            na_str = f"  NaN={na}" if na > 0 else ""
            print(f"    {col:<25s}  min={mn:>8.3f}  median={md:>8.3f}  max={mx:>8.3f}{na_str}")
    print(f"{'='*60}\n")

    if not include_base_columns:
        return df[FEATURE_COLS].copy()

    # Return base columns + feature columns
    base_cols = ["u", "v", "key", "segment_id", "longueur", "type_route"]
    extra_cols = [c for c in base_cols if c in df.columns]
    return df[extra_cols + FEATURE_COLS].copy()


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------

def _encode_road_hierarchy(type_route: pd.Series) -> pd.Series:
    """Map highway type string to ordinal (1=quiet … 10=loud)."""
    return type_route.map(ROAD_HIERARCHY).fillna(ROAD_HIERARCHY_DEFAULT).astype(int)


def _compute_poi_density(
    graph,
    df: pd.DataFrame,
    place_name: str,
    buffer_m: int,
) -> pd.Series:
    """Count POIs (amenity, shop, tourism) within *buffer_m* of each edge midpoint.

    Uses OSM spatial query via ``ox.features_from_place()`` and a projected
    buffer around edge centroids.  Falls back to 0 if the query fails.
    """
    try:
        pois = ox.features_from_place(place_name, tags=POI_TAGS)
        print(f"    Found {len(pois):,} POIs for {place_name}")
    except Exception as exc:
        print(f"    WARNING: POI query failed ({exc}), returning 0 density")
        return pd.Series(0.0, index=df.index)

    if pois.empty:
        print(f"    No POIs found, returning 0 density")
        return pd.Series(0.0, index=df.index)

    # Get edge midpoint coordinates
    nodes_gdf = ox.graph_to_gdfs(graph, nodes=True, edges=False)
    u_x = nodes_gdf.loc[df["u"].values, "x"].values
    u_y = nodes_gdf.loc[df["u"].values, "y"].values
    v_x = nodes_gdf.loc[df["v"].values, "x"].values
    v_y = nodes_gdf.loc[df["v"].values, "y"].values

    mid_lon = (u_x + v_x) / 2
    mid_lat = (u_y + v_y) / 2

    # Create GeoDataFrame of edge midpoints
    midpoints = gpd.GeoDataFrame(
        {"idx": df.index},
        geometry=[Point(lon, lat) for lon, lat in zip(mid_lon, mid_lat)],
        crs="EPSG:4326",
    )

    # Project to metric CRS for buffer computation
    try:
        midpoints_proj = _project_to_meters(midpoints)
        pois_proj = _project_to_meters(pois)
    except Exception as exc:
        print(f"    WARNING: Projection failed ({exc}), returning 0 density")
        return pd.Series(0.0, index=df.index)

    # Get POI centroids (some POIs are polygons)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        poi_points = pois_proj.geometry.centroid

    # Buffer around midpoints
    buffers = midpoints_proj.geometry.buffer(buffer_m)

    # Count POIs in each buffer using spatial index
    poi_points_gdf = gpd.GeoDataFrame(geometry=poi_points, crs=midpoints_proj.crs)
    poi_sindex = poi_points_gdf.sindex

    counts = np.zeros(len(df), dtype=float)
    for i, buf in enumerate(buffers):
        matches = list(poi_sindex.query(buf, predicate="intersects"))
        counts[i] = len(matches)

    # Normalize to [0, 1] using robust min-max
    if counts.max() > 0:
        q95 = np.percentile(counts, 95)
        if q95 > 0:
            normalized = np.clip(counts / q95, 0, 1)
        else:
            normalized = np.clip(counts / counts.max(), 0, 1)
    else:
        normalized = counts

    return pd.Series(normalized.round(4), index=df.index)


def _extract_maxspeed(edges_gdf: pd.DataFrame, type_route: pd.Series) -> pd.Series:
    """Extract maxspeed from OSM tags, imputing from highway type when missing."""
    maxspeed_raw = edges_gdf.get("maxspeed")

    if maxspeed_raw is None:
        # Column doesn't exist at all — impute everything from highway type
        return type_route.map(DEFAULT_MAXSPEED).fillna(DEFAULT_MAXSPEED_FALLBACK).round(1)

    def _parse_speed(val) -> float | None:
        """Parse a single maxspeed value to km/h."""
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, list):
            val = val[0] if val else None
            if val is None:
                return None
        val = str(val).strip().lower()
        if val in ("", "none", "nan", "signals", "walk"):
            return None
        # Handle "XX mph"
        if "mph" in val:
            try:
                return float(val.replace("mph", "").strip()) * 1.60934
            except ValueError:
                return None
        # Handle plain numbers
        try:
            return float(val)
        except ValueError:
            return None

    parsed = maxspeed_raw.apply(_parse_speed)

    # Impute missing values from highway type defaults
    missing_mask = parsed.isna()
    if missing_mask.any():
        imputed = type_route[missing_mask].map(DEFAULT_MAXSPEED).fillna(DEFAULT_MAXSPEED_FALLBACK)
        parsed = parsed.fillna(imputed)

    return parsed.astype(float).round(1)


def _extract_lanes(edges_gdf: pd.DataFrame) -> pd.Series:
    """Extract lane count from OSM tags, defaulting to 0 when missing."""
    lanes_raw = edges_gdf.get("lanes")

    if lanes_raw is None:
        return pd.Series(0, index=edges_gdf.index, dtype=int)

    def _parse_lanes(val) -> int:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return 0
        if isinstance(val, (int, float)):
            return max(0, int(val))
        if isinstance(val, list):
            val = val[0] if val else None
            if val is None:
                return 0
        try:
            return max(0, int(float(str(val).strip())))
        except (ValueError, TypeError):
            return 0

    return lanes_raw.apply(_parse_lanes).astype(int)


def _extract_has_sidewalk(edges_gdf: pd.DataFrame) -> pd.Series:
    """Check if any sidewalk tag indicates presence of a sidewalk."""
    result = pd.Series(0, index=edges_gdf.index, dtype=int)

    for col_name in ["sidewalk", "sidewalk:left", "sidewalk:right"]:
        col = edges_gdf.get(col_name)
        if col is None:
            continue

        def _has_sw(val) -> bool:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return False
            s = str(val).strip().lower()
            return s not in ("", "no", "none", "nan")

        has_it = col.apply(_has_sw).astype(int)
        result = result | has_it

    return result.astype(int)


def _extract_is_lit(edges_gdf: pd.DataFrame) -> pd.Series:
    """Check if the street is lit (lit=yes)."""
    lit_raw = edges_gdf.get("lit")
    if lit_raw is None:
        return pd.Series(0, index=edges_gdf.index, dtype=int)

    def _is_lit(val) -> int:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return 0
        s = str(val).strip().lower()
        return 1 if s in ("yes", "24/7", "automatic", "dusk-dawn") else 0

    return lit_raw.apply(_is_lit).astype(int)


def _extract_surface_quality(edges_gdf: pd.DataFrame) -> pd.Series:
    """Extract and encode surface quality as an ordinal value (1=worst, 5=best)."""
    surface_raw = edges_gdf.get("surface")
    if surface_raw is None:
        return pd.Series(SURFACE_QUALITY_DEFAULT, index=edges_gdf.index, dtype=int)

    def _encode_surface(val) -> int:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return SURFACE_QUALITY_DEFAULT
        if isinstance(val, list):
            val = val[0] if val else None
            if val is None:
                return SURFACE_QUALITY_DEFAULT
        s = str(val).strip().lower()
        return SURFACE_QUALITY.get(s, SURFACE_QUALITY_DEFAULT)

    return surface_raw.apply(_encode_surface).astype(int)


def _compute_connectivity(graph, df: pd.DataFrame) -> pd.Series:
    """Compute the degree (number of connecting edges) of each edge's source node."""
    degree_dict = dict(graph.degree())
    return df["u"].map(degree_dict).fillna(2).astype(int)


def _validate_features(df: pd.DataFrame) -> None:
    """Check that all required feature columns exist and have no unexpected NaNs."""
    missing_cols = [c for c in FEATURE_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Feature engineering failed — missing columns: {missing_cols}"
        )

    for col in FEATURE_COLS:
        nan_count = df[col].isna().sum()
        if nan_count > 0:
            pct = nan_count / len(df) * 100
            print(f"    WARNING: {col} has {nan_count} NaN values ({pct:.1f}%)")
            # Fill NaNs with 0 for ML readiness
            df[col] = df[col].fillna(0)


# ---------------------------------------------------------------------------
#  Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Quick test: extract features from the cached Casablanca graph."""
    from main import fetch_graph

    graph = fetch_graph("Casablanca, Morocco")
    df = extract_transferable_features(
        graph,
        "Casablanca, Morocco",
        use_verdure_query=False,  # fast mode for testing
    )
    print(f"\nResult: {df.shape[0]:,} rows × {df.shape[1]} columns")
    print(f"Columns: {list(df.columns)}")
    print(f"\nFirst 5 rows:")
    print(df.head())
