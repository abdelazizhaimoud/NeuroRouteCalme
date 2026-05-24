# NeuroRoute Calme — Easy Explanation

> Read this before your meeting. It explains what every part of the code does in plain English.

---

## What is this project?

We built a system that finds the **calmest walking path** in Casablanca — not the shortest one. It avoids noisy streets, crowded areas, and prefers green routes. Everything runs from a single file: `main.py`.

---

## How it works, step by step

### 1. We download the map of Casablanca

We use a library called `osmnx` that talks to OpenStreetMap (the free world map). With one line of code, we download every walkable street in Casablanca:

```python
# main.py, line 139 — inside fetch_graph()
graph = ox.graph_from_place("Casablanca, Morocco", network_type="walk")
```

This gives us a **graph** — like a network of connected dots:
- **Nodes** = intersections where streets meet (we got **54,813** of them)
- **Edges** = street segments connecting two intersections (we got **164,818** of them)

The data is saved locally in a `cache/` folder, so next time we run the code it loads instantly instead of downloading again.

---

### 2. We convert the graph into a table

A graph is hard to do math on. So we convert it into a **pandas DataFrame** — basically a big spreadsheet where each row is one street segment.

```python
# main.py, line 148-183 — inside extract_route_features()
edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)  # line 156
df["longueur"] = edges["length"]                           # line 167
df["type_route"] = edges["highway"].apply(flatten_highway)  # line 170
```

For each of the 164,818 streets, we extract:

| Column | What it is | Where it comes from |
|--------|-----------|-------------------|
| `longueur` | Length in meters | Already in the OSM data |
| `type_route` | Type of road | The `highway` tag from OSM (e.g. "footway", "residential", "primary") |
| `verdure` | How green the area is | We query OSM for parks, trees, gardens nearby (line 189) |
| `proximite_principales` | How close to a big road | We measure distance to the nearest primary/trunk road (line 245) |

**How verdure works** (line 186-229): We ask OSM for all parks, gardens, and trees in Casablanca. We found **3,284 green features**. Then for each street, we measure how far its center point is from the nearest green feature. Closer = higher verdure score.

**How proximity works** (line 245-294): We check if the street IS a major road (score = 1.0) or how far it is from one. Less than 50 meters away = 1.0, more than 1km away = 0.05.

---

### 3. We simulate noise and crowd density

We don't have real noise sensors or crowd counters. So we simulate them using common sense logic:

**Noise (`bruit`)** — line 37-59 and line 714-716:

We made a lookup table: each road type gets a base noise level. A pedestrian path is quiet (0.10), a highway is loud (1.00):

```python
# main.py, line 37-58 — NOISE_BY_HIGHWAY dictionary
"footway":     0.10    # very quiet
"residential": 0.35    # some noise
"secondary":   0.70    # noisy
"primary":     0.85    # very noisy
"trunk":       1.00    # maximum noise
```

Then we add a tiny random number (between -0.05 and +0.05) so not every `residential` street has exactly 0.35. This is called **jitter** — it makes the data more realistic.

```python
# main.py, line 714-716 — inside main()
base_noise = df["type_route"].map(NOISE_BY_HIGHWAY)
jitter = rng.uniform(-0.05, 0.05, size=len(df))
df["bruit"] = clip(base_noise + jitter, 0, 1)
```

**Crowd density (`densite`)** — line 440-470:

We assume the city has many crowded areas, not just one. We defined **100 hotspots** around Casablanca (markets, stations, commercial centers).

Instead of just checking the nearest point, we treat each hotspot as a "heater" that emits a crowd density field. A street's total density is the **sum of the density from all 100 hotspots**, based on how close it is to each one.

```python
# We use exponential decay to sum the influence of all hotspots:
influence = np.exp(-distance / 1.5)
raw_density = sum(all_influences)
```

We calculate the actual distance using the **haversine formula** (line 118-125), which measures distance between two GPS coordinates on Earth's curved surface. The final sum is normalized to a 0.10-0.90 scale, and we add jitter here too.

---

### 4. We calculate walking time

Simple division — we divide the length by walking speed (5 km/h = 1.39 m/s):

```python
# main.py, line 722
df["temps"] = df["longueur"] / 1.39  # time in seconds
```

A 100-meter street takes about 72 seconds to walk.

---

### 5. We score each street for "calmness"

Now comes the core formula. We combine the 4 features into **one calm score** between 0 and 1.

```python
# main.py, line 380-398 — inside compute_score_fixed()
score = (
    0.15 * (1 - temps_norm)  +   # shorter walk = calmer
    0.35 * (1 - bruit)       +   # less noise = calmer
    0.30 * (1 - densite)     +   # less crowd = calmer
    0.20 * verdure                # more green = calmer
)
```

Why do we write `(1 - bruit)` instead of just `bruit`? Because we want a **calmness** score. High noise = bad for calm, so we flip it: `(1 - 0.85) = 0.15` means a noisy street gets a low calmness contribution.

