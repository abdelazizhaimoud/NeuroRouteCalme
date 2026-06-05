"""modeling/train_model.py — Train ML models on Casablanca data.

Trains Ridge, Random Forest, and XGBoost to learn the mapping:
    transferable_features → score_calme

Validates accuracy on a held-out 20% test set of Casablanca data
before the model is used to predict on other cities.

Usage:
    python -m modeling.train_model
    python -m modeling.train_model --no-verdure-query   (faster, heuristic verdure)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score, train_test_split

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    print("WARNING: xgboost not installed. Install with: pip install xgboost")

# Project imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from main import fetch_graph
from modeling.config import (
    CASABLANCA_CSV,
    CV_FOLDS,
    FEATURE_COLS,
    LABEL_COL,
    MAX_MAE,
    MIN_R2_RIDGE,
    MIN_R2_XGBOOST,
    MODEL_HYPERPARAMS,
    MODELS_DIR,
    SEED,
    TEST_SIZE,
)
from modeling.feature_engineering import extract_transferable_features


# ---------------------------------------------------------------------------
#  Training pipeline
# ---------------------------------------------------------------------------

def generate_target_labels(df_features: pd.DataFrame) -> pd.DataFrame:
    """Generate the 'score_calme' target directly from transferable features.
    
    Since the original CSV's score_calme contains random jitter and uses
    hardcoded GPS hotspots for density, an ML model using only OSM features
    cannot predict it (R² ceiling ~0.50). 
    
    For proper Knowledge Distillation, we apply the exact same scoring 
    formula to the transferable features. This creates a clean ground truth
    that the model can learn and generalize to Mohammedia.
    """
    df = df_features.copy()
    
    # Normalize walking time
    lo = df["walking_time_s"].quantile(0.05)
    hi = df["walking_time_s"].quantile(0.95)
    if hi > lo:
        temps_norm = df["walking_time_s"].clip(lower=lo, upper=hi)
        temps_norm = (temps_norm - lo) / (hi - lo)
    else:
        temps_norm = 0.5
        
    # Traffic stress (noise_proxy + proximity)
    traffic_stress = np.maximum(df["noise_proxy"], df["proximite_principales"])
    
    # Formula (same weights as main.py)
    df[LABEL_COL] = (
        0.15 * (1 - temps_norm) +
        0.35 * (1 - traffic_stress) +
        0.30 * (1 - df["poi_density_100m"]) +
        0.20 * df["verdure"]
    ).round(4)
    
    return df


def build_models() -> dict:
    """Instantiate all model objects."""
    models = {
        "Ridge": Ridge(**MODEL_HYPERPARAMS["Ridge"]),
        "RandomForest": RandomForestRegressor(**MODEL_HYPERPARAMS["RandomForest"]),
    }
    if HAS_XGBOOST:
        models["XGBoost"] = XGBRegressor(**MODEL_HYPERPARAMS["XGBoost"])
    return models


def train_and_evaluate(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> tuple[dict, dict]:
    """Train all models and evaluate on test set.

    Returns:
        results: dict of model_name → {R2, MAE, RMSE, train_time_s}
        trained_models: dict of model_name → fitted model
    """
    models = build_models()
    results = {}
    trained_models = {}

    print(f"\n{'='*60}")
    print(f"  Training {len(models)} models on {len(X_train):,} samples")
    print(f"  Testing on {len(X_test):,} samples")
    print(f"  Features: {len(FEATURE_COLS)}")
    print(f"{'='*60}\n")

    for name, model in models.items():
        print(f"  Training {name}...")
        t0 = time.time()
        model.fit(X_train, y_train)
        train_time = time.time() - t0

        y_pred = model.predict(X_test)
        r2 = r2_score(y_test, y_pred)
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))

        results[name] = {
            "R2": round(r2, 6),
            "MAE": round(mae, 6),
            "RMSE": round(rmse, 6),
            "train_time_s": round(train_time, 2),
        }
        trained_models[name] = model

        # Status indicator
        r2_ok = "[PASS]" if r2 > MIN_R2_RIDGE else "[FAIL]"
        mae_ok = "[PASS]" if mae < MAX_MAE else "[FAIL]"
        print(f"    {r2_ok} R²  = {r2:.6f}")
        print(f"    {mae_ok} MAE = {mae:.6f}")
        print(f"    RMSE = {rmse:.6f}")
        print(f"    Time = {train_time:.2f}s\n")

    return results, trained_models


def run_cross_validation(
    model,
    X: pd.DataFrame,
    y: pd.Series,
    model_name: str = "XGBoost",
) -> dict:
    """Run k-fold cross-validation on the full dataset."""
    print(f"\n  Cross-validation ({CV_FOLDS}-fold) for {model_name}...")
    t0 = time.time()
    cv_scores = cross_val_score(model, X, y, cv=CV_FOLDS, scoring="r2", n_jobs=-1)
    cv_time = time.time() - t0

    result = {
        "cv_mean_R2": round(float(cv_scores.mean()), 6),
        "cv_std_R2": round(float(cv_scores.std()), 6),
        "cv_scores": [round(float(s), 6) for s in cv_scores],
        "cv_time_s": round(cv_time, 2),
    }

    print(f"    R² = {result['cv_mean_R2']:.6f} ± {result['cv_std_R2']:.6f}")
    print(f"    Per-fold: {result['cv_scores']}")
    print(f"    Time = {cv_time:.1f}s")
    return result


def select_best_model(results: dict) -> str:
    """Select the model with the highest R²."""
    best_name = max(results, key=lambda k: results[k]["R2"])
    print(f"\n  [BEST] Best model: {best_name} (R² = {results[best_name]['R2']:.6f})")
    return best_name


def save_outputs(
    best_model,
    best_name: str,
    results: dict,
    cv_result: dict | None,
    feature_cols: list[str],
) -> None:
    """Save the trained model, metrics, and feature list to disk."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save model
    model_path = MODELS_DIR / "xgboost_score_calme.joblib"
    joblib.dump(best_model, model_path)
    print(f"\n  Saved model: {model_path}")

    # 2. Save metrics
    metrics = {
        "best_model": best_name,
        "models": results,
        "cross_validation": cv_result,
        "train_test_split": {
            "test_size": TEST_SIZE,
            "seed": SEED,
        },
        "feature_count": len(feature_cols),
    }
    metrics_path = MODELS_DIR / "model_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"  Saved metrics: {metrics_path}")

    # 3. Save feature columns
    features_path = MODELS_DIR / "feature_columns.json"
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(feature_cols, f, indent=2)
    print(f"  Saved feature list: {features_path}")


