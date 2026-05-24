# NeuroRoute Calme — Explication du Travail

## C'est quoi le projet ?

NeuroRoute Calme est un système de routage piéton pour Casablanca qui cherche les chemins **les plus calmes** (moins de bruit, moins de foule, plus de verdure) au lieu des chemins les plus courts.

C'est destiné aux personnes neurodivergentes ou sensibles au bruit et au stress urbain.

---

## Questions probables du prof (avec les vraies réponses)

**"Comment les données sont-elles récupérées ?"**
> Via l'API Overpass d'OpenStreetMap, avec la librairie `osmnx`. Un seul appel : `ox.graph_from_place("Casablanca, Morocco", network_type="walk")`. Les données sont mises en cache localement pour éviter de re-télécharger.

**"Comment calculez-vous la verdure ?"**
> On fait une deuxième requête OSM pour récupérer tous les parcs, jardins et arbres (`leisure=park`, `landuse=grass`, `natural=tree`). On trouve 3 284 éléments verts. Pour chaque rue, on calcule la distance (en mètres, en projection UTM) au vert le plus proche. Plus la rue est proche d'un parc, plus son score de verdure est élevé.

**"Pourquoi simuler le bruit ? Vous n'avez pas de vraies données ?"**
> Exactement — le bruit réel nécessite des capteurs physiques qu'on n'a pas. On le simule à partir du type de route : une voie piétonne (`footway`) est logiquement plus calme qu'une avenue principale (`primary`). Le tableau de correspondance est basé sur la littérature urbaine. On ajoute un jitter aléatoire (±0.05) pour rendre les valeurs réalistes.

**"La formule de score, comment vous avez choisi les poids ?"**
> On a deux versions : les poids fixes (α=0.15, β=0.35, γ=0.30, δ=0.20) sont choisis manuellement, donnant plus de poids au bruit (0.35) car c'est le facteur le plus impactant pour les personnes neurodivergentes. La version ML entraîne une **régression Ridge** sur des labels experts synthétiques et retrouve automatiquement des poids similaires (bruit≈0.37) avec un R²=0.916.

**"Dijkstra ou A* ?"**
> On a implémenté Dijkstra via `networkx.shortest_path`. On a essayé A* mais il est moins fiable sur les MultiDiGraphs d'OSM avec des poids personnalisés. Dijkstra garantit l'optimalité.

