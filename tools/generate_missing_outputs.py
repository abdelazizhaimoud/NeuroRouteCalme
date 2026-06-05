"""generate_mohammedia_maps.py — Generate missing map files for Mohammedia."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import folium
import geopandas as gpd
import osmnx as ox

sys.path.insert(0, str(Path('.').absolute()))
from main import fetch_graph, get_best_route, build_scored_graph

OUT_DIR = Path("outputs/mohammedia")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------
# 1. Load graph + scored data
# -----------------------------------------------------------------------
print("[1/4] Loading Mohammedia graph...")
graph = fetch_graph("Mohammedia, Morocco")

print("[2/4] Loading scored CSV...")
df = pd.read_csv("outputs/mohammedia/routes_mohammedia.csv")
scored_graph = build_scored_graph(graph, df)

# -----------------------------------------------------------------------
# 2. map_scores.html — choropleth
# -----------------------------------------------------------------------
print("[3/4] Building map_scores.html...")
edges = ox.graph_to_gdfs(graph, nodes=False, edges=True).reset_index()
df_merge = df[["u", "v", "key", "score_calme"]].copy()
edges_merged = edges.merge(df_merge, on=["u", "v", "key"], how="left")
edges_merged["score_calme"] = edges_merged["score_calme"].fillna(0.5)


def score_to_color(s):
    s = float(np.clip(s, 0, 1))
    r = int(round(255 * (1 - s)))
    g = int(round(255 * s))
    return f"#{r:02x}{g:02x}1e"


center_lat = float(edges_merged.geometry.centroid.y.mean())
center_lon = float(edges_merged.geometry.centroid.x.mean())

m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles="CartoDB dark_matter")

gdf = gpd.GeoDataFrame(
    edges_merged[["score_calme", "geometry"]],
    geometry="geometry",
    crs="EPSG:4326",
)
gdf["color"] = gdf["score_calme"].apply(score_to_color)

folium.GeoJson(
    gdf[["score_calme", "color", "geometry"]],
    name="Score calme ML",
    smooth_factor=0.0,
    style_function=lambda feat: {
        "color": feat["properties"]["color"],
        "weight": 2,
        "opacity": 0.8,
    },
).add_to(m)

legend_html = """
<div style="position:fixed;bottom:30px;left:30px;z-index:1000;
            background:#1a1a2e;padding:12px 16px;border-radius:8px;
            border:1px solid #444;color:white;font-family:sans-serif;font-size:13px;">
    <b>Score de calme (Predit par ML)</b><br>
    <span style="color:#ff1e1e">&#9644;</span> 0.0 - Stressant<br>
    <span style="color:#ff8c00">&#9644;</span> 0.3 - Peu calme<br>
    <span style="color:#a8d000">&#9644;</span> 0.6 - Modere<br>
    <span style="color:#00ff1e">&#9644;</span> 1.0 - Tres calme
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))
folium.LayerControl().add_to(m)

map_path = OUT_DIR / "map_scores.html"
m.save(str(map_path))
print(f"  [OK] Saved: {map_path}")

# -----------------------------------------------------------------------
# 3. map_routes_demo.html — demo routes with 4 profiles
# -----------------------------------------------------------------------
print("[4/4] Building map_routes_demo.html...")

# Two well-known points in Mohammedia
DEMO_ROUTES = [
    {
        "start": (33.7244, -7.3829),  # Gare Mohammedia
        "end":   (33.6866, -7.3867),  # Plage Mohammedia
        "label": "Gare -> Plage"
    },
    {
        "start": (33.7000, -7.4120),  # Quartier industriel
        "end":   (33.7244, -7.3829),  # Gare Mohammedia
        "label": "Industriel -> Gare"
    },
]

PROFILE_COLORS = {
    "normal": "#3498db",
    "equilibre": "#f39c12",
    "autiste": "#9b59b6",
    "fauteuil_roulant": "#2ecc71",
}

