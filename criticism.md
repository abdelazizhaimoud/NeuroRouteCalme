# Criticism — Current Edge Scoring & Routing Pipeline (NeuroRoute Calme)

Date: 2026-05-11

This document is a **deep critique** of the current approach used to score edges (street segments) and to route with profile-specific weights.

It is grounded in the **actual implementation** in `main.py` (plus the demo/visualization scripts) and focuses on:
- What the pipeline does **from data → scoring → navigation**
- What is **wrong / misleading / brittle**
- How to **improve scoring per profile** (normal / autiste / fauteuil_roulant / equilibre)
- **Conceptual test cases** where the current approach gives bad results

---

## 0) Executive summary (what’s most important)

### The 5 biggest issues
1. **Routing cost is not additive-safe** because it uses `temps_norm = minmax(time)` per edge, then sums it along the path. This introduces a strong **edge-count bias** and can select routes that are objectively longer.
2. **Several features are computed but unused** in scoring/routing (notably `proximite_principales`). That’s wasted compute and missed signal.
3. **Synthetic “noise” and “density” drive decisions** (and density uses Casablanca hardcoded hotspots). The system can look “smart” while being ungrounded and not transferable.
4. **Silent fallbacks hide misconfiguration** (default `0.5` costs, unknown profile fallback to `cost_calme`). This makes tests/demos look OK while routing is actually wrong.
5. **Fauteuil roulant profile is conceptually aligned**: the current features/weights (density, stairs penalty, greenery) accurately represent wheelchair accessibility needs.

### What is still good
- The pipeline is easy to run and explain.
- The graph/edge extraction and the basic “score in [0,1]” idea is reasonable.
- The code already has the right high-level structure to improve: (features) → (scores/costs) → (routing).

---

## 1) Pipeline walkthrough (as implemented today)

This section describes what the code does **step-by-step** from OpenStreetMap to route output.

### Step 1 — Download/load the walking graph
**Where:** `main.py: fetch_graph(place_name, cache_dir)`

- Uses OSMnx `graph_from_place(place_name, network_type="walk", retain_all=True, simplify=True)`.
- Enables OSMnx cache in `cache/osmnx_http/`.

**Output:** a NetworkX `MultiDiGraph` with:
- nodes = intersections (with `x,y` coords)
- edges = street segments (with `length`, `highway`, and other tags depending on OSMnx settings)

**Hidden assumption:** the graph contains the edge tags you want. In practice, many scoring-relevant tags (sidewalk, lit, surface, crossing) are often **not guaranteed** unless you explicitly retain them.

---

### Step 2 — Convert edges into a feature table (DataFrame)
**Where:** `main.py: extract_route_features(graph, place_name, use_verdure_query)`

For each edge `(u, v, key)` it creates a row with:
- `longueur` (meters) from `edge.length`
- `type_route` from `edge.highway` using `flatten_highway()`
- `verdure` (green proximity) either by:
  - `_compute_verdure_spatial()` (OSM green features + distances), or
  - `_verdure_heuristic()` (road-type lookup)
- `proximite_principales` (major-road proximity) from `_compute_major_road_proximity()`

**Important detail:**
- `flatten_highway()` tries to normalize messy values like lists and stringified lists.

**Outputs:** `df` with at least:
`u, v, key, segment_id, longueur, type_route, verdure, proximite_principales`

---

### Step 3 — Simulate missing signals (noise and crowd density)
**Where:** `main.py: main()` and `compute_density_from_graph()`

The pipeline does **not** read real sensors. It simulates:

1) **Noise** `bruit`:
- `base_noise = NOISE_BY_HIGHWAY[type_route]` (0=quiet … 1=loud)
- add uniform random jitter ±`JITTER_AMPLITUDE`
- clamp to [0,1]

2) **Density** `densite`:
- compute edge midpoint from node coordinates
- sum influence of many fixed hotspots `DENSITY_HOTSPOTS` using exponential decay
- normalize the final heat to a 0.10–0.90 band
- add jitter and clamp

**Outputs:** `df` gains `bruit` and `densite`.

**Key assumption:** those proxies represent “real” noise/crowd patterns. They do not.

---

### Step 4 — Compute walking time
**Where:** `main.py: main()`

- `temps = longueur / WALKING_SPEED_MS` (seconds)

---

