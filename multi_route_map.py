"""multi_route_map.py — Test multiple routes across Casablanca and visualize them.

Defines 6 real-world O/D pairs across Casablanca, runs the canonical profiles
(normal, equilibre, autiste, fauteuil_roulant) for each, and generates an interactive
Folium map showing:
    - All profile routes per O/D pair (different line styles)
    - Best-scored route highlighted in bold
    - Summary panel per route (distance, time, calm score)
    - Score heatmap layer as background

Run: python multi_route_map.py
Output: outputs/map_multi_routes.html
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import osmnx as ox
import folium
from folium.plugins import MeasureControl, MousePosition
import networkx as nx

from main import (
    fetch_graph,
    build_scoring_dataframe,
    build_scored_graph,
    get_best_route,
)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "map_multi_routes.html"

CASA_CENTER = [33.5731, -7.6114]

# ---------------------------------------------------------------------------
#  6 test routes — (name, start_lat, start_lon, end_lat, end_lon, emoji)
# ---------------------------------------------------------------------------
TEST_ROUTES = [
    {
        "name": "Casa Voyageurs -> Mosquee Hassan II",
        "desc": "Gare ferroviaire vers la grande mosquee",
        "start": (33.5886, -7.5891),
        "end":   (33.6086, -7.6325),
        "color_family": "#3498db",
        "icon": "[A]",
    },
    {
        "name": "Ain Diab -> Derb Sultan",
        "desc": "Bord de mer vers quartier populaire",
        "start": (33.5939, -7.6700),
        "end":   (33.5700, -7.5800),
        "color_family": "#e74c3c",
        "icon": "[B]",
    },
    {
        "name": "Maarif -> Sidi Belyout",
        "desc": "Quartier residentiel vers centre historique",
        "start": (33.5762, -7.6352),
        "end":   (33.5940, -7.6233),
        "color_family": "#2ecc71",
        "icon": "[C]",
    },
    {
        "name": "Hay Mohammadi -> Universite",
        "desc": "Quartier ouvrier vers campus universitaire",
        "start": (33.5592, -7.5947),
        "end":   (33.5490, -7.6520),
        "color_family": "#f39c12",
        "icon": "[D]",
    },
    {
        "name": "Anfa -> Casa-Port",
        "desc": "Quartier residentiel verse le port",
        "start": (33.5871, -7.6479),
        "end":   (33.6020, -7.6145),
        "color_family": "#9b59b6",
        "icon": "[E]",
    },
    {
        "name": "Racine -> Parc Ligue Arabe",
        "desc": "Quartier moderne vers le grand parc central",
        "start": (33.5820, -7.6440),
        "end":   (33.5942, -7.6375),
        "color_family": "#1abc9c",
        "icon": "[F]",
    },
]

# Profile styles: (dash, opacity, weight, label)
PROFILES = ["normal", "equilibre", "autiste", "fauteuil_roulant"]
PROFILE_STYLES = {
    "normal":    {"dash_array": "8,6",  "opacity": 0.75, "weight": 3, "label": "Normal (plus rapide)"},
    "equilibre": {"dash_array": "1,0",  "opacity": 0.75, "weight": 3, "label": "Équilibre"},
    "autiste":   {"dash_array": "1,0",  "opacity": 0.95, "weight": 5, "label": "Autiste (plus calme)"},
    "fauteuil_roulant": {"dash_array": "2,6",  "opacity": 0.85, "weight": 5, "label": "Fauteuil roulant (accessible)"},
}

def score_to_color(score: float) -> str:
    r = int(255 * (1 - score))
    g = int(200 * score)
    return f"#{r:02x}{g:02x}28"

def shade(hex_color: str, factor: float) -> str:
    """Darken or lighten a hex color by factor (0.5=darker, 1.5=lighter)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    r = min(255, int(r * factor))
    g = min(255, int(g * factor))
    b = min(255, int(b * factor))
    return f"#{r:02x}{g:02x}{b:02x}"

def build_df_fast(graph) -> pd.DataFrame:
    return build_scoring_dataframe(
        graph,
        place_name="Casablanca, Morocco",
        use_verdure_query=False,
        seed=42,
        include_geometry=True,
        compute_ml=False,
    )


