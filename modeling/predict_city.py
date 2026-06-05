"""modeling/predict_city.py — Apply trained ML model to a new city (e.g. Mohammedia).

Pipeline:
  1. Fetch OSM graph for the target city
  2. Extract transferable ML features
  3. Load the trained XGBoost model (trained on Casablanca)
  4. Predict `score_calme` for every edge
  5. Run sanity checks
  6. Compute profile costs (normal, autiste, fauteuil_roulant, equilibre)
  7. Export as CSV and Parquet for the server/UI to use

Usage:
    python -m modeling.predict_city --place-name "Mohammedia, Morocco"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import pandas as pd
import numpy as np

# Project imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from main import (
    build_scored_graph,
    compute_profile_costs,
    fetch_graph,
    slugify,
)
from modeling.config import (
    FEATURE_COLS,
    MODELS_DIR,
    OUTPUTS_DIR,
)
from modeling.feature_engineering import extract_transferable_features


def load_model() -> tuple:
    """Load the trained model and feature list."""
    model_path = MODELS_DIR / "xgboost_score_calme.joblib"
    features_path = MODELS_DIR / "feature_columns.json"

    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found: {model_path}. Run train_model.py first."
        )

    model = joblib.load(model_path)
    with open(features_path, "r", encoding="utf-8") as f:
        feature_cols = json.load(f)

    return model, feature_cols


def run_sanity_checks(df: pd.DataFrame, score_col: str) -> dict:
    """Validate predictions against common sense rules."""
    scores = df[score_col]
    checks = {}

    print("\n  [CHECK] Running sanity checks on predictions:")

    # 1. Bounds check
    in_bounds = bool((scores.min() >= 0.0) and (scores.max() <= 1.0))
    checks["bounds_ok"] = in_bounds
    print(f"    Scores in [0,1]: {'[PASS]' if in_bounds else '[FAIL]'} (min={scores.min():.3f}, max={scores.max():.3f})")

    # 2. Footway check (should be calm)
    if "type_route" in df.columns:
        footways = df[df["type_route"].isin(["footway", "pedestrian", "path"])]
        if not footways.empty:
            mean_footway = footways[score_col].mean()
            footway_ok = bool(mean_footway > 0.55)
            checks["footway_ok"] = footway_ok
            print(f"    Footway mean score > 0.55: {'[PASS]' if footway_ok else '[FAIL]'} ({mean_footway:.3f})")

        # 3. Trunk/Motorway check (should be noisy)
        highways = df[df["type_route"].isin(["motorway", "trunk", "primary"])]
        if not highways.empty:
            mean_highway = highways[score_col].mean()
            highway_ok = bool(mean_highway < 0.45)
            checks["highway_ok"] = highway_ok
            print(f"    Highway mean score < 0.45: {'[PASS]' if highway_ok else '[FAIL]'} ({mean_highway:.3f})")

    return checks


def predict_city(
    place_name: str,
    use_verdure_query: bool = True,
) -> pd.DataFrame:
    """Full prediction pipeline for a given city."""
    print("\n" + "=" * 60)
    print(f"  NeuroRoute Calme — ML Prediction: {place_name}")
    print("=" * 60)
    t0 = time.time()

    # --- Step 1: Load Model ---
    model, expected_features = load_model()
    print(f"  Loaded model: {type(model).__name__}")
    print(f"  Expected features: {len(expected_features)}")

    # --- Step 2: Fetch Graph ---
    print("\n[Step 1/5] Fetching OSM graph...")
    graph = fetch_graph(place_name)

    # --- Step 3: Extract Features ---
    print("\n[Step 2/5] Extracting transferable features...")
    df_features = extract_transferable_features(
        graph,
        place_name,
        use_verdure_query=use_verdure_query,
        include_base_columns=True,  # Keep u, v, type_route for routing
    )

    # Ensure columns match exactly what the model expects
    missing_cols = [c for c in expected_features if c not in df_features.columns]
    if missing_cols:
        raise ValueError(f"Missing required features: {missing_cols}")

    X = df_features[expected_features]

    # --- Step 4: Predict ---
    print("\n[Step 3/5] Predicting score_calme...")
    df_features["score_calme"] = model.predict(X).clip(0.0, 1.0).round(4)
    # ML model acts as the definitive score here (no jitter needed)
    df_features["score_ml"] = df_features["score_calme"]
    df_features["temps"] = df_features["walking_time_s"]
    df_features["bruit"] = df_features["noise_proxy"]
    df_features["densite"] = df_features["poi_density_100m"]

    # --- Step 5: Sanity Checks ---
    checks = run_sanity_checks(df_features, "score_calme")

    # --- Step 6: Compute Costs ---
    print("\n[Step 4/5] Computing profile costs...")
    df_scored = compute_profile_costs(df_features)

    # --- Step 7: Export ---
    print("\n[Step 5/5] Exporting outputs...")
    city_slug = slugify(place_name.split(",")[0])
    city_dir = OUTPUTS_DIR / city_slug
    city_dir.mkdir(parents=True, exist_ok=True)

    csv_path = city_dir / f"routes_{city_slug}.csv"
    df_scored.to_csv(csv_path, index=False)
    print(f"  Saved CSV: {csv_path}")
    
    # Save sanity checks
    checks_path = city_dir / "sanity_checks.json"
    with open(checks_path, "w", encoding="utf-8") as f:
        json.dump(checks, f, indent=2)

    total_time = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  PREDICTION COMPLETE — {total_time:.1f}s total")
    print(f"{'='*60}\n")

    return df_scored


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict calm scores for a city")
    parser.add_argument(
        "--place-name",
        type=str,
        default="Mohammedia, Morocco",
        help="Target city place name (e.g. 'Mohammedia, Morocco')",
    )
    parser.add_argument(
        "--no-verdure-query", action="store_true",
        help="Skip spatial green query (faster, less accurate)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    df_scored = predict_city(
        place_name=args.place_name,
        use_verdure_query=not args.no_verdure_query,
    )
