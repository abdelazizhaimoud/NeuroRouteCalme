# NeuroRoute Calme — Phases et Étapes d'Implémentation

> **Document généré le :** 20/05/2026
> **Objectif :** Tracer chaque étape du projet vers le code responsable et identifier ce qui est réalisé / non réalisé.

---

## Légende

| Symbole | Signification |
|---------|--------------|
| ✅ | Implémenté et fonctionnel |
| ⚠️ | Partiellement implémenté |
| ❌ | Non implémenté |

---

## Résumé global

| Phase | Statut | Couverture |
|-------|--------|------------|
| Phase 1 — Data | ✅ Complète | 100% |
| Phase 2 — Scoring | ✅ Complète | 100% |
| Phase 3 — Routage | ✅ Complète | 100% |
| Phase 4 — Personnalisation | ✅ Complète | 100% |
| Phase 5 — Visualisation | ✅ Complète | 100% |

---

## PHASE 1 : DATA — "Construire un graphe urbain exploitable"

### Étape 1 — Récupération des données ✅

| Élément | Détail |
|---------|--------|
| **API** | OpenStreetMap (via Overpass API) |
| **Librairie** | `osmnx` |
| **Livrable** | Graphe piéton de Casablanca (`cache/casablanca_walk.graphml` — 63 Mo) |

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L302-L352) | `fetch_graph(place_name, cache_dir)` | Télécharge le graphe piéton via `ox.graph_from_place()` avec `network_type="walk"`, gère le cache GraphML |
| [`main.py`](main.py#L319-L335) | Logique de cache | Vérifie si `casablanca_walk.graphml` existe en cache, sinon télécharge et sauvegarde |
| [`main.py`](main.py#L220-L230) | `EXTRA_USEFUL_TAGS_WAY` | Tags OSM supplémentaires conservés : `sidewalk`, `lit`, `surface`, `tactile_paving`, etc. |

**Vérification :**
- Le graphe contient **~90k nœuds** et **~165k arêtes** (Casablanca complète)
- Test automatisé dans [`deep_scan.py`](deep_scan.py#L66-L91) (vérifie intégrité, présence de `length`, `highway`, coordonnées x/y)

---

### Étape 2 — Extraction des features par segment ✅

| Feature | Colonne DataFrame | Implémenté |
|---------|-------------------|------------|
| Longueur | `longueur` | ✅ |
| Type de route | `type_route` | ✅ |
| Présence de verdure | `verdure` | ✅ |
| Proximité routes principales | `proximite_principales` | ✅ |

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L359-L397) | `build_edge_features(graph, place_name, ...)` | Construit le DataFrame avec toutes les features |
| [`main.py`](main.py#L382) | `df["longueur"]` | Extrait `edges["length"]` du graphe OSMnx |
| [`main.py`](main.py#L383) | `df["type_route"]` | Extrait `edges["highway"]` puis aplati via `flatten_highway()` |
| [`main.py`](main.py#L241-L254) | `flatten_highway(value)` | Normalise les types de route (gère listes, strings, `stringified lists`) |
| [`main.py`](main.py#L409-L446) | `_compute_verdure_spatial(edges, place_name)` | Requête OSM pour les espaces verts via `ox.features_from_place()` avec `GREEN_TAGS`, calcul de distance projetée |
| [`main.py`](main.py#L449-L459) | `_verdure_heuristic(highway_type)` | Fallback : estime la verdure depuis le type de route uniquement |
| [`main.py`](main.py#L462-L488) | `_compute_major_road_proximity(edges, type_route)` | Calcul de distance aux routes principales (primary, trunk, motorway) via projection métrique |
| [`main.py`](main.py#L180-L186) | `GREEN_TAGS`, `GREEN_BUFFER_METERS` | Configuration : tags verts OSM et rayon de recherche (50m) |
| [`main.py`](main.py#L135-L139) | `MAJOR_HIGHWAY_TYPES` | Ensemble des types de routes principales |

**Livrable :** DataFrame avec colonnes `[u, v, key, segment_id, longueur, type_route, verdure, proximite_principales]`

---

### Étape 3 — Simulation des données manquantes ✅

| Donnée simulée | Colonne | Méthode |
|----------------|---------|---------|
| Bruit | `bruit` | Basé sur le type de route + jitter aléatoire |
| Densité | `densite` | Basé sur la distance aux hotspots centre-ville |

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L495-L514) | `simulate_missing_data(df, rng_seed)` | Ajoute les colonnes `bruit` et `densite` |
| [`main.py`](main.py#L142-L166) | `NOISE_BY_HIGHWAY` | Table de correspondance type de route → niveau de bruit (0=calme, 1=bruyant) |
| [`main.py`](main.py#L900-L904) | Bruit dans `build_scoring_dataframe` | `base_noise + jitter` clippé à [0,1], arrondi à 3 décimales |
| [`main.py`](main.py#L528-L578) | `compute_density_from_graph(graph, df, rng)` | Densité multi-hotspots avec influence gaussienne exponentielle |
| [`main.py`](main.py#L30-L133) | `DENSITY_HOTSPOTS` | 100+ coordonnées GPS de zones denses (marchés, gares, centres commerciaux, etc.) |
| [`main.py`](main.py#L169-L175) | `DENSITY_BANDS` | Bandes distance-densité pour le fallback générique |
| [`main.py`](main.py#L177) | `JITTER_AMPLITUDE = 0.05` | Amplitude du bruit aléatoire ajouté aux simulations |

**Livrable :** Dataset enrichi avec `bruit ∈ [0,1]` et `densite ∈ [0,1]`

---

## PHASE 2 : SCORING — "Créer un score de calme"

### Étape 4 — Fonction de coût à poids fixes ✅

**Formule implémentée :**

```
Score = α·(1-temps_norm) + β·(1-traffic_stress) + γ·(1-densite) + δ·verdure
```

Où `traffic_stress = max(bruit, proximite_principales)`

| Poids | Valeur par défaut | Signification |
|-------|-------------------|---------------|
| α (alpha) | 0.15 | Temps (efficacité) |
| β (beta) | 0.35 | Bruit (le plus important pour neurodivergents) |
| γ (gamma) | 0.30 | Densité (évitement de foule) |
| δ (delta) | 0.20 | Verdure (bonus espaces verts) |

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L606-L631) | `compute_score_fixed(df, weights)` | Calcul du score de calme avec poids fixes |
| [`main.py`](main.py#L585-L590) | `normalize_minmax(series)` | Normalisation min-max simple |
| [`main.py`](main.py#L593-L603) | `normalize_robust_minmax(series, q_low, q_high)` | Normalisation robuste par quantiles (5%-95%) — évite les outliers |
| [`main.py`](main.py#L190-L196) | `DEFAULT_WEIGHTS` | Poids par défaut (somme = 1.0) |

**Livrable :** Colonne `score_calme ∈ [0,1]` (plus élevé = plus calme)

---

### Étape 5 — Version avancée ML ✅

**Approche implémentée :**
1. Génère des labels synthétiques experts (heuristique non-linéaire avec interactions)
2. Entraîne une régression Ridge (scikit-learn)
3. Évalue R² et MAE sur un jeu de test (80/20 split)
4. Retourne les prédictions et les poids appris

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L684-L749) | `compute_score_ml(df, rng_seed)` | Pipeline ML complet : features → labels synthétiques → Ridge → évaluation |
| [`main.py`](main.py#L708-L713) | Features ML | `temps_inv`, `calme_sonore`, `espace`, `verdure` |
| [`main.py`](main.py#L716-L722) | Labels experts synthétiques | Heuristique non-linéaire avec `**1.5`, `sqrt`, et terme d'interaction `verdure*(1-traffic_stress)` |
| [`main.py`](main.py#L730-L731) | Modèle | `Ridge(alpha=1.0)` de scikit-learn |

**Livrable :** Colonne `score_ml` + dictionnaire des poids appris

---

## PHASE 3 : ROUTAGE — "Trouver le meilleur chemin"

### Étape 6 — Algorithme de routage ✅

| Élément | Implémentation |
|---------|---------------|
| **Algorithme** | Dijkstra via `nx.shortest_path()` (networkx) |
| **Librairie** | `networkx` |
| **Poids** | `cost_<profil>` au lieu de la distance brute |

> **Note :** L'implémentation utilise Dijkstra (`nx.shortest_path` avec `weight`). A* a été envisagé mais Dijkstra est plus fiable sur les `MultiDiGraph` de networkx. Une heuristique haversine est définie mais non activée (L793-797).

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L800-L879) | `get_best_route(scored_graph, start, end, profile)` | Fonction principale de routage, accepte nœud ID ou (lat,lon) |
| [`main.py`](main.py#L838) | `nx.shortest_path(scored_graph, start, end, weight=weight_attr)` | Appel Dijkstra avec poids du profil |
| [`main.py`](main.py#L831-L834) | Résolution lat/lon | `ox.nearest_nodes()` pour convertir (lat,lon) → ID nœud le plus proche |
| [`main.py`](main.py#L842-L879) | Statistiques de route | Calcul `total_length_m`, `total_time_s`, `total_cost`, `avg_score_calme` (pondéré par longueur) |
| [`main.py`](main.py#L793-L797) | `_heuristic(u_node, v_node)` | Heuristique A* définie (haversine) mais pas encore branchée |

---

### Étape 7 — Modification du graphe (poids = score) ✅

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L761-L790) | `build_scored_graph(graph, df)` | Copie le graphe, injecte `score_calme`, `cost_calme`, `cost_<profil>`, `temps` sur chaque arête |
| [`main.py`](main.py#L634-L681) | `compute_profile_costs(df)` | Calcule le coût par profil : `cost = time_eff * (1 + λ * discomfort)` |
| [`main.py`](main.py#L208) | `DISCOMFORT_LAMBDA_BASE = 2.0` | Facteur de trade-off temps/inconfort |
| [`main.py`](main.py#L212-L217) | `STEPS_TIME_FACTORS` | Pénalité supplémentaire pour les escaliers par profil |

**Livrable :** `get_best_route(start, end, profile)` — retourne dictionnaire avec chemin, stats, score moyen

---

## PHASE 4 : PERSONNALISATION — "Adapter selon profil"

### Étape 8 — Définition des profils utilisateurs ✅

| Profil | Description |
|--------|-------------|
| `normal` | Priorité temps, peu sensible au bruit/foule |
| `autiste` | Bruit très pénalisé, évite la foule |
| `fauteuil_roulant` | Accessibilité + simplicité, densité très pénalisée, escaliers très pénalisés |
| `equilibre` | Compromis entre temps, bruit, densité et verdure |

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L199-L204) | `USER_PROFILES` | Dictionnaire des profils avec poids `{temps, bruit, densite, verdure}` |

**Poids par profil :**

| Profil | temps | bruit | densite | verdure |
|--------|-------|-------|---------|---------|
| normal | 0.70 | 0.10 | 0.10 | 0.10 |
| autiste | 0.10 | 0.50 | 0.30 | 0.10 |
| fauteuil_roulant | 0.20 | 0.10 | 0.50 | 0.20 |
| equilibre | 0.30 | 0.25 | 0.25 | 0.20 |

---

### Étape 9 — Adaptation dynamique des poids ✅

**Formule de coût par profil :**

```
discomfort = (w_bruit/Σ * traffic_stress) + (w_densite/Σ * densite) + (w_verdure/Σ * (1-verdure))
lambda     = DISCOMFORT_LAMBDA_BASE * (1 - w_temps)
time_eff   = temps * (1 + steps_factor * is_steps)
cost       = time_eff * (1 + lambda * discomfort)
```

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`main.py`](main.py#L634-L681) | `compute_profile_costs(df)` | Applique la formule pour chaque profil, crée `cost_normal`, `cost_autiste`, `cost_fauteuil_roulant`, `cost_equilibre` |
| [`main.py`](main.py#L657-L679) | Boucle sur `USER_PROFILES` | Calcul dynamique de discomfort, lambda, time_eff, cost |
| [`main.py`](main.py#L212-L217) | `STEPS_TIME_FACTORS` | Multiplicateur d'escaliers par profil (`normal=0.5`, `autiste=0.75`, `fauteuil_roulant=2.5`) |

**Livrable :** Système dynamique de poids — changer `USER_PROFILES` adapte automatiquement le routage

---

## PHASE 5 : VISUALISATION — "Carte interactive"

### Étape 10 — Affichage carte ✅

| Librairie | Utilisée | Fichiers |
|-----------|----------|----------|
| **Folium** (Python) | ✅ | `visualize.py`, `demo.py`, `multi_route_map.py`, `demo_100_routes.py`, `map_all_edges_scores.py` |
| **Leaflet.js** | ✅ (via Folium, qui génère du Leaflet.js) | Toutes les cartes HTML générées |

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`visualize.py`](visualize.py#L65-L106) | `make_score_map(graph, df)` | Carte choroplèthe colorée par `score_calme` (rouge=stressant, vert=calme) avec légende |
| [`visualize.py`](visualize.py#L109-L175) | `make_route_map(scored_graph, df)` | Carte de comparaison des itinéraires par profil |
| [`demo.py`](demo.py#L95-L148) | Génération map dans `__main__` | Carte simple avec 3 profils (normal, fauteuil_roulant, autiste) + légende + marqueurs |
| [`multi_route_map.py`](multi_route_map.py#L171-L379) | `build_map(graph, df, all_results)` | Carte avancée : 6 routes × 4 profils, heatmap score en fond, table de comparaison, layer control |
| [`map_all_edges_scores.py`](map_all_edges_scores.py#L70-L143) | `main()` | Visualisation de TOUTES les arêtes colorées par score (165k arêtes) via `folium.GeoJson` |
| [`demo_100_routes.py`](demo_100_routes.py#L13-L135) | `generate_100_routes_demo()` | 100 routes aléatoires (1-5km), layer control par trajet individuel |

**Cartes générées dans `outputs/` :**

| Fichier | Contenu | Taille |
|---------|---------|--------|
| `map_scores.html` | Heatmap score de calme (8k arêtes échantillonnées) | ~10 Mo |
| `map_routes.html` | Comparaison des profils (1 route) | ~1.7 Mo |
| `map_multi_routes.html` | 6 routes × 4 profils + heatmap fond | ~4 Mo |
| `map_scores_all_edges.html` | Toutes les arêtes colorées | ~53 Mo |
| `demo_route.html` | Demo simple 3 profils | ~12 Ko |
| `demo_100_routes.html` | 100 routes aléatoires toggleables | ~822 Ko |

---

### Étape 11 — Comparaison chemin classique vs calme ✅

**Implémenté dans plusieurs fichiers :**

| Fichier | Fonctionnalité |
|---------|----------------|
| [`demo.py`](demo.py#L78-L91) | Compare `normal` vs `autiste` vs `fauteuil_roulant`, affiche le détour |
| [`visualize.py`](visualize.py#L109-L175) | Carte avec 4 profils superposés (normal, équilibre, autiste, fauteuil roulant) |
| [`multi_route_map.py`](multi_route_map.py#L335-L378) | Table HTML intégrée : comparaison Autiste vs Normal (distance, temps, score calme, détour, gain) |
| [`demo_100_routes.py`](demo_100_routes.py#L57-L78) | Comparaison sur 100 routes aléatoires |
| [`test_routing.py`](test_routing.py) | Test de vérification : les 4 profils trouvent des routes différentes |

**Livrable :** Cartes interactives montrant côte à côte le chemin classique (normal) et le chemin calme (autiste/fauteuil roulant)

---

## Fichiers annexes importants

| Fichier | Rôle |
|---------|------|
| [`deep_scan.py`](deep_scan.py) | Vérification automatisée bout-en-bout de toutes les phases (40+ checks) |
| [`check_graph.py`](check_graph.py) | Visualisation statique du graphe brut (PNG haute résolution) |
| [`pick_coords.py`](pick_coords.py) | Outil pour sélectionner des coordonnées sur une carte |
| [`archive/prepare_scoring.py`](archive/prepare_scoring.py) | Pipeline de pré-scoring avancé (highway_score, surface_score, speed_kph, infrastructure_bonus, lane_count) — archivé |
| [`requirements.txt`](requirements.txt) | Dépendances : osmnx, geopandas, pandas, numpy, shapely, scikit-learn |

---

## Ce qui est NON réalisé / Améliorations possibles

> **Toutes les 5 phases et leurs 11 étapes sont implémentées.** Voici les points d'amélioration identifiés :

| Élément | Statut | Détail |
|---------|--------|--------|
| A* au lieu de Dijkstra | ⚠️ Préparé mais pas activé | Heuristique haversine définie (`_heuristic`, L793) mais `nx.shortest_path` utilise Dijkstra. A* possible via `nx.astar_path()` |
| Données de bruit réelles | ⚠️ Simulé | Bruit basé sur type de route + jitter. Des données réelles (capteurs, API bruit urbain) amélioreraient la précision |
| Données de densité réelles | ⚠️ Simulé | Densité basée sur hotspots prédéfinis. Des données réelles (compteurs piétons, Google Popular Times) amélioreraient la précision |
| Labels ML réels | ⚠️ Synthétique | Le score ML utilise des labels synthétiques. En production, il faudrait des annotations d'experts ou du feedback utilisateur |
| Interface utilisateur web | ✅ Implémenté | [`server.py`](server.py) (API Flask) + [`web/`](web/) (HTML/CSS/JS Leaflet.js) — carte interactive avec sélection de points et affichage de 4 profils |
| API REST | ✅ Implémenté | `POST /api/route` dans [`server.py`](server.py) — reçoit coordonnées, retourne JSON avec 4 itinéraires |
| Tests unitaires formels | ⚠️ Script ad hoc | `test_routing.py` et `deep_scan.py` font des vérifications mais ce ne sont pas des tests pytest structurés |

---

## PHASE 6 : INTERFACE WEB — "Carte interactive en temps réel"

### Étape 12 — API REST Flask ✅

**Code responsable :**

| Fichier | Fonction / Lignes | Rôle |
|---------|-------------------|------|
| [`server.py`](server.py) | `init_engine()` | Précharge graphe + DataFrame + scored_graph au démarrage (une seule fois) |
| [`server.py`](server.py) | `api_route()` — `POST /api/route` | Reçoit `{start_lat, start_lon, end_lat, end_lon}`, calcule 4 profils via `get_best_route()`, retourne JSON avec coordonnées + stats |
| [`server.py`](server.py) | `api_profiles()` — `GET /api/profiles` | Retourne les métadonnées des profils (label, description, couleur, icône) |

### Étape 13 — Frontend Leaflet.js interactif ✅

**Code responsable :**

| Fichier | Rôle |
|---------|------|
| [`web/index.html`](web/index.html) | Page HTML : carte plein écran + panneau latéral avec étapes, résultats, légende |
| [`web/style.css`](web/style.css) | Design dark mode premium : glassmorphism, animations, responsive mobile |
| [`web/app.js`](web/app.js) | Logique : clic carte → marqueurs → appel API → affichage 4 routes colorées + stats |

**Librairies utilisées :**
- **Leaflet.js** (CDN) — carte interactive
- **Google Fonts Inter** — typographie premium

**Fonctionnalités :**
- Sélection de points par clic (départ = 1er clic, arrivée = 2e clic)
- Indicateur d'étapes (1. Départ → 2. Arrivée → 3. Résultats)
- 4 routes affichées simultanément avec couleurs/styles distincts
- Clic sur une carte de profil = mise en surbrillance de la route
- Toggle visibilité par route (œil)
- Badge "★ Plus calme" sur le meilleur score
- Bouton reset pour recommencer
- Responsive (mobile : carte en haut, panneau en bas)

**Lancement :** `python server.py` → ouvrir `http://localhost:5000`