def get_path_coords(scored_graph, path: list[int]) -> list[tuple]:
    """Extract (lat, lon) coordinates for each node in the path."""
    nodes_gdf = ox.graph_to_gdfs(scored_graph, nodes=True, edges=False)
    coords = []
    for node_id in path:
        if node_id in nodes_gdf.index:
            row = nodes_gdf.loc[node_id]
            coords.append((float(row["y"]), float(row["x"])))
    return coords


def run_all_routes(scored_graph) -> list[dict]:
    """Run all canonical profiles for all 6 routes, return structured results."""
    all_results = []
    for route_def in TEST_ROUTES:
        print(f"\n  {route_def['icon']} {route_def['name']}")
        route_data = {
            "meta": route_def,
            "profiles": {},
            "best_profile": None,
            "best_score": -1,
        }
        for profile in PROFILES:
            r = get_best_route(
                scored_graph,
                start=route_def["start"],
                end=route_def["end"],
                profile=profile,
            )
            if "error" not in r:
                coords = get_path_coords(scored_graph, r["path"])
                r["coords"] = coords
                route_data["profiles"][profile] = r
                if r["avg_score_calme"] > route_data["best_score"]:
                    route_data["best_score"] = r["avg_score_calme"]
                    route_data["best_profile"] = profile
                print(f"    [{profile:>10s}]  "
                      f"{r['total_length_m']:>6,.0f}m  "
                      f"{r['total_time_min']:>5.1f}min  "
                      f"score={r['avg_score_calme']:.3f}  "
                      f"edges={r['n_edges']}")
            else:
                print(f"    [{profile:>10s}]  ERROR: {r['error']}")
        all_results.append(route_data)
    return all_results