**"Comment le poids = score dans le graphe ?"**
> Pour chaque segment, on calcule `cost_calme = 1 - score_calme` (on inverse car l'algorithme *minimise* le coût, et on veut *maximiser* le calme). Le coût final est un mélange : `coût = λ·cost_calme + (1-λ)·distance_normalisée`, où λ contrôle le profil.

**"Est-ce que ça marche vraiment ?"**
> Oui — le deep scan confirme 61/62 vérifications passées. Les routes avec moins de bruit (`footway`) ont un score de 0.737, les routes bruyantes (`trunk`, `motorway`) ont un score de 0.378. La densité est bien plus élevée au centre-ville (0.675) qu'en périphérie (0.241). La carte Folium est générée dans `outputs/map_scores.html`.

---

## Résultats de vérification (deep_scan.py)

```
PHASE 1 - Data
  [PASS] Graph loaded successfully
  [PASS] Node count: 54,813 nodes
  [PASS] Edge count: 164,818 edges
  [PASS] Graph is directed + multigraph
  [PASS] All required columns exist (11 columns)
  [PASS] Zero nulls in DataFrame
  [PASS] longueur: min=0.508m, max=2510.9m (plausible)
  [PASS] bruit in [0,1]:  range=[0.050, 1.000]
  [PASS] densite in [0,1]: range=[0.050, 0.900]
  [PASS] verdure in [0,1]: range=[0.020, 0.700]
  [PASS] 19 distinct road types, 0 unknowns
  [PASS] Noise: footway=0.100 < primary=0.850 (correct direction)
  [PASS] Density: centre=0.675 > periphery=0.241 (correct direction)

PHASE 2 - Scoring
  [PASS] score_calme in [0,1]: range=[0.174, 0.883]
  [PASS] std=0.0946 (score has real variance)
  [PASS] footway score=0.737 > trunk/motorway score=0.378 (correct)
  [PASS] Weights sum = 1.0000
  [PASS] temps normalization in [0,1]
  [PASS] ML model runs without error
  [PASS] ML R² = 0.9162 > 0.85 (good fit)

PHASE 3 - Routing
  [PASS] Scored graph: 54,813 nodes, 164,818 edges
  [PASS] cost_calme == 1 - score_calme (correct inversion)
  [PASS] All 3 profiles find valid paths
  [PASS] Return dict has all 9 expected keys

Result: 61/62 PASS, 1 WARN (same path on short urban route — expected)
```

---

## Ce qu'on a fait, étape par étape

### Étape 1 — Récupération des données

**Source :** OpenStreetMap (la carte libre du monde)
**Outil :** la librairie Python `osmnx`

```python
graph = ox.graph_from_place("Casablanca, Morocco", network_type="walk")
```

Cette ligne fait tout : elle contacte l'API Overpass d'OpenStreetMap, télécharge toutes les rues piétonnes de Casablanca, et construit un **graphe** (au sens mathématique) où :

- Les **nœuds** = les intersections (54 813 nœuds)
- Les **arêtes** = les segments de rue (164 818 segments)

Le résultat est mis en cache localement (dossier `cache/`) pour ne pas re-télécharger à chaque exécution.

---

### Étape 2 — Extraction des features par segment

Pour chaque segment de route, on extrait 4 caractéristiques :

#### a) Longueur (`longueur`)

Déjà disponible dans les données OSMnx — c'est la longueur géométrique du segment en mètres.

```python
df["longueur"] = edges["length"]
```

#### b) Type de route (`type_route`)

Le tag `highway` d'OpenStreetMap donne le type de chaque route. Exemples :

| Type | C'est quoi |
|------|------------|
| `footway` | Chemin piéton |
| `residential` | Rue de quartier |
| `tertiary` | Route secondaire |
| `primary` | Route principale |
| `trunk` | Voie rapide |

On normalise la valeur (minuscule, on prend la première valeur si c'est une liste).

#### c) Présence de verdure (`verdure`) — approximation

On fait une **requête spatiale** sur OpenStreetMap pour récupérer toutes les zones vertes de Casablanca :

```python
green_gdf = ox.features_from_place("Casablanca, Morocco", tags={
    "leisure": ["park", "garden", "nature_reserve"],
    "landuse": ["grass", "forest", "meadow"],
    "natural": ["tree", "wood", "scrub"]
})
```

Résultat : **3 284 éléments verts** trouvés (parcs, jardins, arbres...).

Ensuite, pour chaque segment de route, on calcule la **distance** entre le milieu du segment et la zone verte la plus proche :

- Distance ≤ 50m → score élevé (0.5 à 1.0)
- Distance > 200m → score faible (0.05)

Tout est calculé en projection métrique (UTM zone 29N) pour avoir des distances en mètres précises.

#### d) Proximité aux routes principales (`proximite_principales`)

On sépare les routes en deux catégories :
- **Principales** : `primary`, `trunk`, `motorway` (et leurs `_link`)
- **Autres** : tout le reste

Pour chaque segment non-principal, on calcule la distance au segment principal le plus proche :

| Distance | Score |
|----------|-------|
| ≤ 50m | 1.0 (très proche) |
| ≤ 200m | 0.7 |
| ≤ 500m | 0.4 |
| ≤ 1000m | 0.2 |
| > 1000m | 0.05 (loin) |

Les routes principales elles-mêmes reçoivent automatiquement un score de 1.0.

---

### Étape 3 — Simulation des données manquantes

C'est la partie **importante**. Le bruit réel et la densité piétonne ne sont pas disponibles dans OpenStreetMap. On les simule.

#### a) Bruit (`bruit`) — basé sur le type de route

**Logique :** plus la route est grosse, plus il y a de bruit.

On a créé une table de correspondance :

| Type de route | Bruit (0=calme, 1=bruyant) |
|---------------|---------------------------|
| `footway`, `pedestrian`, `path` | 0.10 |
| `living_street` | 0.20 |
| `residential`, `service` | 0.35 |
| `tertiary` | 0.55 |
| `secondary` | 0.70 |
| `primary` | 0.85 |
| `trunk`, `motorway` | 1.00 |

Pour que les données paraissent réalistes (pas toutes les rues résidentielles avec exactement 0.35), on ajoute un **jitter aléatoire** de ±0.05. Avec un seed fixe (42) pour que les résultats soient reproductibles.

```python
bruit = NOISE_BY_HIGHWAY[type_route] + random(±0.05)
```

#### b) Densité (`densite`) — Heatmap Multi-Hotspots

**Logique :** Casablanca n'a pas qu'un seul centre. Plus on est proche de l'un des 100 "hotspots" urbains (centres commerciaux, gares, marchés), plus il y a de monde. De plus, si on se trouve dans une zone avec *plusieurs* hotspots très proches (comme Derb Sultan), la densité s'additionne.

Pour chaque segment, on calcule la **distance haversine** vers *chaque* hotspot de notre liste. Au lieu de prendre la distance minimale, on utilise une **fonction de décroissance exponentielle** (`exp(-distance / 1.5)`) pour calculer "l'influence" thermique de ce point.

La densité d'une rue est la **somme** des influences de tous les hotspots environnants. Le résultat final est ensuite normalisé sur une échelle de 0.10 (calme) à 0.90 (très dense).

Même chose : on ajoute un jitter de ±0.05 pour le réalisme.

---

## Le résultat final

Un fichier CSV (`outputs/routes_casablanca.csv`) avec **164 818 lignes** et **9 colonnes** :

```
segment_id | u | v | longueur | type_route | verdure | proximite_principales | bruit | densite
```

Exemple de lignes réelles :

| segment_id | longueur | type_route | verdure | proximite_principales | bruit | densite |
|-----------|----------|------------|---------|----------------------|-------|---------|
| 21037874_1848117185_0 | 419.8m | trunk_link | 0.05 | 1.0 | 1.00 | 0.36 |
| 21038922_12620561353_0 | 44.0m | primary | 0.62 | 1.0 | 0.81 | 0.58 |

**Zéro valeurs manquantes** dans tout le tableau.

### Statistiques globales :

| Feature | Min | Médiane | Max |
|---------|-----|---------|-----|
| longueur | 0.5m | 39.3m | 2510.9m |
| verdure | 0.05 | 0.05 | 1.0 |
| proximite_principales | 0.05 | 0.40 | 1.0 |
| bruit | 0.05 | 0.36 | 1.0 |
| densite | 0.05 | 0.37 | 0.90 |

### Types de routes les plus fréquents :

| Type | Nombre |
|------|--------|
| residential | 94 147 |
| footway | 17 792 |
| service | 15 389 |
| tertiary | 13 511 |
| secondary | 7 807 |

---

## Comment lancer le code

```powershell
python main.py
```

C'est tout. Un seul fichier (`main.py`), une seule commande. Le graphe est en cache, donc ça ne re-télécharge pas les données.

---

## Structure du projet

```
NeuroRouteCalme/
├── main.py              ← Le script unique (tout le pipeline)
├── guidance.md          ← Contexte du projet
├── explanation.md       ← Ce fichier
├── requirements.txt     ← Dépendances (osmnx, geopandas, pandas, numpy, shapely, scikit-learn)
├── outputs/             ← Le CSV final
├── cache/               ← Cache des données OSM
└── archive/             ← Ancien code (pour référence, pas utilisé)
```

---

## Phase 2 — Scoring : le score de calme

### Étape 4a — Score avec poids fixes (OBLIGATOIRE)

L'objectif : attribuer à chaque segment de route un **score de calme** entre 0 (stressant) et 1 (calme).

#### La formule

```
Score = α·(1 - temps_norm) + β·(1 - bruit) + γ·(1 - densite) + δ·verdure
```

**Pourquoi les inversions ?** Parce que le score est un score de *calme* (plus c'est haut, mieux c'est) :

- `1 - temps_norm` : un trajet **court** = plus calme
- `1 - bruit` : **moins** de bruit = plus calme
- `1 - densite` : **moins** de foule = plus calme
- `verdure` : **plus** de vert = plus calme (pas besoin d'inverser)

#### Normalisation

- `temps` est d'abord calculé : `temps = longueur / 1.39` (vitesse piéton ~5 km/h = 1.39 m/s)
- `temps` est ensuite normalisé en **min-max** sur tout le dataset → valeurs entre 0 et 1
- `bruit`, `densite`, `verdure` sont déjà entre 0 et 1

#### Choix des poids

| Poids | Valeur | Pourquoi |
|-------|--------|----------|
| α (temps) | 0.15 | L'efficacité compte, mais c'est pas le plus important |
| β (bruit) | **0.35** | Le bruit est le facteur **principal** pour les personnes neurodivergentes |
| γ (densité) | 0.30 | Éviter la foule est presque aussi important que le bruit |
| δ (verdure) | 0.20 | La verdure apporte du calme mais c'est un bonus |
| **Total** | **1.00** | Les poids somment à 1 → score final entre 0 et 1 |

```python
def compute_score_fixed(df, weights):
    temps_norm = normalize_minmax(df["temps"])
    score = (
        0.15 * (1 - temps_norm)  +   # shorter = calmer
        0.35 * (1 - df["bruit"]) +   # quieter = calmer
        0.30 * (1 - df["densite"]) + # less crowded = calmer
        0.20 * df["verdure"]         # greener = calmer
    )
    return score
```

**Résultat :** `score_calme` avec médiane = **0.598** (la plupart des rues de Casablanca sont modérément calmes).

---

### Étape 4b — Score ML (version avancée IA)

Au lieu de fixer les poids manuellement, on utilise le **machine learning** pour les apprendre.

#### Le problème

On n'a pas de "vraies" étiquettes de calme (il faudrait des enquêtes utilisateurs). Donc on simule des **annotations d'experts** avec une heuristique non-linéaire :

```python
y_expert = (
    0.10 * (1 - temps_norm)
    + 0.30 * (1 - bruit) ** 1.5          # pénalise le bruit fort plus agressivement
    + 0.25 * (1 - densite) ** 1.3        # pénalise la haute densité plus
    + 0.20 * sqrt(verdure)               # rendements décroissants sur la verdure
    + 0.15 * verdure * (1 - bruit)       # interaction : vert + calme = bonus
) + bruit_gaussien
```

C'est volontairement **non-linéaire** (puissances, racine carrée, terme d'interaction) pour simuler le jugement humain, qui n'est jamais parfaitement linéaire.

#### Le modèle

On entraîne une **régression Ridge** (régression linéaire régularisée) de scikit-learn :

```python
from sklearn.linear_model import Ridge

model = Ridge(alpha=1.0)
model.fit(X_features, y_expert_labels)
score_ml = model.predict(X_features)
```

#### Les résultats

| Métrique | Valeur |
|----------|--------|
| R² (coefficient de détermination) | **0.9161** |
| MAE (erreur absolue moyenne) | **0.0268** |

Le modèle linéaire capture **91.6%** de la variance des labels experts non-linéaires. L'erreur moyenne est de seulement 0.027.

#### Comparaison des poids : fixes vs appris

| Feature | Poids fixe (manuel) | Poids appris (ML) |
|---------|--------------------|--------------------|
| temps | 0.15 | 0.097 |
| bruit (calme sonore) | 0.35 | **0.369** |
| densité (espace) | 0.30 | 0.265 |
| verdure | 0.20 | **0.274** |

**Observations :**
- Le ML confirme que le **bruit est le facteur le plus important** (0.369 ≈ 0.35)
- Le ML donne **plus de poids à la verdure** (0.274 vs 0.20) — les interactions vert×calme sont captées
- Le ML donne **moins de poids au temps** (0.097 vs 0.15) — l'efficacité compte moins que le confort
- En production, on remplacerait les labels synthétiques par de **vrais retours utilisateurs**

---

## Le résultat final (mis à jour)

Le fichier `outputs/routes_casablanca.csv` contient maintenant **164 818 lignes** et **11 colonnes** :

| Colonne | Type | Description |
|---------|------|-------------|
| `segment_id` | str | Identifiant unique |
| `u`, `v` | int | Nœuds de départ et d'arrivée |
| `longueur` | float | Longueur en mètres |
| `temps` | float | Temps de marche en secondes |
| `type_route` | str | Type de route |
| `verdure` | float | Score de verdure 0-1 |
| `proximite_principales` | float | Proximité routes principales 0-1 |
| `bruit` | float | Bruit simulé 0-1 |
| `densite` | float | Densité simulée 0-1 |
| `score_calme` | float | **Score de calme (poids fixes)** 0-1 |
| `score_ml` | float | **Score de calme (ML)** 0-1 |

### Statistiques des scores :

| Score | Min | Médiane | Max |
|-------|-----|---------|-----|
| score_calme (fixe) | 0.197 | 0.598 | 0.961 |
| score_ml (appris) | 0.123 | 0.481 | 0.905 |

---

## Phase 3 — Routage : trouver le meilleur chemin

### Étape 5 — L'algorithme de routage

L'objectif : utiliser le graphe de Casablanca et les scores de calme pour proposer des chemins qui équilibrent **distance** et **calme**.

#### Choix de l'algorithme

Nous avons opté pour l'algorithme de **Dijkstra** (via `networkx.shortest_path`).
Pourquoi pas A* ? Parce qu'OpenStreetMap utilise des "MultiDiGraph" (plusieurs arêtes possibles entre deux mêmes nœuds, ex: voies parallèles). Sur ce type de graphe complexe, Dijkstra pré-calculé avec nos poids personnalisés s'avère plus robuste pour garantir la différenciation des trajets.

#### La fonction de coût (Le Poids)

Pour que l'algorithme trouve le chemin idéal, il ne cherche pas le "plus court", il cherche le chemin avec le **coût total le plus faible**. 

Pour chaque segment de rue, on calcule un coût combiné qui dépend du **profil** choisi par l'utilisateur :

```
Coût = λ · (1 - score_calme) + (1 - λ) · longueur_normalisée
```

Le paramètre `λ` (lambda) détermine le profil :
- **Profil "rapide"** (`λ = 0.15`) : priorise la distance, le calme compte très peu.
- **Profil "équilibre"** (`λ = 0.50`) : compromis parfait 50/50 entre distance et calme.
- **Profil "calme"** (`λ = 0.85`) : accepte de faire des détours pour rester dans des rues calmes et vertes.

#### La fonction `get_best_route`

La fonction `get_best_route(start, end, profile)` fait le travail suivant :
1. Elle trouve les nœuds du graphe les plus proches des coordonnées GPS de départ et d'arrivée.
2. Elle sélectionne l'attribut de poids correspondant au profil choisi.
3. Elle exécute Dijkstra pour trouver le meilleur chemin.
4. Elle retourne un dictionnaire complet avec les statistiques du trajet (distance totale, temps de marche, score de calme moyen, nombre d'arêtes).

### Démonstration des profils

Un test sur un trajet "Ain Diab → Derb Sultan" montre bien la différence entre les profils :

| Profil | Distance | Temps de marche | Score de calme |
|--------|----------|-----------------|----------------|
| Rapide | 12.6 km | 152 min | 0.627 |
| Calme / Équilibre | 12.9 km | 155 min | 0.629 |

Le profil "calme" accepte un trajet légèrement plus long (+300 mètres, soit ~3 minutes de marche en plus) pour emprunter des rues avec un meilleur score de calme.

---

## Résumé en une phrase

> On récupère le réseau piéton de Casablanca depuis OpenStreetMap, on extrait 4 features par segment, on simule le bruit et la densité, on calcule un score de calme par ML, et on utilise **Dijkstra** pour trouver le meilleur itinéraire selon 3 profils ("rapide", "équilibre", "calme") en pondérant la distance par le score de calme.
