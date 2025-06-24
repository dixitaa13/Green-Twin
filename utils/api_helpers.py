import pandas as pd
import networkx as nx
import numpy as np
from math import radians, sin, cos, sqrt, atan2
import random
import streamlit as st # ADDED: Import streamlit

# --- Data Loading Functions ---
def load_network(csv_path):
    """Loads network data from a CSV file."""
    df = pd.read_csv(csv_path) # CORRECTED: Changed pd.read_path to pd.read_csv
    return df

def create_graph(network_df):
    """Creates a NetworkX graph from the network DataFrame."""
    G = nx.Graph()
    for index, row in network_df.iterrows():
        G.add_node(row['node_id'], name=row['name'], type=row['type'], lat=row['lat'], lon=row['lon'], country=row['country'])

    # Add edges between all nodes for initial distance calculation
    # In a real scenario, this would be based on actual road network connectivity.
    for i, node1 in network_df.iterrows():
        for j, node2 in network_df.iterrows():
            if node1['node_id'] != node2['node_id']:
                dist = haversine_distance(node1['lat'], node1['lon'], node2['lat'], node2['lon'])
                G.add_edge(node1['node_id'], node2['node_id'], weight=dist)
    return G

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the haversine distance between two points in km."""
    R = 6371  # Radius of Earth in kilometers

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return distance

def build_distance_matrix(G):
    """Builds a distance matrix from the graph using edge weights."""
    nodes_list = list(G.nodes())
    node_id_to_index = {node_id: i for i, node_id in enumerate(nodes_list)}
    index_to_node_id = {i: node_id for i, node_id in enumerate(nodes_list)}

    matrix_size = len(nodes_list)
    distance_matrix = np.zeros((matrix_size, matrix_size))

    for i in range(matrix_size):
        for j in range(matrix_size):
            if i == j:
                distance_matrix[i, j] = 0
            else:
                node1_id = index_to_node_id[i]
                node2_id = index_to_node_id[j]
                # Use pre-calculated haversine distance (edge weight)
                distance_matrix[i, j] = G[node1_id][node2_id]['weight']
    return distance_matrix, node_id_to_index, index_to_node_id

# --- Mock API Functions for Real-Time Factors ---
# In a real application, these would make actual HTTP requests to external APIs.
# For a hackathon, robust mocks are key to demonstrating the concept without API keys.

@st.cache_data(ttl=3600) # Cache for 1 hour for demo purposes
def get_mock_traffic_factor(lat, lon):
    """
    Mocks a traffic factor based on location.
    Simulates fetching real-time traffic conditions.
    A factor > 1 means slower travel.
    """
    # Simple mock: higher traffic in denser areas (arbitrary lat/lon ranges)
    if (25 < lat < 45 and -125 < lon < -70) or (48 < lat < 55 and -5 < lon < 10): # US East/West, UK/France/Germany
        return 1.0 + random.uniform(0.1, 0.4) # Moderate to high traffic
    elif (10 < lat < 30 and 70 < lon < 90) or (30 < lat < 40 and 130 < lon < 145): # India, Japan
        return 1.0 + random.uniform(0.2, 0.5) # Potentially higher traffic
    else:
        return 1.0 + random.uniform(0.05, 0.2) # Lighter traffic
    
@st.cache_data(ttl=3600) # Cache for 1 hour for demo purposes
def get_mock_weather_factor(lat, lon):
    """
    Mocks a weather factor based on location.
    Simulates fetching real-time weather conditions and their impact.
    A factor > 1 means slower travel.
    """
    conditions = ["Clear", "Rain", "Snow", "Fog"]
    selected_condition = random.choice(conditions)
    
    multiplier = 1.0
    if selected_condition == "Rain":
        multiplier = random.uniform(1.1, 1.25)
    elif selected_condition == "Snow":
        multiplier = random.uniform(1.3, 1.5)
    elif selected_condition == "Fog":
        multiplier = random.uniform(1.1, 1.3)
        
    return {"condition": selected_condition, "multiplier": multiplier}

@st.cache_data(ttl=3600) # Cache for 1 hour for demo purposes
def get_mock_carbon_intensity(lat, lon):
    """
    Mocks grid carbon intensity for EV charging/operations.
    Lower values mean "cleaner" electricity. Factor can influence EV routing.
    Values are illustrative (e.g., gCO2/kWh or a scaled factor).
    """
    # Simulate variations based on location/time of day (simplified here)
    intensity = random.uniform(150, 450) # gCO2/kWh illustrative range
    
    # Map intensity to a multiplier (e.g., lower intensity = slightly faster "charge" or better efficiency)
    # This is a conceptual link for demo. In real, it's about optimizing charge times.
    # For travel time: higher carbon intensity might conceptually lead to a slight delay
    # if truck is waiting for cleaner grid for charging/operation, or just for reporting.
    # Here, let's use it as a direct factor: higher intensity = slightly higher travel time (proxy for inefficiency)
    # Normalized for a factor of around 1: (intensity / avg_intensity)
    
    avg_intensity = 300
    return intensity / avg_intensity