### Step 5 — Compute an edge calm score (fixed weights)
**Where:** `main.py: compute_score_fixed(df, weights=None)`

Formula (higher is calmer):

- Normalize time: `temps_norm = normalize_minmax(df["temps"])`
- Compute score:

$$
score\_calme = \alpha(1-temps\_norm) + \beta(1-bruit) + \gamma(1-densite) + \delta(verdure)
$$

With defaults:
- α=0.15, β=0.35, γ=0.30, δ=0.20

**Output:** `df["score_calme"]` in ~[0,1].

---

### Step 6 — Compute per-profile routing costs
**Where:** `main.py: compute_profile_costs(df)`

This is the **current routing core** for profiles:

- `temps_norm = normalize_minmax(df["temps"])`
- For each profile in `USER_PROFILES`, compute:

$$
cost\_profile = w_T\,temps\_norm + w_B\,bruit + w_D\,densite + w_V\,(1-verdure)
$$

Lower cost = “better” route for that profile.

Profiles currently defined in `main.py`:
- `normal`: time dominates
- `autiste`: noise + density dominate
- `fauteuil_roulant`: density + greenery dominate
- `equilibre`: balanced

**Output:** new columns: `cost_normal`, `cost_autiste`, `cost_fauteuil_roulant`, `cost_equilibre`.

---

### Step 7 — Write scores/costs back onto graph edges
**Where:** `main.py: build_scored_graph(graph, df)`

- Builds a lookup from `(u,v,key)` → `{cost_*, score_calme}`
- Copies these values into each graph edge’s attributes
- Also sets `cost_calme = 1 - score_calme` (a calmness-only cost)

**Important fallback behavior:**
- If `df` does not contain `cost_<profile>`, it writes **default 0.5**.
- If `df` does not contain `score_calme`, cost_calme becomes 0.5.

---

### Step 8 — Route computation (navigation)
**Where:** `main.py: get_best_route(scored_graph, start, end, profile)`

- Select weight attribute: `weight_attr = f"cost_{profile}"`
- If that attribute is missing (checked on a sample edge), **fallback to** `cost_calme`
- Convert lat/lon to nearest nodes if needed
- Run `nx.shortest_path(..., weight=weight_attr)` (Dijkstra)
- Aggregate stats along the chosen path:
  - total length (meters)
  - total time (seconds)
  - average `score_calme` across edges (simple mean)

**Output:** a dict: `{path, total_length_m, total_time_s, avg_score_calme, profile, ...}`

---

### Important note — there are multiple “pipelines” in this repo (inconsistent feature definitions)

Even though `main.py` contains the canonical functions, several scripts build the DataFrame in different ways.
This is not just a style issue: it changes the values you score on, and it can invalidate comparisons.

Examples:
- `main.py` (`extract_route_features`):
  - `verdure` can be a real spatial query (parks/trees) or a heuristic.
  - `proximite_principales` is a distance-based proximity function.
- `demo.py` (`build_df`):
  - `verdure` is always heuristic.
  - `proximite_principales` is a coarse rule: major roads = 1.0, else 0.4 (not distance-based).
- `visualize.py` (`build_df_fast`):
  - `densite` is often hard-set to a constant (e.g., `0.4`) for speed.
- `multi_route_map.py` (`build_df_fast`):
  - computes `score_calme` but does not compute profile costs; later routing relies on fallbacks.

**Consequence:** when you say “the scoring works” based on one script, it may not be true for another. Before improving formulas, you should pick one canonical data/feature pipeline and make the rest call it.

---

## 2) What’s wrong / risky (by stage)

### A) Data acquisition & OSM tags

#### Problem A1 — Scoring-relevant tags are mostly absent
**Symptom:** the current scoring does not use `sidewalk`, `lit`, `surface`, `crossing`, `width`, etc.

**Why it’s wrong:** your project spec (`mds/guidance.md`) explicitly expects those tags to drive calm/safety/accessibility.

**Impact:** profiles can’t reflect real accessibility needs, especially `fauteuil_roulant`.

**Fix direction:** explicitly extend the OSM extraction (OSMnx tag allow-list) and create a stable processed feature table.

---

### B) Feature extraction

#### Problem B1 — CRS/unit fallbacks can silently corrupt distance-based features
**Where:** `_compute_verdure_spatial()`, `_compute_major_road_proximity()`