The weights (0.15, 0.35, 0.30, 0.20) add up to 1.0. We gave the most weight to noise (0.35) because for people sensitive to noise, that's the most important factor.

**The result:** a quiet footway near a park scores **~0.74**. A trunk road in the center scores **~0.38**.

---

### 6. We also train a machine learning model (advanced version)

Instead of choosing the weights by hand, we let a computer learn them:

```python
# main.py, line 401-459 — inside compute_score_ml()
model = Ridge(alpha=1.0)       # line 438 — Ridge regression from scikit-learn
model.fit(X, y_train)          # line 439 — train the model
y_pred = model.predict(X)      # line 442 — get predictions
```

But wait — the model needs training data. We don't have real survey data, so we create **synthetic expert labels** (line 427-435): a non-linear formula that simulates what a human expert would rate as "calm". We add Gaussian noise to make it realistic.

The model learns with **R2 = 0.916** — meaning it captures 91.6% of the pattern. The weights it learns are very close to our manual ones, which validates our choices.

---

### 7. We put the scores back on the graph

Now we take the calm score from the table and write it back onto the graph edges:

```python
# main.py, line 476-505 — inside build_scored_graph()
data["score_calme"] = sc           # the calm score (0-1)
data["cost_calme"] = 1.0 - sc      # INVERTED for the algorithm
data["length_norm"] = length_norm   # normalized distance
```

Why invert? Because the routing algorithm (Dijkstra) **minimizes** cost. A calm street has score 0.74, so its cost is `1 - 0.74 = 0.26` (cheap to traverse). A stressful street has score 0.38, so its cost is `1 - 0.38 = 0.62` (expensive to traverse). The algorithm will naturally avoid the expensive edges.

---

### 8. We find the best route using Dijkstra

Given a start point and end point (as GPS coordinates), we find the optimal path:

```python
# main.py, line 515-579 — inside get_best_route()

# Step 1: Find the nearest graph node to the GPS coordinates
start = ox.nearest_nodes(graph, X=start_lon, Y=start_lat)   # line 538

# Step 2: Calculate edge cost = blend of calmness and distance
data[weight_attr] = lam * cost_calme + (1 - lam) * length_norm  # line 546

# Step 3: Run Dijkstra's shortest path algorithm
path = nx.shortest_path(graph, start, end, weight=weight_attr)  # line 550
```

The **lambda** parameter controls what matters more — calmness or distance:

| Profile | Lambda | What it means |
|---------|--------|--------------|
| "rapide" | 0.15 | 85% distance + 15% calmness → takes the short way |
| "equilibre" | 0.50 | 50% distance + 50% calmness → balanced |
| "calme" | 0.85 | 15% distance + 85% calmness → takes detours to stay calm |

The function returns a dictionary with the full path, total distance, walking time, and average calm score.

---

### 9. The main() function ties it all together

```python
# main.py, line 698-746 — the main() function runs everything in order:

graph = fetch_graph("Casablanca, Morocco")          # Step 1: download map
df = extract_route_features(graph, ...)              # Step 2: build the table
df["bruit"] = ...                                    # Step 3: simulate noise
df["densite"] = compute_density_from_graph(graph, df) # Step 3: simulate density
df["temps"] = df["longueur"] / 1.39                  # Step 4: walking time
df["score_calme"] = compute_score_fixed(df)          # Step 5: fixed scoring
df["score_ml"] = compute_score_ml(df)                # Step 6: ML scoring
scored_graph = build_scored_graph(graph, df)          # Step 7: put scores on graph
demo_routing(scored_graph)                            # Step 8: find routes
export_dataframe(df)                                  # Step 9: save CSV
```

You run it with just: `python main.py`

---

## The output

The final CSV file (`outputs/routes_casablanca.csv`) has **164,818 rows** and **12 columns**:

| Column | Example value | What it means |
|--------|--------------|--------------|
| segment_id | 123_456_0 | Unique ID for this street segment |
| u, v | 123, 456 | Start and end node IDs |
| longueur | 45.2 | Length in meters |
| temps | 32.5 | Walking time in seconds |
| type_route | residential | Type of road |
| verdure | 0.30 | Greenery score (0-1) |
| proximite_principales | 0.40 | How close to a major road (0-1) |
| bruit | 0.35 | Simulated noise (0-1) |
| densite | 0.60 | Simulated crowd density (0-1) |
| score_calme | 0.62 | Calm score with fixed weights (0-1) |
| score_ml | 0.58 | Calm score from ML model (0-1) |

---

## Summary diagram

