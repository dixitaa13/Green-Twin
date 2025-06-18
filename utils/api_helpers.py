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

