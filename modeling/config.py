"""modeling/config.py — Centralized configuration for the ML pipeline.

All constants, mappings, hyperparameters, and paths used by the modeling
module are defined here to keep the training/prediction scripts clean.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
MODELS_DIR = OUTPUTS_DIR / "models"
CACHE_DIR = PROJECT_ROOT / "cache"

CASABLANCA_CSV = OUTPUTS_DIR / "routes_casablanca.csv"

# ---------------------------------------------------------------------------
#  Random seed (reproducibility)
# ---------------------------------------------------------------------------

SEED = 42

# ---------------------------------------------------------------------------
#  Road hierarchy — ordinal encoding for highway types
#  Lower = quieter/pedestrian, Higher = noisier/heavier traffic
# ---------------------------------------------------------------------------

ROAD_HIERARCHY: dict[str, int] = {
    "footway": 1,
    "pedestrian": 1,
    "path": 1,
    "corridor": 1,
    "steps": 2,
    "cycleway": 2,
    "living_street": 3,
    "residential": 4,
    "service": 4,
    "track": 4,
    "unclassified": 5,
    "tertiary": 6,
    "tertiary_link": 6,
    "secondary": 7,
    "secondary_link": 7,
    "primary": 8,
    "primary_link": 8,
    "trunk": 9,
    "trunk_link": 9,
    "motorway": 10,
    "motorway_link": 10,
}

ROAD_HIERARCHY_DEFAULT = 5  # for unknown highway types

# ---------------------------------------------------------------------------
#  Surface quality — ordinal encoding
# ---------------------------------------------------------------------------

SURFACE_QUALITY: dict[str, int] = {
    "asphalt": 5,
    "paved": 5,
    "concrete": 4,
    "concrete:plates": 4,
    "paving_stones": 4,
    "sett": 3,
    "cobblestone": 3,
    "compacted": 3,
    "fine_gravel": 2,
    "gravel": 2,
    "pebblestone": 2,
    "dirt": 1,
    "earth": 1,
    "grass": 1,
    "ground": 1,
    "mud": 1,
    "sand": 1,
    "unpaved": 1,
}

SURFACE_QUALITY_DEFAULT = 3  # assume moderate when unknown

# ---------------------------------------------------------------------------
#  Default maxspeed by highway type (km/h) — used when tag is missing
# ---------------------------------------------------------------------------

DEFAULT_MAXSPEED: dict[str, float] = {
    "footway": 5.0,
    "pedestrian": 5.0,
    "path": 5.0,
    "steps": 5.0,
    "corridor": 5.0,
    "cycleway": 20.0,
    "living_street": 20.0,
    "residential": 40.0,
    "service": 30.0,
    "track": 30.0,
    "unclassified": 40.0,
    "tertiary": 50.0,
    "tertiary_link": 40.0,
    "secondary": 60.0,
    "secondary_link": 50.0,
    "primary": 60.0,
    "primary_link": 50.0,
    "trunk": 80.0,
    "trunk_link": 60.0,
    "motorway": 120.0,
    "motorway_link": 80.0,
}

DEFAULT_MAXSPEED_FALLBACK = 40.0  # global fallback

# ---------------------------------------------------------------------------
#  POI density — tags and buffer for the transferable density feature
# ---------------------------------------------------------------------------

POI_TAGS: dict[str, bool] = {
    "amenity": True,
    "shop": True,
    "tourism": True,
}

POI_BUFFER_METERS = [100, 200]  # radii for density computation

# ---------------------------------------------------------------------------
#  Walking speed (same as main.py)
# ---------------------------------------------------------------------------

WALKING_SPEED_MS = 1.39  # 5 km/h ≈ 1.39 m/s

# ---------------------------------------------------------------------------
#  Feature columns — the transferable features used for training & prediction
# ---------------------------------------------------------------------------

FEATURE_COLS: list[str] = [
    "log_length",               # log(1 + longueur)
    "road_hierarchy",           # ordinal encoding of highway type (1-10)
    "noise_proxy",              # road_hierarchy / 10  (proxy for noise)
    "verdure",                  # greenery score from OSM spatial query
    "proximite_principales",    # proximity to major roads
    "poi_density_100m",         # POI count within 100m (replaces densite)
    "maxspeed_kph",             # speed limit (0 if unknown)
    "lanes_count",              # number of lanes (0 if unknown)
    "has_sidewalk",             # boolean: sidewalk present
    "is_lit",                   # boolean: street lighting present
    "surface_quality",          # ordinal surface encoding (1-5)
    "walking_time_s",           # length / 1.39
    "connectivity",             # degree of the source node
]

# Label column
LABEL_COL = "score_calme"

# ---------------------------------------------------------------------------
#  Model hyperparameters
# ---------------------------------------------------------------------------

MODEL_HYPERPARAMS = {
    "Ridge": {
        "alpha": 1.0,
    },
    "RandomForest": {
        "n_estimators": 200,
        "max_depth": 12,
        "min_samples_leaf": 10,
        "random_state": SEED,
        "n_jobs": -1,
    },
    "XGBoost": {
        "n_estimators": 300,
        "max_depth": 6,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "random_state": SEED,
        "n_jobs": -1,
    },
}

# ---------------------------------------------------------------------------
#  Evaluation thresholds
# ---------------------------------------------------------------------------

MIN_R2_RIDGE = 0.90
MIN_R2_XGBOOST = 0.94
MAX_MAE = 0.05

TEST_SIZE = 0.20  # 80/20 train/test split
CV_FOLDS = 5

# ---------------------------------------------------------------------------
#  City configurations
# ---------------------------------------------------------------------------

CITIES = {
    "casablanca": {
        "place_name": "Casablanca, Morocco",
        "center": (33.5731, -7.5898),
        "zoom": 12,
        "scoring_method": "pipeline",   # uses the full simulation pipeline
    },
    "mohammedia": {
        "place_name": "Mohammedia, Morocco",
        "center": (33.6866, -7.3863),
        "zoom": 13,
        "scoring_method": "ml",          # uses the trained ML model
    },
}