def build_map(graph, df: pd.DataFrame, all_results: list[dict]) -> folium.Map:
    m = folium.Map(
        location=CASA_CENTER,
        zoom_start=13,
        tiles="CartoDB dark_matter",
    )

    # --- Background: faint score heatmap ---
    bg_layer = folium.FeatureGroup(name="Heatmap score de calme", show=True)
    sample = df.sample(n=min(5000, len(df)), random_state=7)
    for _, row in sample.iterrows():
        geom = row.get("geometry")
        if geom is None:
            continue
        coords = [(lat, lon) for lon, lat in geom.coords]
        color = score_to_color(row["score_calme"])
        folium.PolyLine(
            coords, color=color, weight=2, opacity=0.4,
            tooltip=f"{row['type_route']} | score={row['score_calme']:.2f}"
        ).add_to(bg_layer)
    bg_layer.add_to(m)

    # --- Per-route layers ---
    route_index = 1
    for route_data in all_results:
        meta = route_data["meta"]
        base_color = meta["color_family"]

        # One FeatureGroup per route
        route_layer = folium.FeatureGroup(
            name=f"Route {route_index}: {meta['icon']} {meta['name']}",
            show=True,
        )

        # Draw each profile
        profile_colors = {
            "normal": shade(base_color, 0.6),
            "equilibre": base_color,
            "autiste": shade(base_color, 1.4),
            "fauteuil_roulant": shade(base_color, 1.1),
        }
        for profile, r in route_data["profiles"].items():
            coords = r.get("coords", [])
            if not coords:
                continue

            style = PROFILE_STYLES[profile]
            color = profile_colors[profile]
            is_best = (profile == route_data["best_profile"])

            popup_html = f"""
            <div style="font-family:sans-serif;min-width:200px">
            <b style="font-size:14px">{meta['icon']} {meta['name']}</b><br>
            <hr style="margin:4px 0">
            <b>Profil:</b> {style['label']}<br>
            <b>Distance:</b> {r['total_length_m']:,.0f} m<br>
            <b>Temps:</b> {r['total_time_min']:.1f} min<br>
            <b>Score calme:</b> <b style="color:{'#2ecc71' if is_best else '#e74c3c'}">{r['avg_score_calme']:.3f}</b>
            {'<br><b style="color:#f1c40f">★ MEILLEUR SCORE</b>' if is_best else ''}<br>
            <b>Nb arêtes:</b> {r['n_edges']}
            </div>
            """
            folium.PolyLine(
                coords,
                color=color,
                weight=style["weight"] if not is_best else 6,
                opacity=style["opacity"],
                dash_array=style["dash_array"],
                popup=folium.Popup(popup_html, max_width=240),
                tooltip=f"{meta['icon']} {profile} | {r['total_length_m']:,.0f}m | score={r['avg_score_calme']:.3f}",
            ).add_to(route_layer)

        # Start / End markers
        start_popup = f"""
        <div style="font-family:sans-serif">
        <b>Départ {route_index}</b><br>
        {meta['icon']} {meta['name']}<br>
        <i>{meta['desc']}</i>
        </div>
        """
        end_popup = f"""
        <div style="font-family:sans-serif">
        <b>Arrivée {route_index}</b><br>
        {meta['icon']} {meta['name']}<br>
        <i>Score calme moyen: {route_data['best_score']:.3f}</i>
        </div>
        """
        folium.CircleMarker(
            meta["start"], radius=9,
            color="white", fill=True, fill_color=base_color, fill_opacity=1,
            popup=folium.Popup(start_popup, max_width=200),
            tooltip=f"Départ {route_index}: {meta['name']}",
        ).add_to(route_layer)
        folium.Marker(
            meta["start"],
            icon=folium.DivIcon(
                html=f'<div style="font-size:11px;font-weight:bold;color:white;'
                     f'background:{base_color};border-radius:50%;width:20px;'
                     f'height:20px;display:flex;align-items:center;justify-content:center;'
                     f'border:2px solid white;margin-top:-10px;margin-left:-10px">{route_index}</div>',
                icon_size=(20, 20),
            ),
        ).add_to(route_layer)

        folium.CircleMarker(
            meta["end"], radius=9,
            color="white", fill=True, fill_color=shade(base_color, 0.7), fill_opacity=1,
            popup=folium.Popup(end_popup, max_width=200),
            tooltip=f"Arrivée {route_index}: {meta['name']}",
        ).add_to(route_layer)
        folium.Marker(
            meta["end"],
            icon=folium.DivIcon(
                html=f'<div style="font-size:11px;font-weight:bold;color:white;'
                     f'background:{shade(base_color, 0.7)};border-radius:3px;'
                     f'width:20px;height:20px;display:flex;align-items:center;'
                     f'justify-content:center;border:2px solid white;'
                     f'margin-top:-10px;margin-left:-10px">{route_index}</div>',
                icon_size=(20, 20),
            ),
        ).add_to(route_layer)

        route_layer.add_to(m)
        route_index += 1

    # --- Layer control ---
    folium.LayerControl(collapsed=False).add_to(m)
    MeasureControl().add_to(m)

    # --- Legend ---
    legend_html = """
    <div style="position:fixed;top:20px;right:20px;z-index:1000;
                background:#1a1a2e;padding:14px 16px;border-radius:10px;
                border:1px solid #444;color:white;font-family:'Segoe UI',sans-serif;
                font-size:12px;min-width:200px;box-shadow:0 4px 12px rgba(0,0,0,0.5)">
      <div style="font-size:14px;font-weight:bold;margin-bottom:8px;
                  border-bottom:1px solid #555;padding-bottom:6px">
        NeuroRoute Calme
      </div>
      <div style="margin-bottom:8px">
        <b>Profils de route</b><br>
                <span style="font-family:monospace">--- </span> Normal<br>
                <span style="font-family:monospace">&mdash;&mdash; </span> Équilibre<br>
                <span style="font-family:monospace">&#9644;&#9644;&#9644; </span> Autiste<br>
                <span style="font-family:monospace">··· </span> Fauteuil roulant
      </div>
      <div style="margin-bottom:8px">
        <b>Score de calme (fond)</b><br>
        <span style="color:#ff2828">&#9644;</span> 0.0 Stressant<br>
        <span style="color:#c8a000">&#9644;</span> 0.5 Modéré<br>
        <span style="color:#00c828">&#9644;</span> 1.0 Très calme
      </div>
      <div style="margin-bottom:4px"><b>Routes testées</b></div>
    """
    for i, rd in enumerate(all_results, 1):
        legend_html += (
            f'<span style="color:{rd["meta"]["color_family"]}">&#9644;</span> '
            f'{i}. {rd["meta"]["icon"]} {rd["meta"]["name"].split("→")[0].strip()}'
            f' → ...  <small>({rd["best_score"]:.3f})</small><br>'
        )
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

        # --- Summary table (Autiste vs Normal) ---
    table_rows = ""
    for i, rd in enumerate(all_results, 1):
        best = rd["profiles"].get(rd["best_profile"], {})
        autiste_r = rd["profiles"].get("autiste", {})
        normal_r = rd["profiles"].get("normal", {})
        diff_m = (autiste_r.get("total_length_m", 0) - normal_r.get("total_length_m", 0))
        diff_score = (autiste_r.get("avg_score_calme", 0) - normal_r.get("avg_score_calme", 0))
        table_rows += f"""
        <tr>
          <td style="padding:4px 8px;color:{rd['meta']['color_family']};font-weight:bold">{i}</td>
          <td style="padding:4px 8px">{rd['meta']['icon']} {rd['meta']['name']}</td>
                    <td style="padding:4px 8px;text-align:right">{autiste_r.get('total_length_m',0):,.0f}m</td>
                    <td style="padding:4px 8px;text-align:right">{autiste_r.get('total_time_min',0):.1f} min</td>
                    <td style="padding:4px 8px;text-align:right;color:#2ecc71;font-weight:bold">{autiste_r.get('avg_score_calme',0):.3f}</td>
          <td style="padding:4px 8px;text-align:right;color:{'#e74c3c' if diff_m < 0 else '#f39c12'}">+{diff_m:,.0f}m</td>
          <td style="padding:4px 8px;text-align:right;color:#2ecc71">+{diff_score:.3f}</td>
        </tr>"""

    summary_html = f"""
    <div style="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
                z-index:1000;background:#1a1a2e;padding:12px 16px;border-radius:10px;
                border:1px solid #444;color:white;font-family:'Segoe UI',sans-serif;
                font-size:11px;box-shadow:0 4px 12px rgba(0,0,0,0.5);max-width:760px">
      <div style="font-size:13px;font-weight:bold;margin-bottom:8px;
                  border-bottom:1px solid #555;padding-bottom:4px">
        Comparaison des itinéraires — Profil AUTISTE vs NORMAL
      </div>
      <table style="border-collapse:collapse;width:100%">
        <thead>
          <tr style="color:#aaa;border-bottom:1px solid #444">
            <th style="padding:2px 8px">#</th>
            <th style="padding:2px 8px">Trajet</th>
            <th style="padding:2px 8px;text-align:right">Distance</th>
            <th style="padding:2px 8px;text-align:right">Temps</th>
            <th style="padding:2px 8px;text-align:right">Score calme</th>
            <th style="padding:2px 8px;text-align:right">Détour</th>
            <th style="padding:2px 8px;text-align:right">Gain calme</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
    """
    m.get_root().html.add_child(folium.Element(summary_html))
    return m