Both functions try to `to_crs(epsg=32629)` (meters). If that fails, they fall back to geographic coords.

**Bug class:** If CRS conversion fails, Shapely distances are in **degrees**, but you compare them to thresholds in **meters** (50m, 200m, 1000m).

**Impact:** verdure/proximity scores can become near-constant or nonsense, and you won’t know.

**Fix direction:** never compare distances to meter thresholds unless you are certain you are in a metric CRS. If projection fails, compute distances with haversine (meters), or fail fast.

#### Problem B2 — `proximite_principales` is computed but unused
You compute a major-road proximity signal but:
- it is not used in `compute_score_fixed`
- it is not used in `compute_profile_costs`

**Impact:** wasted compute and you miss an important noise/safety proxy.

**Fix direction:** either integrate it into scoring/costs, or remove it until you can support it properly.

#### Problem B3 — Verdure scoring has discontinuities
The verdure mapping jumps at boundaries (50m and 200m). That creates artifacts where a street at 49m is scored drastically higher than a street at 51m.

**Fix direction:** make the function continuous (e.g., smooth decay), or normalize against percentiles.

---

### C) Simulated data (bruit, densite)

#### Problem C1 — You are routing on simulated noise and crowd signals
- `bruit` is assigned by road type + random jitter.
- `densite` is a sum of handcrafted hotspots + jitter.

**Why it’s wrong:** it is not anchored to real measurements. In some neighborhoods, this will be systematically wrong.

**Impact:** “calm” routes may avoid streets for fictional reasons, and will fail when validated by real users.

#### Problem C2 — Density is Casablanca-hardcoded (not transferable)
`DENSITY_HOTSPOTS` are literal Casablanca coordinates. For any other city, density becomes meaningless.

**Fix direction:** compute density from real proxies:
- POI density (amenity/shop/tourism) within 50–100m buffers
- transit proximity (stations/stops)
- landuse/commercial indicators

#### Problem C3 — Jitter can change routing decisions (instability)
Changing RNG seed can change edge costs enough to flip path decisions.

**Fix direction:**
- either remove jitter for routing (keep only for demo visualization), or
- make it deterministic per edge (hash-based pseudo-random), or
- treat jitter only as uncertainty bounds, not as the value itself.

---

### D) Scoring math & cost design

#### Problem D1 — Min-max normalization of `temps` breaks additive routing
This is the biggest issue.

You compute:
- `temps_norm = (temps - t_min) / (t_max - t_min)`
- then route by summing `temps_norm` along the path.

Because Dijkstra sums costs, the total path time-component becomes:

$$
\sum_i temps\_norm_i = \frac{\sum_i temps_i}{range} - n\_edges\cdot\frac{t\_min}{range}
$$

That second term **rewards having more edges** (larger `n_edges`) even if the route is longer in real seconds.

**Bad consequence:** a route with many short segments can be chosen over a route with fewer longer segments, even when it’s objectively slower/longer.

**Fix direction:** use an additive-safe cost:
- base cost should be real walking time: `edge_time_s`
- incorporate discomfort as a multiplier: `edge_time_s * (1 + λ * discomfort)`

#### Problem D2 — Discomfort is not weighted by exposure (length/time)
Noise/density/green are added per edge without scaling by how long you spend on the edge.

**Impact:** a long noisy edge can be under-penalized compared to multiple small edges.

**Fix direction:** compute discomfort exposure over time:
- `exposure_noise = edge_time_s * bruit`
- `exposure_crowd = edge_time_s * densite`

#### Problem D3 — `score_calme` is not a “calmness-only” score
It includes a time term `(1 - temps_norm)`.

**Impact:** “calm score” becomes a mixture of calmness + efficiency, making the metric hard to interpret.

**Fix direction:** separate:
- `calmness_score` (noise/green/major-road proximity/light/etc)
- `arrival_efficiency_score` (time)
- combine only when needed (40/40/20 philosophy).

#### Problem D4 — `compute_score_ml` is not real validation
The ML model trains on synthetic labels derived from the same features and evaluates on the same data.

**Impact:** high R² here does not mean the model matches reality; it only means you can fit your own synthetic formula.

**Fix direction:** either remove from “core pipeline” or clearly label it as a demo, and only use ML with real labels (surveys / user feedback / expert annotations).

