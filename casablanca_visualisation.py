from pathlib import Path
import re
import argparse
import webbrowser
import sys

import osmnx as ox
import matplotlib.pyplot as plt


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def graphml_path(place_name: str = 'Casablanca, Morocco', output_dir: str = 'outputs') -> Path:
    place_slug = slugify(place_name)
    return Path(output_dir) / place_slug / 'raw' / f'{place_slug}_walk.graphml'


def load_graph(path: Path):
    return ox.load_graphml(path)


def plot_graph_matplotlib(G, node_size: float = 5, figsize: float = 10, show: bool = True, save_path: str | None = None):
    fig, ax = ox.plot_graph(G, node_size=node_size, figsize=(figsize, figsize))
    if save_path:
        fig.savefig(save_path)
    if show:
        plt.show()
    return fig, ax


def plot_graph_folium(G, color: str = '#333333', weight: float = 2, save_path: str | None = None, open_in_browser: bool = True):
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
        edges_gdf = ox.graph_to_gdfs(G, nodes=False, edges=True, fill_edge_geometry=True)
        if edges_gdf.crs is not None:
            try:
                edges_gdf = edges_gdf.to_crs(epsg=4326)
            except Exception:
                pass
        minx, miny, maxx, maxy = edges_gdf.total_bounds
        center = [(miny + maxy) / 2, (minx + maxx) / 2]
        m = folium.Map(location=center, zoom_start=13, tiles='cartodbpositron')
        folium.GeoJson(
            edges_gdf.__geo_interface__,
            style_function=lambda _feature: {'color': color, 'weight': weight},
        ).add_to(m)
    else:
        m = plot_graph_folium_fn(G, color=color, weight=weight)

    if save_path is None:
        # default path: outputs/<slug>/preview/<slug>_walk_map.html
        # try to infer slug from G.graph if available
        slug = G.graph.get('name') or 'graph'
        save_path = Path('outputs') / slugify(slug) / 'preview' / f'{slugify(slug)}_walk_map.html'

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(save_path))
    if open_in_browser:
        webbrowser.open(save_path.resolve().as_uri())
    return m, save_path


def main(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description='Visualise Casablanca pedestrian graph (matplotlib + folium)')
    p.add_argument('--output-dir', default='outputs', help='Root outputs folder')
    p.add_argument('--place-name', default='Casablanca, Morocco')
    p.add_argument('--matplotlib', action='store_true', help='Show static matplotlib plot')
    p.add_argument('--folium', action='store_true', help='Create folium interactive map (saves HTML)')
    p.add_argument('--node-size', type=float, default=5.0)
    p.add_argument('--figsize', type=float, default=10.0)
    p.add_argument('--color', default='#333333', help='Color for folium lines')
    p.add_argument('--weight', type=float, default=2.0, help='Line weight for folium')
    p.add_argument('--save-matplotlib', default=None, help='File path to save matplotlib figure (PNG)')
    p.add_argument('--save-folium', default=None, help='File path to save folium HTML')
    p.add_argument('--no-show', action='store_true', help="Don't call plt.show() for matplotlib")
    p.add_argument('--no-open', action='store_true', help="Don't open folium HTML automatically in browser")

    args = p.parse_args(argv)

    gpath = graphml_path(args.place_name, args.output_dir)
    if not gpath.exists():
        print(f'Graph file not found: {gpath}')
        print('Run the export script first: casablanca_pedestrian_graph_export.py')
        sys.exit(1)

    G = load_graph(gpath)

    if args.matplotlib:
        plot_graph_matplotlib(G, node_size=args.node_size, figsize=args.figsize, show=not args.no_show, save_path=args.save_matplotlib)

    if args.folium:
        try:
            m, saved = plot_graph_folium(G, color=args.color, weight=args.weight, save_path=args.save_folium, open_in_browser=not args.no_open)
            print('Folium map saved to', saved)
        except Exception as e:
            print('Failed to create folium map:', e)


if __name__ == '__main__':
    main()


# run with matplotlib
# python casablanca_visualisation.py --matplotlib
# run with folium
# python casablanca_visualisation.py --folium
