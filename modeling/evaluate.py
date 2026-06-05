"""modeling/evaluate.py — Generate evaluation metrics and visualizations.

Reads the trained model and metrics from outputs/models/ and generates:
  1. Feature importance plot
  2. SHAP summary plot (for interpretability)
  3. Residuals plot (True vs Predicted)
  4. Per-road-type performance metrics

Usage:
    python -m modeling.evaluate
"""

import json
from pathlib import Path
import sys

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import mean_absolute_error, r2_score

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False
    print("WARNING: shap not installed. Skipping SHAP plots.")

# Project imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modeling.config import (
    CASABLANCA_CSV,
    FEATURE_COLS,
    LABEL_COL,
    MODELS_DIR,
    SEED,
    TEST_SIZE,
)
from modeling.feature_engineering import extract_transferable_features
from modeling.train_model import generate_target_labels
from main import fetch_graph


def load_model_data() -> tuple:
    """Load the trained model and metrics."""
    metrics_path = MODELS_DIR / "model_metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError("model_metrics.json not found. Run train_model.py first.")

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    model_path = MODELS_DIR / "xgboost_score_calme.joblib"
    model = joblib.load(model_path)

    return model, metrics


def get_test_data() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Reconstruct the exact test set used during training."""
    from sklearn.model_selection import train_test_split
    
    print("Loading graph and recomputing features to build test set...")
    graph = fetch_graph("Casablanca, Morocco")
    df_features = extract_transferable_features(graph, "Casablanca, Morocco", use_verdure_query=False)
    
    # Base columns for analysis (we need type_route)
    df_base = extract_transferable_features(graph, "Casablanca, Morocco", use_verdure_query=False, include_base_columns=True)
    
    df_merged = generate_target_labels(df_features)
    
    # We must split identically to get the test set
    idx = df_merged.index
    _, test_idx = train_test_split(idx, test_size=TEST_SIZE, random_state=SEED)
    
    X_test = df_merged.loc[test_idx, FEATURE_COLS]
    y_test = df_merged.loc[test_idx, LABEL_COL]
    
    # Keep base info for road-type analysis
    df_test_base = df_base.loc[test_idx]
    
    return X_test, y_test, df_test_base


def plot_feature_importance(model, feature_cols: list[str]) -> None:
    """Plot standard XGBoost/RF feature importance."""
    if not hasattr(model, "feature_importances_"):
        print("  Model does not support feature_importances_.")
        return

    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]

    plt.figure(figsize=(10, 6))
    sns.barplot(
        x=importances[indices],
        y=[feature_cols[i] for i in indices],
        palette="viridis",
        hue=[feature_cols[i] for i in indices],
        legend=False,
    )
    plt.title("Feature Importance (XGBoost)")
    plt.xlabel("Importance (Gini)")
    plt.ylabel("Feature")
    plt.tight_layout()
    
    out_path = MODELS_DIR / "feature_importance.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"  Saved: {out_path.name}")


def plot_shap_values(model, X_test: pd.DataFrame) -> None:
    """Plot SHAP summary plot for interpretability."""
    if not HAS_SHAP:
        return

    # Subsample test set for SHAP speed (e.g. 5000 points)
    X_sample = X_test.sample(n=min(5000, len(X_test)), random_state=SEED)
    
    print("  Computing SHAP values...")
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    plt.figure(figsize=(10, 6))
    shap.summary_plot(shap_values, X_sample, show=False)
    
    out_path = MODELS_DIR / "shap_summary.png"
    plt.savefig(out_path, bbox_inches="tight", dpi=300)
    plt.close()
    print(f"  Saved: {out_path.name}")


def plot_residuals(y_test: pd.Series, y_pred: np.ndarray) -> None:
    """Plot True vs Predicted scores and residuals histogram."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Scatter: True vs Pred
    sns.scatterplot(x=y_test, y=y_pred, alpha=0.1, ax=axes[0], color="#2ecc71")
    axes[0].plot([0, 1], [0, 1], "r--")
    axes[0].set_title("Predicted vs True Score_Calme")
    axes[0].set_xlabel("True Score")
    axes[0].set_ylabel("Predicted Score")

    # Histogram of residuals
    residuals = y_test - y_pred
    sns.histplot(residuals, bins=50, kde=True, ax=axes[1], color="#e74c3c")
    axes[1].set_title("Residuals Distribution")
    axes[1].set_xlabel("Error (True - Pred)")
    axes[1].set_ylabel("Count")

    plt.tight_layout()
    out_path = MODELS_DIR / "residuals.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"  Saved: {out_path.name}")


def evaluate_per_road_type(y_test: pd.Series, y_pred: np.ndarray, df_base: pd.DataFrame) -> None:
    """Evaluate metrics grouped by OSM highway type."""
    df_eval = pd.DataFrame({
        "True": y_test,
        "Pred": y_pred,
        "Error": np.abs(y_test - y_pred),
        "type_route": df_base["type_route"]
    })

    # Keep top 10 most frequent road types
    top_types = df_eval["type_route"].value_counts().nlargest(10).index
    df_eval_top = df_eval[df_eval["type_route"].isin(top_types)]

    stats = []
    for rt in top_types:
        subset = df_eval[df_eval["type_route"] == rt]
        stats.append({
            "type_route": rt,
            "count": len(subset),
            "R2": r2_score(subset["True"], subset["Pred"]),
            "MAE": subset["Error"].mean(),
            "mean_score": subset["True"].mean()
        })
    
    stats_df = pd.DataFrame(stats)
    
    # Save as CSV
    csv_path = MODELS_DIR / "per_road_type_performance.csv"
    stats_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path.name}")

    # Plot
    plt.figure(figsize=(12, 6))
    sns.barplot(data=stats_df, x="MAE", y="type_route", palette="magma", hue="type_route", legend=False)
    plt.title("Mean Absolute Error (MAE) by Road Type")
    plt.xlabel("MAE")
    plt.ylabel("Road Type")
    plt.tight_layout()
    
    png_path = MODELS_DIR / "per_road_type_performance.png"
    plt.savefig(png_path, dpi=300)
    plt.close()
    print(f"  Saved: {png_path.name}")


def main():
    print("\n" + "=" * 60)
    print("  NeuroRoute Calme — Model Evaluation")
    print("=" * 60)

    model, metrics = load_model_data()
    best_name = metrics["best_model"]
    print(f"  Loaded best model: {best_name}")

    X_test, y_test, df_test_base = get_test_data()
    y_pred = model.predict(X_test)

    print("\n[1/4] Generating Feature Importance plot...")
    plot_feature_importance(model, FEATURE_COLS)

    print("[2/4] Generating SHAP summary plot...")
    plot_shap_values(model, X_test)

    print("[3/4] Generating Residuals plot...")
    plot_residuals(y_test, y_pred)

    print("[4/4] Generating Per-Road-Type evaluation...")
    evaluate_per_road_type(y_test, y_pred, df_test_base)

    print(f"\n{'='*60}")
    print("  EVALUATION COMPLETE — All plots saved to outputs/models/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
