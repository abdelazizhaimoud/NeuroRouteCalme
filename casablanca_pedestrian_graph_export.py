# SECTION 1: Casablanca — Export du graphe piétonnier
from pathlib import Path
from datetime import datetime, timezone
import json
import re

import osmnx as ox


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')

def write_pretty_geojson_preview(gdf, path: Path, n_rows: int = 200):
    # Human-readable preview only, not the full heavy dataset
    preview = gdf.head(n_rows)
    data = json.loads(preview.to_json(drop_id=False))
    with path.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def build_casablanca_walk_graph(output_dir: str = 'outputs', cache_dir: str = 'cache'):
    place_name = 'Casablanca, Morocco'
    place_slug = slugify(place_name)

    root = Path(output_dir) / place_slug
    raw_dir = root / 'raw'
    preview_dir = root / 'preview'
    meta_dir = root / 'meta'
    table_dir = root / 'table'

    for d in (raw_dir, preview_dir, meta_dir, table_dir):
        d.mkdir(parents=True, exist_ok=True)

    # OSMnx cache is hash-based and internal by design; keep it in one explicit place
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(Path(cache_dir) / 'osmnx_http')
    ox.settings.log_console = True

    graph = ox.graph_from_place(
        place_name,
        network_type='walk',
        retain_all=True,
        simplify=True,
    )

    # Raw full graph for routing/algorithms
    graphml_file = raw_dir / f'{place_slug}_walk.graphml'
    ox.save_graphml(graph, graphml_file)

    nodes_gdf, edges_gdf = ox.graph_to_gdfs(graph)

    # Raw GIS files
    nodes_geojson = raw_dir / f'{place_slug}_walk_nodes.geojson'
    edges_geojson = raw_dir / f'{place_slug}_walk_edges.geojson'
    nodes_gdf.to_file(nodes_geojson, driver='GeoJSON')
    edges_gdf.to_file(edges_geojson, driver='GeoJSON')

    # Human-readable previews
    write_pretty_geojson_preview(nodes_gdf, preview_dir / 'nodes_preview_pretty.geojson', n_rows=300)
    write_pretty_geojson_preview(edges_gdf, preview_dir / 'edges_preview_pretty.geojson', n_rows=300)

    # Fast readable tables for quick checks
    nodes_cols = [c for c in ['osmid', 'y', 'x', 'street_count', 'highway'] if c in nodes_gdf.columns]
    edges_cols = [c for c in ['u', 'v', 'key', 'osmid', 'highway', 'maxspeed', 'lanes', 'length', 'name'] if c in edges_gdf.columns]

    nodes_gdf[nodes_cols].head(2000).to_csv(table_dir / 'nodes_preview.csv', index=False)
    edges_gdf[edges_cols].head(5000).to_csv(table_dir / 'edges_preview.csv', index=False)

    # Run metadata (human-readable)
    manifest = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'place_name': place_name,
        'network_type': 'walk',
        'retain_all': True,
        'simplify': True,
        'counts': {
            'nodes': int(len(nodes_gdf)),
            'edges': int(len(edges_gdf)),
        },
        'crs': str(nodes_gdf.crs),
        'node_columns': [str(c) for c in nodes_gdf.columns],
        'edge_columns': [str(c) for c in edges_gdf.columns],
        'files': {
            'graphml': str(graphml_file),
            'nodes_geojson': str(nodes_geojson),
            'edges_geojson': str(edges_geojson),
            'nodes_preview_geojson': str(preview_dir / 'nodes_preview_pretty.geojson'),
            'edges_preview_geojson': str(preview_dir / 'edges_preview_pretty.geojson'),
            'nodes_preview_csv': str(table_dir / 'nodes_preview.csv'),
            'edges_preview_csv': str(table_dir / 'edges_preview.csv'),
        },
        'cache_folder': str(Path(cache_dir) / 'osmnx_http'),
    }

    with (meta_dir / 'run_manifest.json').open('w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print('Pedestrian graph generated successfully')
    print(f'Place: {place_name}')
    print(f'Nodes: {len(nodes_gdf):,}')
    print(f'Edges: {len(edges_gdf):,}')
    print(f'Raw graph: {graphml_file}')
    print('Metadata:', meta_dir / 'run_manifest.json')

build_casablanca_walk_graph()