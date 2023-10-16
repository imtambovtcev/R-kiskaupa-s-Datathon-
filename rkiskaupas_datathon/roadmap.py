import json
import networkx as nx


class RoadMap(nx.Graph):
    def __init__(self, incoming_graph_data=None, **attr):
        super().__init__(incoming_graph_data, **attr)

    def save(self, filename):
        """Save the RoadMap to a file using JSON."""
        adjacency_data = nx.to_dict_of_lists(self)
        with open(filename, 'w') as file:
            json.dump(adjacency_data, file)

    @classmethod
    def load(cls, filename):
        """Load a RoadMap from a file using JSON."""
        with open(filename, 'r') as file:
            adjacency_data = json.load(file)
        return cls(nx.from_dict_of_lists(adjacency_data))
