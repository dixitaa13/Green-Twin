import pandas as pd
import networkx as nx
from geopy.distance import geodesic

def load_network(csv_path="data/network.csv"):
    df = pd.read_csv(csv_path)
    return df

def create_graph(df):
    G = nx.Graph()
    # Add nodes with coordinates
    for _, row in df.iterrows():
        G.add_node(row["id"], 
                   name=row["name"], 
                   type=row["type"],
                   pos=(row["latitude"], row["longitude"]))
    # Add edges with geodesic distance as weight (fully connected for now)
    nodes = df[["id", "latitude", "longitude"]].values
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            node_i = nodes[i]
            node_j = nodes[j]
            dist = geodesic((node_i[1], node_i[2]), (node_j[1], node_j[2])).km
            G.add_edge(int(node_i[0]), int(node_j[0]), weight=round(dist, 2))
    return G
    
def build_distance_matrix(G):
    """Returns a distance matrix using the edge weights from the graph G"""
    nodes = list(G.nodes)
    size = len(nodes)
    dist_matrix = [[0]*size for _ in range(size)]

    for i in range(size):
        for j in range(size):
            if i != j:
                try:
                    dist = G[nodes[i]][nodes[j]]['weight']
                except KeyError:
                    dist = float('inf')  # if no direct edge
                dist_matrix[i][j] = dist
    return dist_matrix, nodes  # return node id mapping too


