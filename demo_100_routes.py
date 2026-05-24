import os
import random
import numpy as np
import networkx as nx
import folium
import osmnx as ox

from main import (
    fetch_graph, build_scored_graph, get_best_route, haversine_km
)
from demo import build_df

def generate_100_routes_demo():
    print("=" * 60)
    print("  NeuroRoute Calme -- 100 Routes Demo")
    print("=" * 60)

    GRAPHML_PATH = "cache/casablanca_walk.graphml"
    
    if os.path.exists(GRAPHML_PATH):
        print(f"\n[1] Loading Casablanca graph from {GRAPHML_PATH}...")
        graph = ox.load_graphml(GRAPHML_PATH)
    else:
        print("\n[1] Loading Casablanca graph from OSM...")
        graph = fetch_graph("Casablanca, Morocco")
        os.makedirs("cache", exist_ok=True)
        ox.save_graphml(graph, GRAPHML_PATH)

    print("\n[2] Scoring all streets...")
    df = build_df(graph)

    print("\n[3] Building scored graph...")
    sg = build_scored_graph(graph, df)

    print("\n[4] Selecting 100 random node pairs (>1km apart)...")
    nodes = list(sg.nodes(data=True))
    
    valid_pairs = []
    # Set a seed so results are reproducible
    random.seed(42)
    
    while len(valid_pairs) < 100:
        u = random.choice(nodes)
        v = random.choice(nodes)
        
        # Calculate straight line distance
        dist = haversine_km(u[1]['x'], u[1]['y'], v[1]['x'], v[1]['y'])
        
        # Only accept if distance is between 1km and 5km (to avoid extremely long routes that take forever to compute)
        if 1.0 <= dist <= 5.0:
            valid_pairs.append((u[0], v[0]))

    print(f"    Found {len(valid_pairs)} valid pairs.")

    print("\n[5] Computing routes for all 3 profiles...")
    
    routes_list = []
    
    for i, (start_node, end_node) in enumerate(valid_pairs):
        if (i+1) % 10 == 0:
            print(f"    Processing route {i+1}/100...")
            
        route_info = {
            "start": (sg.nodes[start_node]['y'], sg.nodes[start_node]['x']),
            "end": (sg.nodes[end_node]['y'], sg.nodes[end_node]['x']),
            "profiles": {}
        }
            
        for profile in ["normal", "fauteuil_roulant", "autiste"]:
            r = get_best_route(sg, start_node, end_node, profile=profile)
            if "error" not in r:
                coords = [(float(sg.nodes[nid]['y']), float(sg.nodes[nid]['x'])) for nid in r["path"] if nid in sg.nodes]
                route_info["profiles"][profile] = {
                    "coords": coords,
                    "length": r['total_length_m'],
                    "score": r['avg_score_calme']
                }
        routes_list.append(route_info)

    print("\n[6] Generating map with individual Route Selection...")
    # Center map on Casablanca
    m = folium.Map(
        location=[33.573, -7.589],
        zoom_start=13,
        tiles="CartoDB dark_matter",
    )

    colors = {"normal": "#3498db", "fauteuil_roulant": "#f39c12", "autiste": "#9b59b6"}
    # Different weights so overlapping lines are all visible (normal is thinnest, autiste is thickest)
    weights = {"normal": 3, "fauteuil_roulant": 6, "autiste": 9}

    # Add a clear Legend
    legend_html = '''
     <div style="position: fixed; 
                 bottom: 50px; left: 50px; width: 220px; height: 110px; 
                 border:2px solid grey; z-index:9999; font-size:14px;
                 background-color:white; padding: 10px; border-radius: 5px;">
     <b>Profils Utilisateurs</b><br>
                <i style="background:#3498db; width: 14px; height: 14px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> Normal<br>
                <i style="background:#f39c12; width: 14px; height: 14px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> Fauteuil roulant<br>
                <i style="background:#9b59b6; width: 14px; height: 14px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> Autiste<br>
     </div>
     '''
    m.get_root().html.add_child(folium.Element(legend_html))

    # Add each route as a separate toggleable group
    for i, route_info in enumerate(routes_list):
        # Only show the first route by default so the map isn't tangled
        fg = folium.FeatureGroup(name=f"Trajet {i+1}", show=(i == 0))
        
        # Add Start/End markers
        folium.Marker(route_info["start"], icon=folium.Icon(color="green", icon="play")).add_to(fg)
        folium.Marker(route_info["end"], icon=folium.Icon(color="red", icon="stop")).add_to(fg)
        
        for profile, data in route_info["profiles"].items():
            folium.PolyLine(
                data["coords"],
                color=colors[profile],
                weight=weights[profile],
                opacity=0.8,
                tooltip=f"Trajet {i+1} | PROFIL: {profile.upper()} | {data['length']:,.0f}m | score={data['score']:.3f}",
            ).add_to(fg)
            
        fg.add_to(m)

    # Add layer control so the user can check/uncheck specific routes
    folium.LayerControl(collapsed=False).add_to(m)

    os.makedirs("outputs", exist_ok=True)
    m.save("outputs/demo_100_routes.html")
    print("\n    Saved: outputs/demo_100_routes.html")
    print("    Open this file. In the Layer Control (top right), you can uncheck 'Trajet 1' and check 'Trajet 2', etc., to view routes one by one!")

if __name__ == "__main__":
    generate_100_routes_demo()
