# NeuroRoute Calme — Understanding the Process

> **One-line pitch:** We build a system that finds the *calmest* walking route in Casablanca, not the shortest one.

---

## STEP 1 — Get the city data

**What:** Download all walkable streets of Casablanca as a mathematical graph.

**Code:** `main.py` → function `fetch_graph()` — line ~155

```python
graph = ox.graph_from_place("Casablanca, Morocco", network_type="walk")
```

**Result:**
- 54,813 nodes (intersections)
- 164,818 edges (street segments)
- Cached locally so it never re-downloads

---

## STEP 2 — Extract features per street segment

**What:** For each of the 164,818 segments, extract 4 measurable characteristics.

**Code:** `main.py` → function `extract_route_features()` — line ~195

| Feature | How we get it |
|---------|--------------|
| `longueur` | Already in OSM data (meters) |
| `type_route` | `highway` tag from OSM (`footway`, `residential`, `primary`...) |
| `verdure` | Spatial query: distance to nearest park/tree in OSM |
| `proximite_principales` | Distance to nearest major road (primary, trunk...) |

**Result:** A pandas DataFrame — one row per street, 4 columns.

---

## STEP 3 — Simulate missing data

**What:** We don't have real noise sensors or crowd counters, so we simulate them intelligently.

**Code:** `main.py` → constants `NOISE_BY_HIGHWAY`, `DENSITY_BANDS` — lines ~37–70

| Simulated feature | Logic |
|------------------|-------|
| `bruit` (noise) | Lookup by road type: `footway=0.10`, `primary=0.85`, `trunk=1.00` |
| `densite` (crowd) | Distance from city centre: inside 1km=0.85, beyond 10km=0.10 |

Small random jitter (±0.05) added so values aren't perfectly identical.

**Result:** Dataset now has 6 columns — ready for scoring.

---

## STEP 4A — Fixed-weight scoring (Obligatoire)

**What:** Combine the 4 features into **one calm score** between 0 and 1.

**Code:** `main.py` → function `compute_score_fixed()` — line ~380

```
score_calme = 0.15·(1-temps) + 0.35·(1-bruit) + 0.30·(1-densite) + 0.20·verdure
```

Why inverted? Because it's a *calmness* score — less noise = more calm, so we flip:
- `(1 - bruit)` = quieter is better
- `(1 - densite)` = less crowded is better
- `verdure` stays positive (greener is better)

**Why these weights?**

| Weight | Value | Reason |
|--------|-------|--------|
| α (temps) | 0.15 | Efficiency matters but isn't priority |
| β (bruit) | **0.35** | Noise is #1 factor for neurodivergent users |
| γ (densite) | 0.30 | Avoiding crowds is almost as important |
| δ (verdure) | 0.20 | Greenery is a bonus |

**Result:** Every street has a `score_calme` from 0.174 (stressful) to 0.883 (very calm).

---

## STEP 4B — ML scoring (Version avancée)

**What:** Instead of fixing the weights manually, use machine learning to learn them.

**Code:** `main.py` → function `compute_score_ml()` — line ~401

**How:**
1. Generate synthetic "expert annotations" using a non-linear heuristic
2. Train a **Ridge regression** (scikit-learn) on those labels
3. The model learns the weights automatically

**Result:** R² = 0.916 — the ML model agrees 91.6% with the expert heuristic.

Learned weights vs fixed:

| Feature | Fixed | ML-learned |
|---------|-------|-----------|
| bruit | 0.35 | 0.37 |
| densite | 0.30 | 0.27 |
| verdure | 0.20 | 0.36 |
| temps | 0.15 | 0.10 |

ML confirms bruit is the most important factor.

---

## STEP 5 — Build the scored graph for routing

**What:** Assign the calm score as a cost on every edge of the networkx graph.

**Code:** `main.py` → function `build_scored_graph()` — line ~477

```python
cost_calme = 1 - score_calme   # invert: algorithm MINIMIZES cost
```

The routing algorithm (Dijkstra) will minimize cost → it will find the path with the lowest total `cost_calme` → the calmest route.

---

## STEP 6 — Find the best route (Dijkstra)

**What:** Use Dijkstra to find the path that minimizes a blend of distance and calm cost.

**Code:** `main.py` → function `get_best_route()` — line ~510

```python
edge_cost = λ · cost_calme + (1 - λ) · distance_norm
```

Three profiles control λ:

| Profile | λ | Priority |
|---------|---|----------|
| `rapide` | 0.15 | 85% distance, 15% calm |
| `equilibre` | 0.50 | 50% / 50% |
| `calme` | 0.85 | 85% calm, 15% distance |

**Input:** `get_best_route(start=(lat,lon), end=(lat,lon), profile="calme")`

**Output:** `{ path, total_length_m, total_time_min, avg_score_calme, ... }`

---

## STEP 7 — Visualization

**What:** Generate interactive HTML maps to verify results visually.

**Code:** `visualize.py`, `multi_route_map.py`

| Map | File | Shows |
|-----|------|-------|
| Score heatmap | `outputs/map_scores.html` | Every street colored green→red by score |
| Route comparison | `outputs/map_routes.html` | Rapide vs Calme route for one trip |
| 6 test routes | `outputs/map_multi_routes.html` | 6 different O/D pairs, all 3 profiles |

---

## The full pipeline in one diagram

```
OpenStreetMap API
      |
      v
[STEP 1] fetch_graph()          →  54,813 nodes, 164,818 edges
      |
      v
[STEP 2] extract_route_features() →  longueur, type, verdure, proximite
      |
      v
[STEP 3] simulate bruit + densite →  dataset enrichi (6 features)
      |
      v
[STEP 4] compute_score_fixed()   →  score_calme ∈ [0, 1]  (1 number)
         compute_score_ml()       →  score_ml    ∈ [0, 1]  (ML version)
      |
      v
[STEP 5] build_scored_graph()    →  graph with cost_calme on edges
      |
      v
[STEP 6] get_best_route()        →  optimal path for chosen profile
      |
      v
[STEP 7] visualize.py            →  interactive Folium map (HTML)
```

---

## Key numbers to remember

| What | Number |
|------|--------|
| Nodes (intersections) | 54,813 |
| Edges (street segments) | 164,818 |
| Road types detected | 19 |
| footway noise score | 0.10 (very quiet) |
| primary road noise score | 0.85 (loud) |
| footway calm score | 0.737 |
| motorway calm score | 0.378 |
| ML R² | 0.916 |
| Verification checks passed | 61 / 62 |
