import json

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import pyproj
from shapely.geometry import LineString, MultiLineString
from shapely.ops import transform


class RoadMap(nx.Graph):
    TRANSLATION_DICT = {
        'Héraðsvegur': 'County Road',
        'Einkavegur': 'Private Road',
        'Almennur vegur': 'Public Road',
        'Stofnvegur': 'Main Road',
        'Tengivegur': 'Link Road',
        'Landsvegur': 'National Road',
        'Stofnvegur um hálendið': 'Highland Main Road'
    }
    # Iceland's bounding box coordinates in Web Mercator projection
    ICELAND_BOUNDS = {
        "xmin": -2800000,
        "ymin": 9100000,
        "xmax": -1400000,
        "ymax": 10100000
    }

    def __init__(self, incoming_graph_data=None, **attr):
        super().__init__(incoming_graph_data, **attr)

    def save(self, filename):
        """Save the RoadMap to a file using JSON."""
        adjacency_data = nx.to_dict_of_dicts(self)

        # Convert LineString to list of coordinates and tuple keys to strings
        adjacency_data_str_keys = {
            str(k): {
                str(inner_key): {
                    **val,
                    'geometry': list(val['geometry'].coords) if 'geometry' in val else None
                } for inner_key, val in v.items()
            } for k, v in adjacency_data.items()
        }

        with open(filename, 'w') as file:
            json.dump(adjacency_data_str_keys, file)

    @classmethod
    def load(cls, filename):
        """Load a RoadMap from a file using JSON."""
        with open(filename, 'r') as file:
            adjacency_data_str_keys = json.load(file)

        # Convert string keys back to tuples for nodes and list of coordinates to LineString
        from shapely.geometry import LineString
        adjacency_data = {
            (float(k.replace("(", "").replace(")", "").split(',')[0].strip()),
             float(k.replace("(", "").replace(")", "").split(',')[1].strip())
             ): {
                (float(inner_key.replace("(", "").replace(")", "").split(',')[0].strip()),
                 float(inner_key.replace("(", "").replace(
                     ")", "").split(',')[1].strip())
                 ): {
                    **val,
                    'geometry': LineString(val['geometry']) if val['geometry'] else None
                } for inner_key, val in v.items()
            } for k, v in adjacency_data_str_keys.items()
        }

        return cls(nx.from_dict_of_dicts(adjacency_data))

    @classmethod
    def load_from_wfs(cls, filename):
        """Load a RoadMap from a GeoJSON file."""
        gdf = gpd.read_file(filename)
        G = cls()

        # Function to handle both LineString and MultiLineString geometries
        def add_edges_from_geometry(G, geometry, road_type):
            if isinstance(geometry, LineString):
                start_point = geometry.coords[0]
                end_point = geometry.coords[-1]
                G.add_node(start_point)
                G.add_node(end_point)
                # Translate Icelandic road type to English
                translated_road_type = cls.TRANSLATION_DICT.get(
                    road_type, road_type)
                G.add_edge(start_point, end_point,
                           geometry=geometry, road_type=translated_road_type)
            elif isinstance(geometry, MultiLineString):
                for line in geometry.geoms:
                    add_edges_from_geometry(G, line, road_type)

        # Iterate over the GeoDataFrame to add edges to the graph
        for index, row in gdf.iterrows():
            # Adjust this based on the exact column name for road type
            road_type = row['vegflokkun_text_is']
            add_edges_from_geometry(G, row['geometry'], road_type)

        return G

    @property
    def road_types(self):
        """Return a list of all road types in the graph."""
        return [data.get('road_type', None) for _, _, data in self.edges(data=True)]

    def filter_by_road_type(self, road_types):
        """Return a new RoadMap that contains only the specified road types."""
        if isinstance(road_types, str):
            road_types = [road_types]

        filtered_edges = [(u, v, data) for u, v, data in self.edges(
            data=True) if data['road_type'] in road_types]

        G_filtered = RoadMap()

        for u, v, data in filtered_edges:
            G_filtered.add_edge(u, v, **data)
            G_filtered.add_node(u)
            G_filtered.add_node(v)

        return G_filtered

    def draw(self, title="Road Types in Iceland", zoom_to_extent=True):
        # Function to convert geometry to Web Mercator projection
        def to_web_mercator(geometry):
            project = pyproj.Transformer.from_crs(
                pyproj.CRS('EPSG:4326'),  # original (lat/lon)
                pyproj.CRS('EPSG:3857'),  # destination (Web Mercator)
                always_xy=True).transform
            return transform(project, geometry)

        # Set up the plot
        fig, ax = plt.subplots(figsize=(10, 10))

        # Define a colormap
        colors = plt.cm.tab20c.colors  # Using the tab20c colormap

        # Collect road types from the edges
        road_types = set(data['road_type']
                         for u, v, data in self.edges(data=True))

        all_lines = []

        for idx, road_type in enumerate(road_types):
            # Use the translation or the original if not found
            translated_road_type = self.TRANSLATION_DICT.get(
                road_type, road_type)

            # Extract edges of this road type
            edges = [(u, v) for u, v, data in self.edges(
                data=True) if data['road_type'] == road_type]
            lines = [self[u][v]['geometry'] for u, v in edges]

            # Plot them in Web Mercator projection
            for line in lines:
                line_mercator = to_web_mercator(line)
                xs, ys = line_mercator.xy
                ax.plot(xs, ys, color=colors[idx % 20],
                        label=translated_road_type, alpha=0.5)
                all_lines.append(line_mercator)

        # If zoom_to_extent is True, adjust the plot limits to the extent of the road data
        if zoom_to_extent:
            all_coords = [point for line in all_lines for point in line.coords]
            xs, ys = zip(*all_coords)
            ax.set_xlim(min(xs), max(xs))
            ax.set_ylim(min(ys), max(ys))
            print(f'{min(xs) = } {max(xs) = }{min(ys) = } {max(ys) = }')
        else:
            # Show the entire Iceland using the predefined bounding box
            ax.set_xlim(self.ICELAND_BOUNDS["xmin"],
                        self.ICELAND_BOUNDS["xmax"])
            ax.set_ylim(self.ICELAND_BOUNDS["ymin"],
                        self.ICELAND_BOUNDS["ymax"])

        # Add the specified basemap
        ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron)

        # Remove axes
        ax.set_axis_off()

        # Set legend with a specific location
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(),
                  title="Road Types", loc="upper left")

        # Set title and display the plot
        ax.set_title(title)
        plt.show()
