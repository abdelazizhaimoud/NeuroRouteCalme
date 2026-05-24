"""demo.py — Quick demonstration for the teacher.

Run:  python demo.py

Shows the full pipeline in action:
  1. Load the graph
  2. Score every street
  3. Find the best route for 3 profiles
  4. Save a map with the result
"""
from main import fetch_graph, build_scoring_dataframe, build_scored_graph, get_best_route
import osmnx as ox

# ===================================================================
#  CHANGE THESE TWO POINTS TO DEMO ANY ROUTE IN CASABLANCA
# ===================================================================

START = (33.5730, -7.5383)    # Anfa (residential district)
END   = (33.5627, -7.5537)    # Casa-Port (near the port)

START_NAME = "Anfa"
END_NAME   = "Casa-Port"
# ===================================================================

def build_df(graph):
    # Keep this wrapper for backward-compat with demo_100_routes.py
    return build_scoring_dataframe(
        graph,
        place_name="Casablanca, Morocco",
        use_verdure_query=False,
        seed=42,
        include_geometry=False,
        compute_ml=False,
    )

if __name__ == "__main__":
    print("=" * 60)
    print("  NeuroRoute Calme  --  DEMO")
    print("=" * 60)

    # Step 1
    import os
    GRAPHML_PATH = "cache/casablanca_walk.graphml"
    
    if os.path.exists(GRAPHML_PATH):
        print(f"\n[1] Loading Casablanca graph from {GRAPHML_PATH} (FAST)...")
        graph = ox.load_graphml(GRAPHML_PATH)
    else:
        print("\n[1] Loading Casablanca graph from OSM...")
        graph = fetch_graph("Casablanca, Morocco")
        print(f"    Saving to {GRAPHML_PATH} for faster loading next time...")
        os.makedirs("cache", exist_ok=True)
        ox.save_graphml(graph, GRAPHML_PATH)

    # Step 2
    import time
    print("\n[2] Scoring all streets...")
    start_time = time.time()
    df = build_df(graph)
    scoring_time = time.time() - start_time
    print(f"    {len(df):,} edges scored in {scoring_time:.3f} seconds")
    print(f"    score range: [{df['score_calme'].min():.3f} .. {df['score_calme'].max():.3f}]")

    # Step 3
    print("\n[3] Building scored graph...")
    sg = build_scored_graph(graph, df)

    # Step 4
    print(f"\n[4] Finding routes:")
    print(f"    FROM: {START_NAME}  {START}")
    print(f"    TO:   {END_NAME}  {END}")
    print()

    # Find nearest nodes ONCE to avoid extremely slow ox.nearest_nodes inside loop
    start_node = ox.nearest_nodes(sg, X=START[1], Y=START[0])
    end_node = ox.nearest_nodes(sg, X=END[1], Y=END[0])

    results = {}
    profiles = ["normal", "autiste", "fauteuil_roulant"]
    
    for profile in profiles:
        r = get_best_route(sg, start_node, end_node, profile=profile)
        results[profile] = r
        if "error" not in r:
            print(f"    {profile:>12s}  |  "
                  f"{r['total_length_m']:>6,.0f} m  |  "
                  f"{r['total_time_min']:>5.1f} min  |  "
                  f"score calme = {r['avg_score_calme']:.3f}  |  "
                  f"{r['n_edges']} edges")
        else:
            print(f"    {profile:>12s}  |  ERROR: {r['error']}")

    # Step 5 — Generate map
    print("\n[5] Generating map...")
    try:
        import folium

        m = folium.Map(
            location=[(START[0]+END[0])/2, (START[1]+END[1])/2],
            zoom_start=14,
            tiles="CartoDB positron",
        )

        colors = {"normal": "#3498db", "fauteuil_roulant": "#f39c12", "autiste": "#9b59b6"}
        weights = {"normal": 3, "fauteuil_roulant": 5, "autiste": 7}

        for profile in ["normal", "fauteuil_roulant", "autiste"]:
            r = results.get(profile)
            if not r or "error" in r:
                continue
            coords = []
            for nid in r["path"]:
                if nid in sg.nodes:
                    # Direct dictionary access is instantly fast
                    coords.append((float(sg.nodes[nid]['y']), float(sg.nodes[nid]['x'])))
            if coords:
                folium.PolyLine(
                    coords,
                    color=colors[profile],
                    weight=weights[profile],
                    opacity=0.85,
                    tooltip=f"PROFIL: {profile.upper()} | {r['total_length_m']:,.0f}m | score={r['avg_score_calme']:.3f}",
                ).add_to(m)

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

        folium.Marker(START, popup=f"Depart: {START_NAME}",
                      icon=folium.Icon(color="blue", icon="play")).add_to(m)
        folium.Marker(END, popup=f"Arrivee: {END_NAME}",
                      icon=folium.Icon(color="red", icon="stop")).add_to(m)

        from pathlib import Path
        Path("outputs").mkdir(exist_ok=True)
        m.save("outputs/demo_route.html")
        print("    Saved: outputs/demo_route.html")
    except ImportError:
        print("    (folium not installed, skipping map)")

    # Summary
    n = results.get("normal", {})
    a = results.get("autiste", {})
    if n and a and "error" not in n and "error" not in a:
        detour = a["total_length_m"] - n["total_length_m"]
        print(f"\n    L'autiste fait un détour de +{detour:,.0f}m pour éviter le bruit et la foule.")

    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)
