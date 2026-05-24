"""visualize.py — Map visualization of scoring and routing results.

Generates an interactive Folium map showing:
- Edge coloring by score_calme (green = calm, red = stressful)
- Demo route comparison across the canonical profiles
- Popup info on each edge (type, score, bruit, densite, verdure)

Run: python visualize.py
Output: outputs/map_scores.html  (scoring heatmap)
    outputs/map_routes.html  (route comparison)
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import osmnx as ox
import folium
from folium import plugins

from main import (
    fetch_graph,
    build_scoring_dataframe,
    build_scored_graph,
    get_best_route,
)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# Casablanca centre for map center
CASA_CENTER = [33.5731, -7.6114]

# Demo route: Casa Voyageurs -> Hassan II Mosque
START_POINT = (33.5886, -7.5891)
END_POINT   = (33.6086, -7.6325)

ROUTE_LABELS = {
    "normal": ("#3498db", "Profil NORMAL (priorité temps)"),
    "equilibre": ("#f39c12", "Profil ÉQUILIBRE"),
    "autiste": ("#9b59b6", "Profil AUTISTE (évite bruit + foule)"),
    "fauteuil_roulant": ("#27ae60", "Profil FAUTEUIL ROULANT (évite foule + escaliers)"),
}


def score_to_color(score: float) -> str:
    """Map 0-1 score to a red-yellow-green hex color."""
    r = int(255 * (1 - score))
    g = int(255 * score)
    b = 30
    return f"#{r:02x}{g:02x}{b:02x}"


def build_df_fast(graph, place_name: str) -> pd.DataFrame:
    """Build DataFrame using heuristic verdure (faster, no OSM green query)."""
    return build_scoring_dataframe(
        graph,
        place_name=place_name,
        use_verdure_query=False,
        seed=42,
        include_geometry=True,
        compute_ml=False,
    )


def make_score_map(graph, df: pd.DataFrame) -> folium.Map:
    """Create a choropleth-style map colored by score_calme."""
    print("  Building score map...")
    m = folium.Map(location=CASA_CENTER, zoom_start=13,
                   tiles="CartoDB dark_matter")

    # Sample 8000 edges for performance (full 164k is too heavy for HTML)
    sample = df.sample(n=min(8000, len(df)), random_state=42)

    for _, row in sample.iterrows():
        geom = row["geometry"]
        if geom is None:
            continue
        coords = [(lat, lon) for lon, lat in geom.coords]
        color = score_to_color(row["score_calme"])
        popup_html = (
            f"<b>{row['type_route']}</b><br>"
            f"Longueur: {row['longueur']:.0f}m<br>"
            f"Score calme: <b>{row['score_calme']:.3f}</b><br>"
            f"Bruit: {row['bruit']:.3f}<br>"
            f"Densité: {row['densite']:.3f}<br>"
            f"Verdure: {row['verdure']:.3f}"
        )
        folium.PolyLine(
            coords, color=color, weight=3, opacity=0.75,
            popup=folium.Popup(popup_html, max_width=200)
        ).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:#1a1a2e;padding:12px 16px;border-radius:8px;
                border:1px solid #444;color:white;font-family:sans-serif;font-size:13px;">
        <b>Score de calme</b><br>
        <span style="color:#ff1e1e">&#9644;</span> 0.0 — Stressant (bruyant, dense)<br>
        <span style="color:#ff8c00">&#9644;</span> 0.3 — Peu calme<br>
        <span style="color:#a8d000">&#9644;</span> 0.6 — Modéré<br>
        <span style="color:#00ff1e">&#9644;</span> 1.0 — Très calme (vert, silencieux)
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


def make_route_map(scored_graph: nx.MultiDiGraph, df: pd.DataFrame) -> folium.Map:
    """Create a map comparing routes for the canonical profiles."""
    import networkx as nx
    print("  Building route comparison map...")
    m = folium.Map(location=CASA_CENTER, zoom_start=14,
                   tiles="CartoDB positron")

    # Draw a subset of edges as faint background
    sample = df.sample(n=min(3000, len(df)), random_state=1)
    for _, row in sample.iterrows():
        geom = row.get("geometry")
        if geom is None:
            continue
        coords = [(lat, lon) for lon, lat in geom.coords]
        folium.PolyLine(coords, color="#aaaaaa", weight=1, opacity=0.3).add_to(m)

    # Draw each profile route
    nodes_gdf = ox.graph_to_gdfs(scored_graph, nodes=True, edges=False)

    for profile, (color, label) in ROUTE_LABELS.items():
        result = get_best_route(scored_graph, START_POINT, END_POINT, profile=profile)
        if "error" in result:
            print(f"    {profile}: no path — {result['error']}")
            continue

        path_coords = []
        for node_id in result["path"]:
            if node_id in nodes_gdf.index:
                row = nodes_gdf.loc[node_id]
                path_coords.append((row["y"], row["x"]))

        if path_coords:
            popup = (
                f"<b>{label}</b><br>"
                f"Distance: {result['total_length_m']:,.0f} m<br>"
                f"Temps: {result['total_time_min']:.1f} min<br>"
                f"Score calme moyen: {result['avg_score_calme']:.3f}<br>"
                f"Arêtes: {result['n_edges']}"
            )
            folium.PolyLine(
                path_coords, color=color, weight=5, opacity=0.9,
                popup=folium.Popup(popup, max_width=220)
            ).add_to(m)

        print(f"    [{profile}] {result['total_length_m']:,.0f}m  "
              f"calme={result['avg_score_calme']:.3f}  edges={result['n_edges']}")

    # Markers for start/end
    folium.Marker(START_POINT, popup="Départ: Casa Voyageurs",
                  icon=folium.Icon(color="blue", icon="play")).add_to(m)
    folium.Marker(END_POINT, popup="Arrivée: Mosquée Hassan II",
                  icon=folium.Icon(color="red", icon="stop")).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:12px 16px;border-radius:8px;
                border:1px solid #ccc;font-family:sans-serif;font-size:13px;">
        <b>Comparaison des profils</b><br>
        <span style="color:#3498db">&#9644;&#9644;&#9644;</span> Normal<br>
        <span style="color:#f39c12">&#9644;&#9644;&#9644;</span> Équilibre<br>
        <span style="color:#9b59b6">&#9644;&#9644;&#9644;</span> Autiste<br>
        <span style="color:#27ae60">&#9644;&#9644;&#9644;</span> Fauteuil roulant
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


if __name__ == "__main__":
    import networkx as nx

    print("=== NeuroRoute Calme — Visualization ===\n")

    # 1. Load graph
    graph = fetch_graph("Casablanca, Morocco")

    # 2. Build DataFrame (fast heuristic mode)
    print("\nBuilding DataFrame (heuristic mode)...")
    df = build_df_fast(graph, "Casablanca, Morocco")
    print(f"  {len(df):,} edges loaded")
    print(f"  score_calme: min={df['score_calme'].min():.3f}  "
          f"median={df['score_calme'].median():.3f}  max={df['score_calme'].max():.3f}")

    # 3. Build scored graph for routing
    print("\nBuilding scored graph...")
    sg = build_scored_graph(graph, df)

    # 4. Generate scoring map
    print("\n[Map 1] Score de calme")
    score_map = make_score_map(graph, df)
    score_path = OUTPUT_DIR / "map_scores.html"
    score_map.save(str(score_path))
    print(f"  Saved: {score_path}")

    # 5. Generate route comparison map
    print("\n[Map 2] Comparaison des itinéraires")
    route_map = make_route_map(sg, df)
    route_path = OUTPUT_DIR / "map_routes.html"
    route_map.save(str(route_path))
    print(f"  Saved: {route_path}")

    print("\nDone! Open the HTML files in your browser.")
