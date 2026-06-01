"""modeling — ML pipeline for NeuroRoute Calme.

This package provides:
- feature_engineering: Extract transferable features from any OSMnx graph
- train_model: Train Ridge, Random Forest, and XGBoost on Casablanca data
- predict_city: Predict calm scores on a new city (e.g. Mohammedia)
- evaluate: Evaluation metrics, SHAP, and visualization
- visualize_comparison: Cross-city comparison plots
- config: Centralized constants, mappings, and hyperparameters
"""

from modeling.config import FEATURE_COLS, LABEL_COL, SEED