---

### E) Routing integration & reporting

#### Problem E1 — Silent fallbacks can make routing “look fine” while it’s wrong
- If profile costs were never computed, graph edges may get `cost_profile = 0.5` for everything.
- If a profile name is unknown, routing falls back to `cost_calme`.

**Impact:** scripts can output a path without errors, but it’s not the intended profile behavior.

**Fix direction:** fail fast (raise) when:
- routing is requested with a profile not in `USER_PROFILES`
- required cost columns are missing

#### Problem E2 — Route “avg_score_calme” is an unweighted mean
It averages per-edge `score_calme` without weighting by length/time.

**Impact:** a route can appear “very calm” even if the longest edges are stressful.

**Fix direction:** compute a time-weighted or length-weighted mean:
- `avg_score_len = sum(score*length)/sum(length)`

---

### F) Repository-level inconsistencies (dangerous for evaluation)

Several scripts still assume the **older** concept of profiles (`rapide/calme/λ`) and can silently trigger fallbacks:
- `visualize.py`
- `multi_route_map.py`
- `deep_scan.py`
- `test_routing.py`

**Impact:** your tests can pass while not testing the intended thing.

**Fix direction:** update these scripts to use `normal/autiste/fauteuil_roulant/equilibre` consistently, or remove them from “verification” claims.

---

## 3) Profile-by-profile critique + improvement directions

### Profile: `normal`
**Current behavior:** dominated by `temps_norm`.

**What’s wrong:**
- `temps_norm` is min-max and causes edge-count bias.
- It optimizes relative time, not actual time.

**Improve it:**
- Use base cost = real seconds: `edge_time_s`.
- Add small penalties for noise/crowds:
  - `edge_cost = edge_time_s * (1 + λ_normal * discomfort)` with λ_normal small (e.g., 0.2–0.5).

### Profile: `autiste`
**Current behavior:** high weight on noise and density.

**What’s wrong:**
- Detours can be unbounded because the cost has no physical meaning.
- No exposure weighting (long noisy edges not penalized enough).

**Improve it:**
- Make time the base (so detours are naturally bounded).
- Use exposure-weighted discomfort:
  - `discomfort = w_noise*bruit + w_crowd*densite + w_green*(1-verdure) + w_major*proximite_principales`
  - `edge_cost = edge_time_s * (1 + λ_autiste * discomfort)` with λ_autiste high (e.g., 1.0–2.0).

### Profile: `fauteuil_roulant`
**Current behavior:** mostly avoids density, prefers greenery.

**What’s wrong (conceptual):**
- Density/greenery preferences align well with wheelchair accessibility. Dense, crowded streets are difficult to navigate in a wheelchair.
- The pipeline ignores the most relevant signals:
  - stairs (`highway=steps`)
  - sidewalk presence
  - crossings
  - surface quality
  - lighting (`lit`)

**Improve it (priority order):**
1) Add hard constraints / very large penalties:
   - avoid `highway=steps` unless unavoidable (stairs are impassable for wheelchairs)
   - penalize edges with missing sidewalk / dangerous crossings when known
2) Add surface quality features from OSM tags (smooth surfaces are critical for wheelchairs).
3) Only then tune calmness/crowd preferences.

### Profile: `equilibre`
**Current behavior:** balanced weights.

**Risk:** if costs are missing or fallbacks happen, it may become identical to other profiles.

**Improve it:**
- Ensure profiles differ at the cost-function level (λ and weights).
- Add an explicit “detour budget” check in evaluation: the route should not exceed X% of the shortest-time path.

---

## 4) Recommended fixes (prioritized)

### Quick wins (hours)
- Remove silent fallbacks:
  - unknown profile should error
  - missing `cost_*` columns should error
- Replace min-max `temps_norm` in routing costs with additive-safe time:
  - use `edge_time_s = longueur / WALKING_SPEED_MS`
- Change route reporting to length-weighted score.

### Medium (days)
- Implement time-based multiplier design:
  - `edge_cost = edge_time_s * (1 + λ_profile * discomfort)`
- Weight discomfort by exposure:
  - either by `edge_time_s` or `longueur`.
- Integrate `proximite_principales` properly or remove it.

### Larger improvements (week+)
- Replace synthetic density/noise with real proxies:
  - POI density, transit proximity, commercial intensity
