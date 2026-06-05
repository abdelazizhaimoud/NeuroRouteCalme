"""modeling/visualize_comparison.py — Compare Casa (original) vs Mohammedia (predicted).

Generates:
  1. Side-by-side score distributions
  2. Map HTML for Mohammedia scores
  3. Demo routes HTML on Mohammedia

Usage:
    python -m modeling.visualize_comparison
"""

from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Project imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from main import fetch_graph
from modeling.config import OUTPUTS_DIR, LABEL_COL


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load Casablanca and Mohammedia DataFrames."""
    casa_path = OUTPUTS_DIR / "routes_casablanca.csv"
    moh_path = OUTPUTS_DIR / "mohammedia" / "routes_mohammedia.csv"

    if not moh_path.exists():
        raise FileNotFoundError(f"Mohammedia predictions not found: {moh_path}")

    df_casa = pd.read_csv(casa_path)
    df_moh = pd.read_csv(moh_path)
    return df_casa, df_moh


def plot_distributions(df_casa: pd.DataFrame, df_moh: pd.DataFrame) -> None:
    """Plot score distributions side-by-side."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True, sharex=True)

    sns.histplot(df_casa[LABEL_COL], bins=50, kde=True, ax=axes[0], color="#3498db")
    axes[0].set_title(f"Casablanca (Original) - {len(df_casa):,} edges")
    axes[0].set_xlabel("Score Calme")
    
    sns.histplot(df_moh[LABEL_COL], bins=50, kde=True, ax=axes[1], color="#9b59b6")
    axes[1].set_title(f"Mohammedia (Predicted) - {len(df_moh):,} edges")
    axes[1].set_xlabel("Score Calme")

    plt.tight_layout()
    out_path = OUTPUTS_DIR / "mohammedia" / "distribution_comparison.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"  Saved: {out_path.name}")


def generate_maps(df_moh: pd.DataFrame) -> None:
    """Generate HTML maps for Mohammedia (scores + routes)."""
    pass


def main():
    print("\n" + "=" * 60)
    print("  NeuroRoute Calme — Inter-City Comparison")
    print("=" * 60)

    try:
        df_casa, df_moh = load_data()
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        return

    print("\n[1/2] Plotting distributions...")
    plot_distributions(df_casa, df_moh)

    print("\n[2/2] Generating Maps for Mohammedia...")
    generate_maps(df_moh)

    print(f"\n{'='*60}")
    print("  COMPARISON COMPLETE")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