```
[OpenStreetMap API]
        |
        v
  1. fetch_graph()           --> graph (54,813 nodes, 164,818 edges)
        |
        v
  2. extract_route_features() --> DataFrame with longueur, type, verdure, proximite
        |
        v
  3. simulate bruit + densite --> DataFrame now has 6 features per street
        |
        v
  4. compute walking time    --> temps = longueur / 1.39
        |
        v
  5. compute_score_fixed()   --> score_calme = weighted sum of 4 features
     compute_score_ml()      --> score_ml = Ridge regression learned weights
        |
        v
  6. build_scored_graph()    --> graph edges now carry cost_calme
        |
        v
  7. get_best_route()        --> Dijkstra finds optimal path for chosen profile
        |
        v
  8. export CSV + HTML maps  --> outputs/routes_casablanca.csv
                                 outputs/map_multi_routes.html
```

---

## Extra: How the synthetic expert labels work (line 427-435)

This is the part that confuses most people. Here's the idea step by step:

**The problem:** We want to train a machine learning model to learn the best scoring weights. But ML needs **training data** — thousands of streets labeled with a "true" calm score. We don't have real survey data from users.

**The solution:** We create **fake expert labels** — we pretend a human expert rated every street, and we use a formula to generate those ratings. But we make the formula **deliberately different** from the simple linear formula in Step 5, so the ML has something non-trivial to learn.

Here's the formula, line by line:

```python
# main.py, line 427-435
y_expert = (
    0.10 * (1 - temps_norm)                    # (A) time component — same idea
    + 0.30 * (1 - bruit) ** 1.5                # (B) noise — raised to power 1.5
    + 0.25 * (1 - densite) ** 1.3              # (C) density — raised to power 1.3
    + 0.20 * sqrt(verdure)                     # (D) greenery — square root
    + 0.15 * verdure * (1 - bruit)             # (E) interaction term
)
noise = rng.normal(0, 0.03, size=len(df))      # (F) Gaussian noise
y_train = clip(y_expert + noise, 0, 1)         # (G) clip to [0, 1]
```

**What each part does:**

| Part | What | Why it's different from the fixed formula |
|------|------|----------------------------------------|
| (A) | Time contribution | Same as fixed, nothing special |
| (B) | `(1-bruit)**1.5` | The `**1.5` means a noisy street (bruit=0.9) is punished **more** than the linear formula would. It's non-linear — a street with noise 0.8 is much worse than two streets with noise 0.4 |
| (C) | `(1-densite)**1.3` | Same idea — high density is punished exponentially |
| (D) | `sqrt(verdure)` | Square root means the first bit of greenery helps a lot, but adding more green has **diminishing returns** (going from 0 to 0.3 helps more than going from 0.7 to 1.0) |
| (E) | `verdure * (1-bruit)` | **Interaction term** — a green street that is ALSO quiet gets a bonus. Green + noisy doesn't help as much. This is something the linear model can't capture directly |
| (F) | Gaussian noise (mean=0, std=0.03) | We add random noise to simulate the fact that real experts wouldn't agree perfectly — their ratings would vary a bit |
| (G) | Clip to [0,1] | Make sure no value goes below 0 or above 1 |

**Then what?** We train a Ridge regression on these fake labels. The Ridge model is **linear** (no powers, no square roots), so it can't perfectly reproduce the non-linear expert formula — but it gets close (R2=0.916). The weights it learns tell us "if I had to approximate this complex human judgment with a simple weighted sum, these would be the best weights."

**In production:** You would replace `y_expert` with real survey data from actual users walking the streets and rating them.

---

## Extra: Did we use A* or Dijkstra?

**We use Dijkstra, NOT A*.**

```python
# main.py, line 548-550
# Run Dijkstra (handles MultiDiGraph reliably)
path = nx.shortest_path(scored_graph, start, end, weight=weight_attr)
```

**Why not A*?** We originally tried `nx.astar_path()`, but it had issues with our graph:

1. **MultiDiGraph problem**: OpenStreetMap graphs are MultiDiGraphs — there can be multiple edges between the same two nodes (e.g. two parallel lanes). A* with custom weight functions didn't handle this well in networkx.
2. **Weight function issue**: A* requires the weight as either a string (attribute name) or a function. With our pre-computed profile weights stored as edge attributes, Dijkstra via `nx.shortest_path(weight="attribute_name")` is more reliable.
3. **Optimality**: Both Dijkstra and A* find the **optimal** (best) path. A* is faster when you have a good heuristic, but Dijkstra is guaranteed to work correctly on any graph. For our graph size (~55k nodes), Dijkstra runs in under 1 second anyway.

**Bottom line**: Same result, Dijkstra is just more reliable for our specific graph type.

---

## Extra: The Multi-Hotspot Additive Density

The current implementation uses **100 density hotspots** across Casablanca (defined in `DENSITY_HOTSPOTS` at the top of `main.py`).

**How we calculate it**:
We use an **Additive Heatmap Model** (similar to Kernel Density Estimation). 
If a street is near an isolated hotspot, it gets a high density score. But if a street is surrounded by 5 closely-packed hotspots (like in Derb Sultan or Maarif), their influences **stack together**, creating a massive "red zone" of extreme density.

This is much more realistic than a single center point or simple radius logic, as it accurately models the true, complex urban fabric of Casablanca where multiple busy districts overlap.
