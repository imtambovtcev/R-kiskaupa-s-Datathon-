import json

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import pyproj
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import nearest_points, transform


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
        gdf = gpd.read_file(filename).to_crs("EPSG:3857")
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

    def filter_circular_paths(self):
        """Return a new RoadMap that contains only the roads that are part of circles (closed paths)."""

        # Create a new empty RoadMap
        G_filtered = RoadMap()

        # Identify all simple cycles (closed paths) in the graph
        for cycle in nx.simple_cycles(self):
            # If the cycle has more than 2 nodes, it's a valid closed path
            if len(cycle) > 2:
                # Create pairs of nodes to represent the edges in the cycle
                pairs = [(cycle[i], cycle[i+1]) for i in range(len(cycle)-1)]
                pairs.append((cycle[-1], cycle[0]))  # Closing the loop

                # Add these edges and their data to the new RoadMap
                for u, v in pairs:
                    if self.has_edge(u, v):
                        data = self[u][v]
                        G_filtered.add_edge(u, v, **data)
                        G_filtered.add_node(u)
                        G_filtered.add_node(v)

        return G_filtered

    def closest_road(self, location):
        """
        Find the closest road to the given location.

        Parameters:
        - location (tuple): A tuple representing (longitude, latitude) of the location.

        Returns:
        - (u, v, data): A tuple representing the start node, end node, and edge data of the closest road.
        """

        # Convert location to a Shapely Point
        location_point = Point(location)

        # Set an initial large value for minimum distance
        min_distance = float('inf')
        closest_edge = None

        # Iterate over all the road geometries in the graph
        for u, v, data in self.edges(data=True):
            distance = location_point.distance(data['geometry'])
            if distance < min_distance:
                min_distance = distance
                closest_edge = (u, v, data)

        return closest_edge

    def assign_traffic_to_roads(self, gdf_traffic):
        """
        Assign traffic values to the nearest roads.

        Parameters:
        - gdf_traffic: GeoDataFrame containing traffic points with traffic columns and geometry.
        """

        # Ensure the gdf_traffic is in the correct CRS
        gdf_traffic = gdf_traffic.to_crs("EPSG:3857")

        # Iterate over each traffic point
        for idx, row in gdf_traffic.iterrows():
            traffic_point_coords = row.geometry.coords[0]
            traffic_data = {
                'UMF_15MIN': row['UMF_15MIN'],
                'UMF_I_DAG': row['UMF_I_DAG'],
                'UMF_DAGUR1': row['UMF_DAGUR1'],
                'UMF_DAGUR2': row['UMF_DAGUR2'],
                'UMF_DAGUR3': row['UMF_DAGUR3'],
                'UMF_DAGUR4': row['UMF_DAGUR4'],
                'UMF_DAGUR5': row['UMF_DAGUR5'],
                'UMF_DAGUR6': row['UMF_DAGUR6'],
                'UMF_DAGUR7': row['UMF_DAGUR7'],
                'coordinates': traffic_point_coords
            }

            # Find the nearest road to this traffic point using the closest_road method
            u, v, _ = self.closest_road(traffic_point_coords)

            # Update the traffic data for the nearest road
            self[u][v]['traffic'] = traffic_data

    def subgraph_with_only_traffic(self):
        """
        Return a subgraph containing only the edges that have traffic data.

        Returns:
        - A RoadMap instance (or NetworkX Graph) containing only the edges with traffic data.
        """

        edges_with_traffic = [(u, v, data) for u, v, data in self.edges(
            data=True) if 'traffic' in data]

        # Create an empty graph of the same type as the current graph
        G_traffic = type(self)()
        for u, v, data in edges_with_traffic:
            G_traffic.add_edge(u, v, **data)

        return G_traffic

    def subgraph_with_traffic(self):
        """
        Return a connected subgraph that contains all nodes associated with traffic data using Steiner Tree approximation.

        Returns:
        - A RoadMap instance (or NetworkX Graph) that's a tree connecting all nodes with traffic data.
        """

        # Identify nodes connected to edges with 'traffic' attribute
        traffic_nodes = set()
        for u, v, data in self.edges(data=True):
            if 'traffic' in data:
                traffic_nodes.add(u)
                traffic_nodes.add(v)

        # Calculate the shortest paths between all pairs of these nodes
        complete_graph = nx.complete_graph(traffic_nodes)
        for u, v in complete_graph.edges():
            path_length = nx.shortest_path_length(self, source=u, target=v, weight='length')
            complete_graph[u][v]['length'] = path_length

        # Compute the Minimum Spanning Tree of this complete graph
        mst = nx.minimum_spanning_tree(complete_graph, weight='length')

        # Build the subgraph of the original graph that corresponds to this MST
        G_sub = self.__class__()
        for u, v in mst.edges():
            path = nx.shortest_path(self, source=u, target=v, weight='length')
            for i in range(len(path) - 1):
                if not G_sub.has_edge(path[i], path[i + 1]):
                    G_sub.add_edge(path[i], path[i + 1], **self[path[i]][path[i + 1]])

        return G_sub


    def draw(self, title="Road Types in Iceland", zoom_to_extent=True, fig=None, ax=None,
             save=None, show=True, show_traffic_cameras=False):

        if fig is None or ax is None:
            fig, ax = plt.subplots(figsize=(10, 10))

        colors = plt.cm.tab20c.colors  # Using the tab20c colormap

        road_types = set(data['road_type']
                         for u, v, data in self.edges(data=True))
        all_lines = []

        for idx, road_type in enumerate(road_types):
            translated_road_type = self.TRANSLATION_DICT.get(
                road_type, road_type)
            edges = [(u, v) for u, v, data in self.edges(
                data=True) if data['road_type'] == road_type]
            lines = [self[u][v]['geometry'] for u, v in edges]

            for line in lines:
                xs, ys = line.xy
                ax.plot(xs, ys, color=colors[idx % 20],
                        label=translated_road_type, alpha=0.5)
                all_lines.append(line)

        if show_traffic_cameras:
            # Extract locations of traffic cameras from edges with the attribute 'traffic'
            camera_coords = [(u[0], u[1]) for u, v, data in self.edges(
                data=True) if 'traffic' in data]
            camera_xs, camera_ys = zip(*camera_coords)
            ax.scatter(camera_xs, camera_ys, color='red',
                       s=50, label='Traffic Cameras')

        if zoom_to_extent:
            all_coords = [point for line in all_lines for point in line.coords]
            xs, ys = zip(*all_coords)
            ax.set_xlim(min(xs), max(xs))
            ax.set_ylim(min(ys), max(ys))
        else:
            ax.set_xlim(self.ICELAND_BOUNDS["xmin"],
                        self.ICELAND_BOUNDS["xmax"])
            ax.set_ylim(self.ICELAND_BOUNDS["ymin"],
                        self.ICELAND_BOUNDS["ymax"])

        ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron)
        ax.set_axis_off()

        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(),
                  title="Road Types", loc="upper left")
        ax.set_title(title)

        if save:
            plt.savefig(save)

        if show:
            plt.show()
        else:
            return fig, ax
