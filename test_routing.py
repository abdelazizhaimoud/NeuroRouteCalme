"""Quick test to verify routing profiles produce different routes."""

from main import fetch_graph, build_scoring_dataframe, build_scored_graph, get_best_route


graph = fetch_graph("Casablanca, Morocco")
df = build_scoring_dataframe(
    graph,
    place_name="Casablanca, Morocco",
    use_verdure_query=False,
    seed=42,
    include_geometry=False,
    compute_ml=False,
)
sg = build_scored_graph(graph, df)

# Longer cross-city route
start = (33.5939, -7.6700)
end = (33.5700, -7.5800)

print("\nRouting test: Ain Diab -> Derb Sultan")
print("-" * 60)
for p in ["normal", "equilibre", "autiste", "fauteuil_roulant"]:
    r = get_best_route(sg, start, end, profile=p)
    if "error" in r:
        print(f"  {p}: ERROR - {r['error']}")
    else:
        pf = r["profile"]
        print(f"  {pf:>10s}: {r['total_length_m']:,.0f}m  "
              f"{r['total_time_min']:.1f}min  "
              f"calme={r['avg_score_calme']:.3f}  "
              f"edges={r['n_edges']}")
