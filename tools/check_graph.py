import osmnx as ox
import os

GRAPHML_PATH = "cache/casablanca_walk.graphml"

def main():
    print("=" * 60)
    print("  Visualizing Raw Graph Data")
    print("=" * 60)
    
    if not os.path.exists(GRAPHML_PATH):
        print(f"Error: {GRAPHML_PATH} not found. Run demo.py first to cache the graph.")
        return

    print(f"[1] Loading graph from {GRAPHML_PATH}...")
    graph = ox.load_graphml(GRAPHML_PATH)
    
    print(f"    Graph loaded: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")

    print("\n[2] Generating high-resolution image...")
    print("    (Using a static PNG because 160,000+ interactive HTML edges would crash your browser)")
    
    os.makedirs("outputs", exist_ok=True)
    filepath = "outputs/casablanca_raw_graph.png"
    
    # Plotting the graph
    # node_size=1 makes nodes visible but small
    # edge_linewidth=0.2 makes the dense streets distinguishable
    fig, ax = ox.plot_graph(
        graph,
        node_size=1,
        node_color="#ff5e5e",
        edge_color="#444444",
        edge_linewidth=0.2,
        edge_alpha=0.5,
        bgcolor="#ffffff",
        show=False,
        save=True,
        filepath=filepath,
        dpi=600  # Very high resolution to zoom in
    )
    
    print(f"\n[+] Success! Open {filepath} to verify the Casablanca street network.")

if __name__ == "__main__":
    main()