if __name__ == "__main__":
    print("=" * 60)
    print("  NeuroRoute Calme — Multi-Route Visualization")
    print("=" * 60)

    print("\n[1] Loading graph...")
    graph = fetch_graph("Casablanca, Morocco")

    print("\n[2] Building DataFrame (heuristic mode)...")
    df = build_df_fast(graph)
    print(f"  {len(df):,} edges  |  "
          f"score range=[{df['score_calme'].min():.3f}, {df['score_calme'].max():.3f}]")

    print("\n[3] Building scored graph...")
    sg = build_scored_graph(graph, df)

    print("\n[4] Computing routes for all O/D pairs...")
    all_results = run_all_routes(sg)

    print("\n[5] Building map...")
    m = build_map(graph, df, all_results)
    m.save(str(OUTPUT_PATH))
    print(f"\n  Saved: {OUTPUT_PATH}")

    # Print summary table
    print("\n" + "=" * 75)
    print(f"  {'Route':<40} {'Autiste':>8}  {'Normal':>8}  {'Detour':>8}  {'Gain':>6}")
    print("=" * 75)
    for i, rd in enumerate(all_results, 1):
        a = rd["profiles"].get("autiste", {})
        n = rd["profiles"].get("normal", {})
        if a and n:
            diff = a.get("total_length_m", 0) - n.get("total_length_m", 0)
            gain = a.get("avg_score_calme", 0) - n.get("avg_score_calme", 0)
            name = rd["meta"]["name"][:38]
            print(f"  {i}. {name:<38}  "
                  f"{a.get('total_length_m',0):>6,.0f}m  "
                  f"{n.get('total_length_m',0):>6,.0f}m  "
                  f"+{diff:>5,.0f}m  "
                  f"+{gain:.3f}")
    print("=" * 75)
    print("\nDone! Open outputs/map_multi_routes.html in your browser.")
