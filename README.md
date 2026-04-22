# NeuroRoute Calme

This repository exports and visualizes a pedestrian graph for Casablanca using OSMnx.

## Quick Start

1. Create and activate a virtual environment.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```powershell
pip install -r requirements.txt
```

3. Run the full pipeline (export + visualization).

```powershell
python main.py all --folium
```

This command will:
- fetch and build the walk graph from OpenStreetMap
- export GraphML, GeoJSON, CSV previews, and a manifest
- generate an interactive HTML map in the preview folder

## Main Commands

Run export only:

```powershell
python main.py export
```

Run visualization only (requires existing export):

```powershell
python main.py visualize --folium
```

Run both export and visualization:

```powershell
python main.py all --folium
```

## Optional Installed CLI

You can install this project in editable mode and use the script entrypoint:

```powershell
pip install -e .
neuroroute all --folium
```

## Output Structure

```text
outputs/<place_slug>/
  raw/
  preview/
  table/
  meta/

cache/
  osmnx_http/
```

## Notes

- Default place: Casablanca, Morocco
- Default network type: walk
- To avoid opening browser windows automatically, add: --no-open
- To disable matplotlib windows, add: --no-show
