from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import re

import osmnx as ox


DEFAULT_PLACE_NAME = 'Casablanca, Morocco'


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def write_pretty_geojson_preview(gdf, path: Path, n_rows: int = 200):
    # Human-readable preview only, not the full heavy dataset.
    preview = gdf.head(n_rows)
    data = json.loads(preview.to_json(drop_id=False))
    with path.open('w', encoding='utf-8') as file_handle:
        json.dump(data, file_handle, ensure_ascii=False, indent=2)


def build_walk_graph(
    place_name: str = DEFAULT_PLACE_NAME,
    output_dir: str = 'outputs',
    cache_dir: str = 'cache',
    network_type: str = 'walk',
    retain_all: bool = True,
    simplify: bool = True,
    geojson_preview_rows: int = 300,
    nodes_csv_rows: int = 2000,
    edges_csv_rows: int = 5000,
):
    place_slug = slugify(place_name)

    root = Path(output_dir) / place_slug
    raw_dir = root / 'raw'
    preview_dir = root / 'preview'
    meta_dir = root / 'meta'
    table_dir = root / 'table'

    for directory in (raw_dir, preview_dir, meta_dir, table_dir):
        directory.mkdir(parents=True, exist_ok=True)

    # Keep OSMnx HTTP cache in a stable explicit location.
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(Path(cache_dir) / 'osmnx_http')
    ox.settings.log_console = True

    graph = ox.graph_from_place(
        place_name,
        network_type=network_type,
        retain_all=retain_all,
        simplify=simplify,
    )

    graphml_file = raw_dir / f'{place_slug}_{network_type}.graphml'
    ox.save_graphml(graph, graphml_file)

    nodes_gdf, edges_gdf = ox.graph_to_gdfs(graph)

    nodes_geojson = raw_dir / f'{place_slug}_{network_type}_nodes.geojson'
    edges_geojson = raw_dir / f'{place_slug}_{network_type}_edges.geojson'
    nodes_gdf.to_file(nodes_geojson, driver='GeoJSON')
    edges_gdf.to_file(edges_geojson, driver='GeoJSON')

    nodes_preview_geojson = preview_dir / 'nodes_preview_pretty.geojson'
    edges_preview_geojson = preview_dir / 'edges_preview_pretty.geojson'
    write_pretty_geojson_preview(nodes_gdf, nodes_preview_geojson, n_rows=geojson_preview_rows)
    write_pretty_geojson_preview(edges_gdf, edges_preview_geojson, n_rows=geojson_preview_rows)

    nodes_cols = [c for c in ['osmid', 'y', 'x', 'street_count', 'highway'] if c in nodes_gdf.columns]
    edges_cols = [c for c in ['u', 'v', 'key', 'osmid', 'highway', 'maxspeed', 'lanes', 'length', 'name'] if c in edges_gdf.columns]

    nodes_csv = table_dir / 'nodes_preview.csv'
    edges_csv = table_dir / 'edges_preview.csv'
    nodes_gdf[nodes_cols].head(nodes_csv_rows).to_csv(nodes_csv, index=False)
    edges_gdf[edges_cols].head(edges_csv_rows).to_csv(edges_csv, index=False)

    manifest = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'place_name': place_name,
        'network_type': network_type,
        'retain_all': retain_all,
        'simplify': simplify,
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
            'nodes_preview_geojson': str(nodes_preview_geojson),
            'edges_preview_geojson': str(edges_preview_geojson),
            'nodes_preview_csv': str(nodes_csv),
            'edges_preview_csv': str(edges_csv),
        },
        'cache_folder': str(Path(cache_dir) / 'osmnx_http'),
    }

    manifest_path = meta_dir / 'run_manifest.json'
    with manifest_path.open('w', encoding='utf-8') as file_handle:
        json.dump(manifest, file_handle, ensure_ascii=False, indent=2)

    print('Pedestrian graph generated successfully')
    print(f'Place: {place_name}')
    print(f'Nodes: {len(nodes_gdf):,}')
    print(f'Edges: {len(edges_gdf):,}')
    print(f'Raw graph: {graphml_file}')
    print('Metadata:', manifest_path)

    return manifest


def build_casablanca_walk_graph(output_dir: str = 'outputs', cache_dir: str = 'cache'):
    return build_walk_graph(place_name=DEFAULT_PLACE_NAME, output_dir=output_dir, cache_dir=cache_dir)


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description='Export an OSMnx graph and data previews')
    parser.add_argument('--place-name', default=DEFAULT_PLACE_NAME, help='OSM place query')
    parser.add_argument('--output-dir', default='outputs', help='Root output folder')
    parser.add_argument('--cache-dir', default='cache', help='Root cache folder')
    parser.add_argument('--network-type', default='walk', help='OSMnx network type')
    parser.add_argument('--retain-all', action='store_true', default=True, help='Keep disconnected components')
    parser.add_argument('--no-retain-all', action='store_false', dest='retain_all', help='Drop disconnected components')
    parser.add_argument('--simplify', action='store_true', default=True, help='Simplify graph topology')
    parser.add_argument('--no-simplify', action='store_false', dest='simplify', help='Disable graph simplification')
    parser.add_argument('--geojson-preview-rows', type=int, default=300)
    parser.add_argument('--nodes-csv-rows', type=int, default=2000)
    parser.add_argument('--edges-csv-rows', type=int, default=5000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    build_walk_graph(
        place_name=args.place_name,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        network_type=args.network_type,
        retain_all=args.retain_all,
        simplify=args.simplify,
        geojson_preview_rows=args.geojson_preview_rows,
        nodes_csv_rows=args.nodes_csv_rows,
        edges_csv_rows=args.edges_csv_rows,
    )


if __name__ == '__main__':
    main()