m2 = folium.Map(location=[33.7100, -7.3950], zoom_start=13, tiles="CartoDB dark_matter")

for demo in DEMO_ROUTES:
    start_pt = demo["start"]
    end_pt = demo["end"]

    # Add start/end markers
    folium.Marker(
        location=list(start_pt),
        tooltip=f"Depart : {demo['label']}",
        icon=folium.Icon(color="blue", icon="play"),
    ).add_to(m2)
    folium.Marker(
        location=list(end_pt),
        tooltip=f"Arrivee : {demo['label']}",
        icon=folium.Icon(color="red", icon="flag"),
    ).add_to(m2)

    for profile, color in PROFILE_COLORS.items():
        result = get_best_route(scored_graph, start_pt, end_pt, profile=profile)
        if "error" in result:
            print(f"  [SKIP] {demo['label']} / {profile}: {result['error']}")
            continue

        coords = []
        for nid in result["path"]:
            if nid in scored_graph.nodes:
                nd = scored_graph.nodes[nid]
                coords.append([float(nd["y"]), float(nd["x"])])

        if len(coords) < 2:
            continue

        folium.PolyLine(
            coords,
            color=color,
            weight=4,
            opacity=0.85,
            tooltip=(
                f"{profile} | {demo['label']}<br>"
                f"{result['total_length_m']:.0f}m | {result['total_time_min']} min<br>"
                f"Score: {result['avg_score_calme']:.3f}"
            ),
        ).add_to(m2)

legend2_html = """
<div style="position:fixed;bottom:30px;left:30px;z-index:1000;
            background:#1a1a2e;padding:12px 16px;border-radius:8px;
            border:1px solid #444;color:white;font-family:sans-serif;font-size:13px;">
    <b>Routes de demo - Mohammedia</b><br>
    <span style="color:#3498db">&#9644;</span> Normal<br>
    <span style="color:#f39c12">&#9644;</span> Equilibre<br>
    <span style="color:#9b59b6">&#9644;</span> Autiste<br>
    <span style="color:#2ecc71">&#9644;</span> Fauteuil roulant
</div>
"""
m2.get_root().html.add_child(folium.Element(legend2_html))
folium.LayerControl().add_to(m2)

demo_path = OUT_DIR / "map_routes_demo.html"
m2.save(str(demo_path))
print(f"  [OK] Saved: {demo_path}")

# -----------------------------------------------------------------------
# 4. model_comparison.png — bar chart of the 3 models
# -----------------------------------------------------------------------
import matplotlib.pyplot as plt
import json

metrics_path = Path("outputs/models/model_metrics.json")
if metrics_path.exists():
    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    results = metrics.get("results", {})
    if results:
        models = list(results.keys())
        r2_vals = [results[m]["R2"] for m in models]
        mae_vals = [results[m]["MAE"] for m in models]

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        fig.suptitle("Model Comparison — Casablanca Test Set", fontsize=14, fontweight="bold")

        colors = ["#3498db", "#2ecc71", "#e74c3c"]
        axes[0].bar(models, r2_vals, color=colors)
        axes[0].set_title("R² Score (higher is better)")
        axes[0].set_ylim(0, 1.05)
        for i, v in enumerate(r2_vals):
            axes[0].text(i, v + 0.01, f"{v:.4f}", ha="center", fontsize=9)

        axes[1].bar(models, mae_vals, color=colors)
        axes[1].set_title("MAE (lower is better)")
        for i, v in enumerate(mae_vals):
            axes[1].text(i, v + 0.0005, f"{v:.4f}", ha="center", fontsize=9)

        plt.tight_layout()
        out_cmp = Path("outputs/models/model_comparison.png")
        plt.savefig(out_cmp, dpi=300)
        plt.close()
        print(f"  [OK] Saved: {out_cmp}")

print("\n[DONE] All missing files generated.")
