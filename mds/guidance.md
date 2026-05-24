# NeuroRoute Calme — Project Context (Compressed Spec)

## Overview
NeuroRoute Calme is a smart pedestrian routing system for Casablanca that prioritizes **calm, sensory-friendly, and comfortable walking routes** instead of shortest distance only.

Target users:
- Neurodivergent users
- People sensitive to noise/crowds
- Users seeking stress-reduced walking paths
- General pedestrians preferring calm routes

---

## Core Idea

Traditional routing:
- shortest path
- fastest path

NeuroRoute Calme routing:
- lower noise
- lower crowd density
- greener streets
- better lighting
- safer sidewalks
- time-aware context

Uses modified Dijkstra / A* with custom edge weights.

---

## Main Data Source

### OpenStreetMap (OSM)

Used for:
- road network
- footways
- sidewalks
- crossings
- lighting tags
- parks
- POI
- road type

Python library:
- osmnx
- geopandas
- networkx
- pandas

---

## Graph Model

### Nodes
Intersections

### Edges
Street segments

Each edge contains:
- length
- highway type
- sidewalk
- lit
- maxspeed
- lanes
- surface
- crossing
- geometry

---

## Important OSM Tags

### Traffic / Noise
- highway
- maxspeed
- lanes
- surface

### Walkability
- sidewalk
- width
- footway
- crossing

### Light / Safety
- lit
- covered

### Green / Calm
- leisure=park
- landuse=grass
- natural=tree
- garden
- water

### Crowd Proxies
- amenity
- shop
- tourism
- public_transport

---

## Engineered Features Per Segment

- noise_score
- crowd_score
- green_score
- light_score
- sidewalk_score
- arrival_efficiency
- transit_proximity
- poi_density_50m
- road_hierarchy
- final_score

All normalized between 0 and 1.

0 = stressful / bad  
1 = calm / optimal

---

## Core Scoring Philosophy (UPDATED)

NeuroRoute Calme uses **three primary routing criteria**:

### 1. Calmness (40%)
Represents sensory noise and environmental stress:
- highway type
- maxspeed
- surface
- traffic intensity proxies

Goal:
→ minimize noise and sensory overload

---

### 2. Crowd Comfort (40%)
Represents pedestrian density and social congestion:
- POI density (cafes, shops, schools, transport)
- commercial activity
- tourism zones
- public transport proximity

Goal:
→ avoid overcrowded streets

---

### 3. Arrival Efficiency (20%)
Represents practical walking efficiency (NOT vehicle speed):
- estimated walking time
- route length
- detours vs direct path

Formula:

```latex
t = \frac{d}{v}