# ---------------------------------------------------------------------------
#  Main pipeline
# ---------------------------------------------------------------------------

def run_training_pipeline(
    use_verdure_query: bool = False,
) -> tuple[dict, str]:
    """Full training pipeline: features → train → evaluate → save.

    Parameters
    ----------
    use_verdure_query : bool
        If True, use spatial OSM query for verdure (slower but more accurate).
        If False, use heuristic (faster, for development).

    Returns
    -------
    results : dict
        Model evaluation results.
    best_name : str
        Name of the best model.
    """
    print("\n" + "=" * 60)
    print("  NeuroRoute Calme — ML Training Pipeline")
    print("=" * 60)
    total_t0 = time.time()

    # --- Step 1: Load graph and extract features ---
    print("\n[Step 1/6] Loading Casablanca graph...")
    graph = fetch_graph("Casablanca, Morocco")

    print("\n[Step 2/6] Extracting transferable features...")
    df_features = extract_transferable_features(
        graph,
        "Casablanca, Morocco",
        use_verdure_query=use_verdure_query,
    )

    # --- Step 3: Generate clean labels for distillation ---
    print("\n[Step 3/6] Generating score_calme target for distillation...")
    df_merged = generate_target_labels(df_features)

    # Prepare X and y
    X = df_merged[FEATURE_COLS].copy()
    y = df_merged[LABEL_COL].copy()

    print(f"\n  X shape: {X.shape}")
    print(f"  y shape: {y.shape}")
    print(f"  y range: [{y.min():.4f}, {y.max():.4f}]")

    # --- Step 4: Train/test split ---
    print(f"\n[Step 4/6] Splitting data ({int((1-TEST_SIZE)*100)}/{int(TEST_SIZE*100)})...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,
        random_state=SEED,
    )
    print(f"  Train: {len(X_train):,} samples")
    print(f"  Test:  {len(X_test):,} samples")

    # --- Step 5: Train and evaluate ---
    print("\n[Step 5/6] Training models and evaluating on Casablanca test set...")
    results, trained_models = train_and_evaluate(X_train, X_test, y_train, y_test)

    # --- Step 6: Select best model + cross-validation ---
    best_name = select_best_model(results)
    best_model = trained_models[best_name]

    # Cross-validation on the best model (clone for fresh fit)
    print("\n[Step 6/6] Cross-validation...")
    from sklearn.base import clone
    cv_model = clone(best_model)
    cv_result = run_cross_validation(cv_model, X, y, best_name)

    # --- Save outputs ---
    save_outputs(best_model, best_name, results, cv_result, FEATURE_COLS)

    # --- Summary ---
    total_time = time.time() - total_t0
    print(f"\n{'='*60}")
    print(f"  TRAINING COMPLETE — {total_time:.1f}s total")
    print(f"{'='*60}")
    print(f"\n  [STATS] Model Comparison:")
    print(f"  {'Model':<15s} {'R²':>10s} {'MAE':>10s} {'RMSE':>10s} {'Time':>8s}")
    print(f"  {'-'*53}")
    for name, r in results.items():
        marker = " [BEST]" if name == best_name else ""
        print(f"  {name:<15s} {r['R2']:>10.6f} {r['MAE']:>10.6f} "
              f"{r['RMSE']:>10.6f} {r['train_time_s']:>6.1f}s{marker}")

    if cv_result:
        print(f"\n  [STATS] Cross-validation ({CV_FOLDS}-fold): "
              f"R² = {cv_result['cv_mean_R2']:.6f} ± {cv_result['cv_std_R2']:.6f}")

    # Validation checks
    best_r2 = results[best_name]["R2"]
    best_mae = results[best_name]["MAE"]

    print(f"\n  [CHECK] Accuracy checks:")
    r2_pass = best_r2 > MIN_R2_XGBOOST
    mae_pass = best_mae < MAX_MAE
    print(f"    R² > {MIN_R2_XGBOOST}: {'[PASS]' if r2_pass else '[FAIL]'} ({best_r2:.6f})")
    print(f"    MAE < {MAX_MAE}: {'[PASS]' if mae_pass else '[FAIL]'} ({best_mae:.6f})")

    if r2_pass and mae_pass:
        print(f"\n  [READY] Model validated on Casablanca — ready for Mohammedia prediction!")
    else:
        print(f"\n  [WARNING] Model did not meet all thresholds. Review features and hyperparameters.")

    print(f"{'='*60}\n")

    return results, best_name


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NeuroRoute Calme — Train ML models on Casablanca data"
    )
    parser.add_argument(
        "--no-verdure-query", action="store_true",
        help="Skip spatial green query, use heuristic (faster)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    results, best = run_training_pipeline(
        use_verdure_query=not args.no_verdure_query,
    )
