import argparse
import sys

from casablanca_pedestrian_graph_export import DEFAULT_PLACE_NAME, build_walk_graph
from casablanca_visualisation import run_visualization


def add_common_graph_args(parser: argparse.ArgumentParser):
    parser.add_argument('--place-name', default=DEFAULT_PLACE_NAME, help='OSM place query')
    parser.add_argument('--output-dir', default='outputs', help='Root outputs folder')
    parser.add_argument('--network-type', default='walk', help='OSMnx network type')


def add_export_args(parser: argparse.ArgumentParser):
    parser.add_argument('--cache-dir', default='cache', help='Root cache folder')
    parser.add_argument('--retain-all', action='store_true', default=True)
    parser.add_argument('--no-retain-all', action='store_false', dest='retain_all')
    parser.add_argument('--simplify', action='store_true', default=True)
    parser.add_argument('--no-simplify', action='store_false', dest='simplify')
    parser.add_argument('--geojson-preview-rows', type=int, default=300)
    parser.add_argument('--nodes-csv-rows', type=int, default=2000)
    parser.add_argument('--edges-csv-rows', type=int, default=5000)


def add_visualize_args(parser: argparse.ArgumentParser):
    parser.add_argument('--matplotlib', action='store_true', help='Create matplotlib figure')
    parser.add_argument('--folium', action='store_true', help='Create folium HTML map')
    parser.add_argument('--node-size', type=float, default=5.0)
    parser.add_argument('--figsize', type=float, default=10.0)
    parser.add_argument('--color', default='#333333', help='Color for folium segments')
    parser.add_argument('--weight', type=float, default=2.0, help='Line width for folium segments')
    parser.add_argument('--save-matplotlib', default=None, help='File path for matplotlib PNG')
    parser.add_argument('--save-folium', default=None, help='File path for folium HTML')
    parser.add_argument('--no-show', action='store_true', help='Do not open matplotlib window')
    parser.add_argument('--no-open', action='store_true', help='Do not open folium in browser')


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description='NeuroRoute Calme pipeline runner')
    subparsers = parser.add_subparsers(dest='command', required=True)

    export_cmd = subparsers.add_parser('export', help='Fetch and export graph data')
    add_common_graph_args(export_cmd)
    add_export_args(export_cmd)

    visualize_cmd = subparsers.add_parser('visualize', help='Visualize exported graph')
    add_common_graph_args(visualize_cmd)
    add_visualize_args(visualize_cmd)

    all_cmd = subparsers.add_parser('all', help='Run export then visualize')
    add_common_graph_args(all_cmd)
    add_export_args(all_cmd)
    add_visualize_args(all_cmd)

    return parser.parse_args(argv)


def run_export(args):
    return build_walk_graph(
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


def run_visualize(args):
    folium_enabled = args.folium or not args.matplotlib
    return run_visualization(
        place_name=args.place_name,
        output_dir=args.output_dir,
        network_type=args.network_type,
        matplotlib_enabled=args.matplotlib,
        folium_enabled=folium_enabled,
        node_size=args.node_size,
        figsize=args.figsize,
        color=args.color,
        weight=args.weight,
        save_matplotlib=args.save_matplotlib,
        save_folium=args.save_folium,
        show_matplotlib=not args.no_show,
        open_folium=not args.no_open,
    )


def main(argv: list[str] | None = None):
    args = parse_args(argv)

    try:
        if args.command == 'export':
            run_export(args)
            return 0

        if args.command == 'visualize':
            result = run_visualize(args)
            if result.get('folium_path'):
                print('Folium map saved to', result['folium_path'])
            return 0

        if args.command == 'all':
            run_export(args)
            result = run_visualize(args)
            if result.get('folium_path'):
                print('Folium map saved to', result['folium_path'])
            return 0

        print(f'Unsupported command: {args.command}')
        return 2
    except Exception as exc:
        print('Pipeline failed:', exc)
        return 1


if __name__ == '__main__':
    sys.exit(main())
