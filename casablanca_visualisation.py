from pathlib import Path
import argparse
import re
import sys
import webbrowser

import matplotlib.pyplot as plt
import osmnx as ox


DEFAULT_PLACE_NAME = 'Casablanca, Morocco'


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def graphml_path(
    place_name: str = DEFAULT_PLACE_NAME,
    output_dir: str = 'outputs',
    network_type: str = 'walk',
) -> Path:
    place_slug = slugify(place_name)
    return Path(output_dir) / place_slug / 'raw' / f'{place_slug}_{network_type}.graphml'


def default_folium_path(
    place_name: str = DEFAULT_PLACE_NAME,
    output_dir: str = 'outputs',
    network_type: str = 'walk',
) -> Path:
    place_slug = slugify(place_name)
    return Path(output_dir) / place_slug / 'preview' / f'{place_slug}_{network_type}_map.html'


def load_graph(path: Path):
    return ox.load_graphml(path)


def plot_graph_matplotlib(
    graph,
    node_size: float = 5,
    figsize: float = 10,
    show: bool = True,
    save_path: str | None = None,
):
    fig, ax = ox.plot_graph(graph, node_size=node_size, figsize=(figsize, figsize))
    if save_path:
        fig.savefig(save_path)
    if show:
        plt.show()
    return fig, ax


def plot_graph_folium(
    graph,
    color: str = '#333333',
    weight: float = 2,
    save_path: str | Path | None = None,
    open_in_browser: bool = True,
):
    try:
        import folium  # noqa: F401
    except ImportError as exc:
        raise ImportError('Folium is required for folium output: pip install folium') from exc

    plot_graph_folium_fn = getattr(ox, 'plot_graph_folium', None)
    if plot_graph_folium_fn is None:
        try:
            from osmnx import plot as ox_plot

            plot_graph_folium_fn = getattr(ox_plot, 'plot_graph_folium', None)
        except Exception:
            plot_graph_folium_fn = None

    if plot_graph_folium_fn is None:
        edges_gdf = ox.graph_to_gdfs(graph, nodes=False, edges=True, fill_edge_geometry=True)
        if edges_gdf.crs is not None:
            try:
                edges_gdf = edges_gdf.to_crs(epsg=4326)
            except Exception:
                pass
        minx, miny, maxx, maxy = edges_gdf.total_bounds
        center = [(miny + maxy) / 2, (minx + maxx) / 2]
        map_obj = folium.Map(location=center, zoom_start=13, tiles='cartodbpositron')
        folium.GeoJson(
            edges_gdf.__geo_interface__,
            style_function=lambda _feature: {'color': color, 'weight': weight},
        ).add_to(map_obj)
    else:
        map_obj = plot_graph_folium_fn(graph, color=color, weight=weight)

    if save_path is None:
        save_path = Path('outputs') / 'preview' / 'graph_map.html'

    output_path = Path(save_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    map_obj.save(str(output_path))

    if open_in_browser:
        webbrowser.open(output_path.resolve().as_uri())

    return map_obj, output_path


def run_visualization(
    place_name: str = DEFAULT_PLACE_NAME,
    output_dir: str = 'outputs',
    network_type: str = 'walk',
    matplotlib_enabled: bool = False,
    folium_enabled: bool = True,
    node_size: float = 5.0,
    figsize: float = 10.0,
    color: str = '#333333',
    weight: float = 2.0,
    save_matplotlib: str | None = None,
    save_folium: str | None = None,
    show_matplotlib: bool = True,
    open_folium: bool = True,
):
    graph_path = graphml_path(place_name=place_name, output_dir=output_dir, network_type=network_type)
    if not graph_path.exists():
        raise FileNotFoundError(f'Graph file not found: {graph_path}')

    graph = load_graph(graph_path)
    result = {'graph_path': str(graph_path), 'folium_path': None, 'matplotlib_path': save_matplotlib}

    if matplotlib_enabled:
        plot_graph_matplotlib(
            graph,
            node_size=node_size,
            figsize=figsize,
            show=show_matplotlib,
            save_path=save_matplotlib,
        )

    if folium_enabled:
        folium_path = save_folium or default_folium_path(
            place_name=place_name,
            output_dir=output_dir,
            network_type=network_type,
        )
        _, saved_path = plot_graph_folium(
            graph,
            color=color,
            weight=weight,
            save_path=folium_path,
            open_in_browser=open_folium,
        )
        result['folium_path'] = str(saved_path)

    return result


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description='Visualize exported pedestrian graph data')
    parser.add_argument('--output-dir', default='outputs', help='Root outputs folder')
    parser.add_argument('--place-name', default=DEFAULT_PLACE_NAME)
    parser.add_argument('--network-type', default='walk', help='Network type suffix in exported files')
    parser.add_argument('--matplotlib', action='store_true', help='Show static matplotlib plot')
    parser.add_argument('--folium', action='store_true', help='Create folium interactive map (saves HTML)')
    parser.add_argument('--node-size', type=float, default=5.0)
    parser.add_argument('--figsize', type=float, default=10.0)
    parser.add_argument('--color', default='#333333', help='Color for folium lines')
    parser.add_argument('--weight', type=float, default=2.0, help='Line weight for folium')
    parser.add_argument('--save-matplotlib', default=None, help='File path to save matplotlib figure (PNG)')
    parser.add_argument('--save-folium', default=None, help='File path to save folium HTML')
    parser.add_argument('--no-show', action='store_true', help='Do not call plt.show() for matplotlib')
    parser.add_argument('--no-open', action='store_true', help='Do not open folium HTML in browser')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    folium_enabled = args.folium or not args.matplotlib

    try:
        result = run_visualization(
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
        if result['folium_path']:
            print('Folium map saved to', result['folium_path'])
    except FileNotFoundError as exc:
        print(exc)
        print('Run export first: python casablanca_pedestrian_graph_export.py')
        sys.exit(1)
    except Exception as exc:
        print('Failed to create visualization:', exc)
        sys.exit(1)


if __name__ == '__main__':
    main()
