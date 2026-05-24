# NeuroRoute Calme

Extraction de features par segment piéton + simulation de données manquantes pour Casablanca.

## Ce que ça fait

Un seul script (`main.py`) qui :

1. **Récupère** le graphe piéton de Casablanca depuis OpenStreetMap (via OSMnx)
2. **Extrait** pour chaque route :
   - `longueur` — longueur du segment (mètres)
   - `type_route` — type de route (highway OSM)
   - `verdure` — présence de verdure à proximité (0-1)
   - `proximite_principales` — proximité aux routes principales (0-1)
3. **Simule** les données manquantes :
   - `bruit` — niveau de bruit basé sur le type de route (0-1)
   - `densite` — densité piétonne basée sur la distance au centre-ville (0-1)
4. **Exporte** un DataFrame propre → CSV

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Output

Le fichier `outputs/routes_casablanca.csv` contient :

| Colonne | Type | Description |
|---------|------|-------------|
| `segment_id` | str | Identifiant unique (u_v_key) |
| `u` | int | Noeud de départ |
| `v` | int | Noeud d'arrivée |
| `longueur` | float | Longueur en mètres |
| `type_route` | str | Type de route (footway, residential, etc.) |
| `verdure` | float | Score de verdure 0-1 |
| `proximite_principales` | float | Proximité routes principales 0-1 |
| `bruit` | float | Bruit simulé 0-1 |
| `densite` | float | Densité simulée 0-1 |

## Options

```powershell
python main.py --help
python main.py --no-verdure-query   # utiliser heuristique au lieu de requête spatiale
python main.py --seed 123           # changer la graine aléatoire
```

## Structure

```
NeuroRouteCalme/
├── main.py             ← Pipeline unique
├── guidance.md         ← Contexte du projet
├── requirements.txt
├── pyproject.toml
├── outputs/            ← CSV de sortie
├── cache/              ← Cache HTTP OSMnx (évite re-téléchargement)
└── archive/            ← Ancien code (pour référence)
```

## Notes

- Le cache OSMnx est réutilisé automatiquement (pas besoin de re-télécharger le graphe)
- Installer `pyarrow` pour avoir aussi une sortie Parquet en plus du CSV
- L'ancien code (scan, scoring, visualisation) est dans `archive/` pour référence