- Add missing-data policy + confidence:
  - store which fields are inferred/defaulted
  - compute `confidence_score` and penalize low-confidence edges

---

## 5) Conceptual test cases where the current approach gives bad results

Use these as “red flag” scenarios. Each test case is: **setup → expected → current behavior → root cause → fix**.

### TC1 — “Profile costs missing” silently becomes hop-count routing
- **Setup:** build a `df` with `score_calme` but do not call `compute_profile_costs()`.
- **Expected:** `normal/autiste/fauteuil_roulant/equilibre` still behave differently.
- **Current:** `cost_normal`, `cost_autiste`, etc. become default `0.5` everywhere → routing minimizes number of edges.
- **Root cause:** `build_scored_graph()` writes default 0.5 costs.
- **Fix:** fail fast if requested profile cost columns are missing.

### TC2 — Unknown profile name returns a route anyway
- **Setup:** call `get_best_route(..., profile="rapide")`.
- **Expected:** error (“unknown profile”).
- **Current:** falls back to `cost_calme` and returns a path.
- **Root cause:** fallback logic in `get_best_route()`.
- **Fix:** validate `profile in USER_PROFILES`.

### TC3 — Min-max time normalization prefers more edges (edge-count bias)
- **Setup:** compare two alternative paths:
  - Path A: 1 edge of 100s
  - Path B: 100 edges of 2s each (=200s total)
- **Expected:** Path A should be chosen for time-heavy profiles.
- **Current:** with min-max scaling, `temps_norm(100s)` can equal the sum of many small `temps_norm(2s)` values, so Path B may look equally good or better.
- **Root cause:** `temps_norm` subtracts a global minimum per edge and is summed.
- **Fix:** base routing cost on real seconds, not min-max.

### TC4 — Long noisy segment under-penalized vs many short segments
- **Setup:** one route contains a single long loud edge; another contains many short medium-noise edges.
- **Expected:** the long loud exposure should dominate.
- **Current:** both are penalized per-edge, not per time exposure.
- **Root cause:** discomfort terms not multiplied by time/length.
- **Fix:** exposure-weighted penalties.

### TC5 — Running on a different city makes density meaningless
- **Setup:** `fetch_graph("Rabat, Morocco")` and compute density.
- **Expected:** density should correlate with Rabat’s real crowded areas.
- **Current:** density uses Casablanca hotspots → near-random/flat outcomes.
- **Root cause:** hardcoded `DENSITY_HOTSPOTS`.
- **Fix:** derive density from POIs/transit in the selected city.

### TC6 — CRS conversion fails → verdure/proximity broken
- **Setup:** CRS conversion fails (common with missing CRS metadata).
- **Expected:** distances still represent meters.
- **Current:** distances computed in degrees but compared to meter thresholds.
- **Root cause:** fallback path in `_compute_verdure_spatial()` and `_compute_major_road_proximity()`.
- **Fix:** never mix units; use haversine if not projected.

### TC7 — Different seeds → different routes
- **Setup:** run pipeline with different `--seed` values.
- **Expected:** routing should be stable for the same city.
- **Current:** jitter alters edge costs enough to flip path choices.
- **Root cause:** randomness injected into core signals.
- **Fix:** remove jitter from routing inputs, or make deterministic.

### TC8 — Fauteuil roulant profile chooses steps because they are “quiet”
- **Setup:** area where `highway=steps` is available along a quiet shortcut.
- **Expected:** fauteuil_roulant should strongly avoid steps.
- **Current:** steps are assigned very low noise and no accessibility penalty → may be selected.
- **Root cause:** missing accessibility feature set; scoring optimizes calm proxies only.
- **Fix:** hard penalties/constraints for steps + sidewalk/crossing/surface features.

---

## 6) Bottom line

Right now, the system is a good demo of “custom routing weights”, but the **current edge-cost design is mathematically unsafe** (min-max time + additive path sum) and the **profile semantics are not reliable** due to silent fallbacks and missing accessibility signals.

If you fix only one thing first, fix this:
- **route on real time (seconds) + time-multiplied discomfort**, not min-max time.

Then, to truly improve each profile, you need:
- real proxies (POI/transit/accessibility tags),
- explicit missing-data policy,
- and validation that cannot silently fall back.
