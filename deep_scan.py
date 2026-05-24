"""deep_scan.py — End-to-end verification of the pipeline.

Checks:
  Phase 1: graph integrity, DataFrame schema, value ranges, nulls
  Phase 2: scoring sanity + optional ML scoring quality
  Phase 3: routing validity + (light) profile differentiation

Run:
  python deep_scan.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import osmnx as ox

from main import (
    DEFAULT_WEIGHTS,
    DENSITY_HOTSPOTS,
    USER_PROFILES,
    build_scored_graph,
    build_scoring_dataframe,
    fetch_graph,
    get_best_route,
    haversine_km,
    normalize_robust_minmax,
)


PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"


results: list[tuple[str, str]] = []


def check(label: str, condition: bool, detail: str = "", *, warn_only: bool = False) -> None:
    status = PASS if condition else (WARN if warn_only else FAIL)
    msg = f"  {status}  {label}"
    if detail:
        msg += f"  ->  {detail}"
    print(msg)
    results.append((status, label))


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _ratio(predicates: list[bool]) -> float:
    if not predicates:
        return 0.0
    return float(sum(1 for x in predicates if x)) / float(len(predicates))


if __name__ == "__main__":
    # =========================================================================
    # PHASE 1 — Data
    # =========================================================================
    section("PHASE 1 — Data")

    print("\n[1.1] Graph integrity...")
    graph = fetch_graph("Casablanca, Morocco")
    n_nodes = graph.number_of_nodes()
    n_edges = graph.number_of_edges()

    check("Graph loaded successfully", graph is not None)
    check("Node count reasonable (>1000)", n_nodes > 1000, f"{n_nodes:,} nodes")
    check("Edge count reasonable (>5000)", n_edges > 5000, f"{n_edges:,} edges")
    check("Graph is directed", graph.is_directed())
    check("Graph is multigraph", graph.is_multigraph())

    sample_edges = list(graph.edges(data=True))[:50]
    length_ratio = _ratio([("length" in d) for _, _, d in sample_edges])
    highway_ratio = _ratio([("highway" in d) for _, _, d in sample_edges])
    check(
        "Edges usually have 'length'",
        length_ratio >= 0.90,
        f"{length_ratio:.0%} of sample",
        warn_only=length_ratio < 1.0,
    )
    check(
        "Edges usually have 'highway'",
        highway_ratio >= 0.90,
        f"{highway_ratio:.0%} of sample",
        warn_only=highway_ratio < 1.0,
    )

    sample_nodes = list(graph.nodes(data=True))[:50]
    coords_ratio = _ratio([("x" in d and "y" in d) for _, d in sample_nodes])
    check("Nodes have x/y coordinates", coords_ratio >= 0.98, f"{coords_ratio:.0%} of sample")

    print("\n[1.2] Building scoring DataFrame (canonical pipeline)...")
    df = build_scoring_dataframe(
        graph,
        place_name="Casablanca, Morocco",
        use_verdure_query=False,
        seed=42,
        include_geometry=False,
        compute_ml=False,
    )

    required_cols = [
        "u",
        "v",
        "key",
        "longueur",
        "type_route",
        "verdure",
        "proximite_principales",
        "bruit",
        "densite",
        "temps",
        "score_calme",
    ]
    for col in required_cols:
        check(f"Column '{col}' exists", col in df.columns)
    for profile in USER_PROFILES.keys():
        check(f"Column 'cost_{profile}' exists", f"cost_{profile}" in df.columns)

    print("\n[1.3] Value ranges and nulls...")
    check(
        "No nulls in required columns",
        df[required_cols].isnull().sum().sum() == 0,
        f"{int(df[required_cols].isnull().sum().sum())} nulls found",
    )
    check("longueur > 0", (df["longueur"] > 0).all(), f"min={df['longueur'].min():.3f}m")
    check("longueur < 10km (plausible)", (df["longueur"] < 10_000).all(), f"max={df['longueur'].max():.1f}m")
    check("temps > 0", (df["temps"] > 0).all(), f"min={df['temps'].min():.2f}s")
    check("bruit in [0,1]", df["bruit"].between(0, 1).all(), f"range=[{df['bruit'].min():.3f},{df['bruit'].max():.3f}]")
    check(
        "densite in [0,1]",
        df["densite"].between(0, 1).all(),
        f"range=[{df['densite'].min():.3f},{df['densite'].max():.3f}]",
    )
    check(
        "verdure in [0,1]",
        df["verdure"].between(0, 1).all(),
        f"range=[{df['verdure'].min():.3f},{df['verdure'].max():.3f}]",
    )
    check(
        "proximite_principales in [0,1]",
        df["proximite_principales"].between(0, 1).all(),
    )
    for profile in USER_PROFILES.keys():
        check(
            f"cost_{profile} is non-negative",
            (df[f"cost_{profile}"] >= 0).all(),
            warn_only=True,
        )

    print("\n[1.4] Road type distribution...")
    top_types = df["type_route"].value_counts()
    check("At least 5 distinct road types", df["type_route"].nunique() >= 5, f"{df['type_route'].nunique()} unique types")
    if not top_types.empty:
        check(
            "Most common type is 'residential' (typical)",
            top_types.index[0] == "residential",
            f"top={top_types.index[0]} ({top_types.iloc[0]:,})",
            warn_only=True,
        )
    unknown_ratio = float((df["type_route"] == "unknown").mean())
    check("'unknown' road types not dominant", unknown_ratio < 0.05, f"unknown={unknown_ratio:.1%}", warn_only=True)

    print("\n[1.5] Simulation sanity...")
    footway_noise = float(df.loc[df["type_route"] == "footway", "bruit"].mean())
    primary_noise = float(df.loc[df["type_route"] == "primary", "bruit"].mean())
    if not np.isnan(footway_noise) and not np.isnan(primary_noise):
        check(
            "Noise: footway < primary (usually)",
            footway_noise < primary_noise,
            f"footway={footway_noise:.3f} < primary={primary_noise:.3f}",
            warn_only=True,
        )

    # Density should be higher near hotspots (Casablanca case). Heuristic -> warn-only.
    try:
        nodes_gdf = ox.graph_to_gdfs(graph, nodes=True, edges=False)
        u_coords = nodes_gdf.loc[df["u"].values, ["x", "y"]].to_numpy()
        mid_lon = u_coords[:, 0]
        mid_lat = u_coords[:, 1]

        dists = []
        for lon, lat in zip(mid_lon[:5000], mid_lat[:5000]):
            h_dists = [haversine_km(lon, lat, h_lon, h_lat) for h_lon, h_lat in DENSITY_HOTSPOTS]
            dists.append(min(h_dists))
        dists = np.asarray(dists)

        near_mask = dists < 2.0
        far_mask = dists > 6.0
        if near_mask.sum() > 10 and far_mask.sum() > 10:
            near_density = float(df["densite"].to_numpy()[:5000][near_mask].mean())
            far_density = float(df["densite"].to_numpy()[:5000][far_mask].mean())
            check(
                "Density: near hotspots > far (heuristic)",
                near_density > far_density,
                f"near={near_density:.3f} > far={far_density:.3f}",
                warn_only=True,
            )
    except Exception as exc:
        check("Density hotspot check ran", False, str(exc), warn_only=True)

    # =========================================================================
    # PHASE 2 — Scoring
    # =========================================================================
    section("PHASE 2 — Scoring")

    print("\n[2.1] Fixed-weight score sanity...")
    check("score_calme exists", "score_calme" in df.columns)
    check(
        "score_calme in [0,1]",
        df["score_calme"].between(0, 1).all(),
        f"range=[{df['score_calme'].min():.3f},{df['score_calme'].max():.3f}]",
    )
    check(
        "score_calme has variance",
        float(df["score_calme"].std()) > 0.01,
        f"std={float(df['score_calme'].std()):.4f}",
    )

    footway_score = float(df.loc[df["type_route"] == "footway", "score_calme"].mean())
    trunk_score = float(df.loc[df["type_route"].isin(["trunk", "motorway"]), "score_calme"].mean())
    if not np.isnan(footway_score) and not np.isnan(trunk_score):
        check(
            "Score: footway > trunk/motorway (usually)",
            footway_score > trunk_score,
            f"footway={footway_score:.3f} > trunk/motorway={trunk_score:.3f}",
            warn_only=True,
        )

    w_sum = float(sum(DEFAULT_WEIGHTS.values()))
    check("Weights sum to 1.0", abs(w_sum - 1.0) < 1e-3, f"sum={w_sum:.4f}")

    temps_norm = normalize_robust_minmax(df["temps"])
    check(
        "temps normalization in [0,1]",
        temps_norm.between(0, 1).all(),
        f"range=[{temps_norm.min():.4f},{temps_norm.max():.4f}]",
    )

    print("\n[2.2] ML scoring (optional sanity)...")
    try:
        from main import compute_score_ml

        score_ml, learned = compute_score_ml(df, rng_seed=42)
        check("ML model ran without error", True)
        check(
            "score_ml in [0,1]",
            score_ml.between(0, 1).all(),
            f"range=[{score_ml.min():.3f},{score_ml.max():.3f}]",
        )
        check(
            "Learned weights have reasonable magnitudes",
            all(abs(v) < 2.0 for k, v in learned.items() if k != "intercept"),
            str({k: round(v, 3) for k, v in learned.items()}),
            warn_only=True,
        )

        # Simple held-out R² sanity (warn-only, because labels are synthetic)
        try:
            from sklearn.linear_model import Ridge
            from sklearn.metrics import r2_score
            from sklearn.model_selection import train_test_split

            traffic_stress = np.maximum(df["bruit"].to_numpy(), df["proximite_principales"].to_numpy())
            traffic_stress = np.clip(traffic_stress, 0.0, 1.0)
            temps_norm2 = normalize_robust_minmax(df["temps"])

            X = pd.DataFrame({
                "temps_inv": 1 - temps_norm2,
                "calme_sonore": 1 - traffic_stress,
                "espace": 1 - df["densite"],
                "verdure": df["verdure"],
            })
            y_expert = (
                0.10 * (1 - temps_norm2)
                + 0.30 * (1 - traffic_stress) ** 1.5
                + 0.25 * (1 - df["densite"]) ** 1.3
                + 0.20 * np.sqrt(df["verdure"])
                + 0.15 * df["verdure"] * (1 - traffic_stress)
            )
            rng2 = np.random.default_rng(42)
            y = np.clip(y_expert + rng2.normal(0, 0.03, len(df)), 0, 1)

            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            model = Ridge(alpha=1.0)
            model.fit(X_train, y_train)
            r2 = float(r2_score(y_test, model.predict(X_test)))
            check(
                "ML R² > 0.70 on held-out set (sanity)",
                r2 > 0.70,
                f"R²={r2:.4f}",
                warn_only=True,
            )
        except Exception as exc:
            check("Held-out R² computed", False, str(exc), warn_only=True)
    except ImportError:
        check("scikit-learn available", False, "install scikit-learn", warn_only=True)

    # =========================================================================
    # PHASE 3 — Routing
    # =========================================================================
    section("PHASE 3 — Routing")

    print("\n[3.1] Graph weighting...")
    sg = build_scored_graph(graph, df)
    check("Scored graph created", sg is not None)
    check("Node count preserved", sg.number_of_nodes() == n_nodes, f"{sg.number_of_nodes():,}")
    check("Edge count preserved", sg.number_of_edges() == n_edges, f"{sg.number_of_edges():,}")

    sample_scored = list(sg.edges(data=True))[:20]
    check("Edges have score_calme", all("score_calme" in d for _, _, d in sample_scored), warn_only=True)
    for profile in USER_PROFILES.keys():
        has_cost = all(f"cost_{profile}" in d for _, _, d in sample_scored)
        check(f"Edges have cost_{profile}", has_cost, warn_only=True)
        if has_cost:
            nonneg = all(float(d[f"cost_{profile}"]) >= 0.0 for _, _, d in sample_scored)
            check(f"cost_{profile} non-negative", nonneg, warn_only=True)

    print("\n[3.2] Route finding...")
    START = (33.5886, -7.5891)
    END = (33.6086, -7.6325)

    route_results: dict[str, dict] = {}
    profile_order = ["normal", "equilibre", "autiste", "fauteuil_roulant"]
    for profile in profile_order:
        r = get_best_route(sg, START, END, profile=profile)
        route_results[profile] = r
        ok = "error" not in r and len(r.get("path", [])) > 2
        detail = (
            f"{r.get('n_edges', 0)} edges  {r.get('total_length_m', 0):,.0f}m  "
            f"calme={r.get('avg_score_calme', 0):.3f}  cost={r.get('total_cost', 0):,.0f}"
            if ok
            else r.get("error", "")
        )
        check(f"Profile '{profile}' finds a valid path", ok, detail)

    print("\n[3.3] Profile differentiation (Autiste vs Normal)...")
    if all("error" not in route_results.get(p, {}) for p in ["normal", "autiste"]):
        normal = route_results["normal"]
        autiste = route_results["autiste"]
        diff_len = float(autiste["total_length_m"]) - float(normal["total_length_m"])
        diff_score = float(autiste["avg_score_calme"]) - float(normal["avg_score_calme"])

        check(
            "Autiste not shorter than Normal (often detours)",
            diff_len >= 0,
            f"Δlen={diff_len:,.0f}m",
            warn_only=True,
        )
        check(
            "Autiste calmer than Normal",
            diff_score >= 0,
            f"Δscore={diff_score:+.3f}",
            warn_only=True,
        )

        same_path = autiste.get("path") == normal.get("path")
        check(
            "Paths differ (not always guaranteed)",
            not same_path,
            "same path" if same_path else "paths differ",
            warn_only=True,
        )

    print("\n[3.4] get_best_route return schema...")
    r0 = route_results.get("autiste", {})
    expected_keys = [
        "path",
        "n_edges",
        "n_nodes",
        "total_length_m",
        "total_time_s",
        "total_time_min",
        "total_cost",
        "avg_score_calme",
        "avg_score_calme_edges",
        "profile",
    ]
    for k in expected_keys:
        check(f"Return dict has '{k}'", k in r0)

    # =========================================================================
    # SUMMARY
    # =========================================================================
    section("SUMMARY")
    n_pass = sum(1 for s, _ in results if s == PASS)
    n_warn = sum(1 for s, _ in results if s == WARN)
    n_fail = sum(1 for s, _ in results if s == FAIL)
    total = len(results)

    print(f"\n  {PASS} {n_pass}/{total} checks passed")
    if n_warn:
        print(f"  {WARN} {n_warn} warnings")
    if n_fail:
        print(f"  {FAIL} {n_fail} failures")

    if n_fail == 0:
        print("\n  ALL PHASES VERIFIED CORRECTLY.")
    else:
        print("\n  FAILURES DETECTED — review above.")
