import os
import requests
import warnings
from dotenv import load_dotenv
from functools import lru_cache
from urllib3.exceptions import NotOpenSSLWarning

import pandas as pd
import networkx as nx
from geopy.distance import geodesic

# Suppress LibreSSL warning on macOS
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)


def load_network(csv_path="data/network.csv"):
    df = pd.read_csv(csv_path)
    return df

def create_graph(df):
    G = nx.Graph()
    for _, row in df.iterrows():
        G.add_node(row["id"],
                   name=row["name"],
                   type=row["type"],
                   pos=(row["latitude"], row["longitude"]))
    # Add geodesic distances as edge weights
    nodes = df[["id", "latitude", "longitude"]].values
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            node_i = nodes[i]
            node_j = nodes[j]
            dist = geodesic((node_i[1], node_i[2]), (node_j[1], node_j[2])).km
            G.add_edge(int(node_i[0]), int(node_j[0]), weight=round(dist, 2))
    return G

def build_distance_matrix(G):
    nodes = list(G.nodes)
    size = len(nodes)
    dist_matrix = [[0]*size for _ in range(size)]

    for i in range(size):
        for j in range(size):
            if i != j:
                try:
                    dist = G[nodes[i]][nodes[j]]['weight']
                except KeyError:
                    dist = float('inf')
                dist_matrix[i][j] = dist
    return dist_matrix, nodes


load_dotenv()

def _round_coord(val, precision=4):
    try:
        return round(float(val), precision)
    except:
        return val

@lru_cache(maxsize=256)
def _fetch_carbon_intensity(lat, lon):
    api_key = os.getenv("CO2SIGNAL_API_KEY")
    if not api_key:
        print("CO2SIGNAL_API_KEY not set")
        return None
    headers = {"auth-token": api_key}
    url = f"https://api.co2signal.com/v1/latest?lat={lat}&lon={lon}"
    try:
        response = requests.get(url, headers=headers, timeout=8)
        print(f"CO2Signal status: {response.status_code}")
        data = response.json()
        intensity = data.get("data", {}).get("carbonIntensity")
        if intensity is None:
            print("CO2Signal: intensity missing, fallback used")
        return intensity
    except Exception as e:
        print("CO₂ Signal API error:", e)
        return None

def get_carbon_intensity_factor(vehicle_type, latitude, longitude):
    if vehicle_type != "EV":
        return 1.0
    lat = _round_coord(latitude)
    lon = _round_coord(longitude)
    intensity = _fetch_carbon_intensity(lat, lon)
    if intensity is None:
        return 1.1
    if intensity < 150:
        return 1.0
    elif intensity < 300:
        return 1.1
    elif intensity < 450:
        return 1.2
    else:
        return 1.3

@lru_cache(maxsize=256)
def _fetch_weather_main(lat, lon):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        print("OPENWEATHER_API_KEY not set")
        return None
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}"
    try:
        response = requests.get(url, timeout=8)
        print(f"OpenWeatherMap status: {response.status_code}")
        data = response.json()
        weather_list = data.get("weather")
        if isinstance(weather_list, list) and weather_list:
            return weather_list[0].get("main")
        else:
            print("Weather API: 'weather' missing or empty")
            return None
    except Exception as e:
        print("Weather API error:", e)
        return None

def get_weather_factor(latitude, longitude):
    lat = _round_coord(latitude)
    lon = _round_coord(longitude)
    main = _fetch_weather_main(lat, lon)
    if main is None:
        return 1.1
    if main in ["Clear", "Clouds"]:
        return 1.0
    elif main in ["Rain", "Drizzle"]:
        return 1.15
    elif main in ["Thunderstorm", "Snow"]:
        return 1.25
    else:
        return 1.1

@lru_cache(maxsize=512)
def _fetch_traffic_factor(lat1, lon1, lat2, lon2):
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("GOOGLE_MAPS_API_KEY not set")
        return None
    url = (
        f"https://maps.googleapis.com/maps/api/directions/json?"
        f"origin={lat1},{lon1}&destination={lat2},{lon2}"
        f"&departure_time=now&key={api_key}"
    )
    try:
        response = requests.get(url, timeout=8)
        print(f"Google Maps Directions status: {response.status_code}")
        data = response.json()
        status = data.get("status")
        if status != "OK":
            print(f"Google Maps API returned status: {status}")
            return None
        routes = data.get("routes", [])
        if not routes:
            print("Google Maps: No routes found")
            return None
        leg0 = routes[0].get("legs", [])
        if not leg0:
            print("Google Maps: No legs in route")
            return None
        leg = leg0[0]
        duration = leg.get("duration", {}).get("value")
        traffic = leg.get("duration_in_traffic", {}).get("value", duration)
        if duration is None:
            print("Google Maps: duration missing")
            return None
        factor = traffic / duration if duration > 0 else 1.0
        factor = max(0.8, min(factor, 2.0))
        return round(factor, 2)
    except Exception as e:
        print("Google Maps API error:", e)
        return None

def get_traffic_factor(start_lat, start_lon, end_lat, end_lon):
    lat1 = _round_coord(start_lat)
    lon1 = _round_coord(start_lon)
    lat2 = _round_coord(end_lat)
    lon2 = _round_coord(end_lon)
    factor = _fetch_traffic_factor(lat1, lon1, lat2, lon2)
    if factor is None:
        return 1.1
    return factor
