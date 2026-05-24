"""map_all_edges_scores.py — Visualize ALL edges colored by score_calme.

This script generates a Folium HTML map where every edge is drawn and colored
according to its calm score:
  - Red   = stressful
  - Green = calm

NOTE: Casablanca has ~165k edges; the generated HTML can be large and may load
slowly in the browser.

Run:
  python map_all_edges_scores.py

Output:
  outputs/map_scores_all_edges.html
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import folium
import geopandas as gpd

from main import fetch_graph, build_scoring_dataframe


OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "map_scores_all_edges.html"

PLACE_NAME = "Casablanca, Morocco"

# Discretize the red->green gradient into a small set of bins.
# This keeps HTML smaller than using a unique color per edge.
N_COLOR_BINS = 24


def _score_to_color(score: float) -> str:
    """Map a 0-1 score to a red-yellow-green-ish hex color."""
    s = float(np.clip(score, 0.0, 1.0))
    r = int(round(255 * (1.0 - s)))
    g = int(round(255 * s))
    b = 30
    return f"#{r:02x}{g:02x}{b:02x}"


def _bin_color_map(n_bins: int) -> dict[int, str]:
    n_bins = int(max(2, n_bins))
    return {i: _score_to_color(i / (n_bins - 1)) for i in range(n_bins)}


def _graph_center_latlon(graph) -> tuple[float, float]:
    ys = []
    xs = []
    for _, data in graph.nodes(data=True):
        y = data.get("y")
        x = data.get("x")
        if y is None or x is None:
            continue
        ys.append(float(y))
        xs.append(float(x))
    if not ys:
        return (33.5731, -7.6114)  # Casablanca fallback
    return (float(np.mean(ys)), float(np.mean(xs)))


def main() -> None:
    print("=" * 60)
    print("  NeuroRoute Calme — All Edges Score Map")
    print("=" * 60)

    print("\n[1] Loading graph...")
    graph = fetch_graph(PLACE_NAME)

    print("\n[2] Building DataFrame (canonical pipeline, geometry included)...")
    df = build_scoring_dataframe(
        graph,
        place_name=PLACE_NAME,
        use_verdure_query=False,
        seed=42,
        include_geometry=True,
        compute_ml=False,
    )

    print("\n[3] Preparing GeoDataFrame...")
    gdf = gpd.GeoDataFrame(
        df[["score_calme"]].copy(),
        geometry=df["geometry"],
        crs="EPSG:4326",
    )
    gdf = gdf[gdf.geometry.notnull()].copy()
    gdf["score_bin"] = np.floor(np.clip(gdf["score_calme"], 0.0, 1.0) * (N_COLOR_BINS - 1) + 1e-12).astype(int)

    color_map = _bin_color_map(N_COLOR_BINS)
    gdf["color"] = gdf["score_bin"].map(color_map)

    center_lat, center_lon = _graph_center_latlon(graph)

    print("\n[4] Building Folium map...")
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="CartoDB dark_matter",
    )

    # Keep feature properties minimal to reduce output size
    gdf_out = gdf[["score_calme", "score_bin", "color", "geometry"]]

    folium.GeoJson(
        gdf_out,
        name="Score calme (toutes les arêtes)",
        smooth_factor=0.0,
        style_function=lambda feat: {
            "color": feat["properties"]["color"],
            "weight": 2,
            "opacity": 0.75,
        },
    ).add_to(m)

    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:#1a1a2e;padding:12px 16px;border-radius:8px;
                border:1px solid #444;color:white;font-family:sans-serif;font-size:13px;">
        <b>Score de calme (arêtes)</b><br>
        <span style="color:#ff1e1e">&#9644;</span> 0.0 — Stressant<br>
        <span style="color:#ff8c00">&#9644;</span> 0.3 — Peu calme<br>
        <span style="color:#a8d000">&#9644;</span> 0.6 — Modéré<br>
        <span style="color:#00ff1e">&#9644;</span> 1.0 — Très calme
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(collapsed=True).add_to(m)

    print(f"\n[5] Saving: {OUTPUT_PATH}")
    m.save(str(OUTPUT_PATH))
    print("Done! Open the HTML file in your browser.")


if __name__ == "__main__":
    main()
