import pandas as pd
import numpy as np

def multi_truck_simulation(
    route_ids,
    distance_matrix,
    node_id_to_index,
    index_to_node_id,
    demand_map_initial,
    trucks_config,
    get_traffic_factor_func,
    get_weather_factor_func,
    get_carbon_intensity_func
):
    """
    Simulates multi-truck deliveries over an optimized route, incorporating
    real-time factors, inventory management, and carbon emission calculation.

    Args:
        route_ids (list): List of node IDs representing the optimized route.
        distance_matrix (np.array): Matrix of distances between nodes.
        node_id_to_index (dict): Mapping from node ID to its index in the matrix.
        index_to_node_id (dict): Mapping from index to node ID.
        demand_map_initial (dict): Initial demand for each store node.
        trucks_config (list): List of dictionaries, each describing a truck,
                              including 'emission_rate_kg_per_km' and 'ev_consumption_kwh_per_km'.
        get_traffic_factor_func (function): Function to get traffic factor (mock or real).
        get_weather_factor_func (function): Function to get weather factor (mock or real).
        get_carbon_intensity_func (function): Function to get carbon intensity (mock or real).

    Returns:
        dict: Contains simulation log (list of dicts), animation segments (DataFrame),
              final truck states, and max simulation time.
    """
    # Handle empty route_ids gracefully
    if not route_ids:
        print("Warning: multi_truck_simulation received an empty route. Skipping simulation.")
        return {'log': [], 'segments': pd.DataFrame(), 'final_truck_states': {}, 'max_simulation_time': 0.0}
    
    # If there's only one node in the route, there are no segments to simulate
    if len(route_ids) < 2:
        print("Warning: Route contains less than 2 nodes. No segments to simulate.")
        trucks = {}
        first_node_id = route_ids[0]
        try:
            network_df_for_coords = pd.read_csv('data/network.csv')
            node_coords_map = network_df_for_coords.set_index('node_id')[['lat', 'lon']].to_dict('index')
            initial_coords = node_coords_map.get(first_node_id, {'lat': 0, 'lon': 0})
        except FileNotFoundError:
            initial_coords = {'lat': 0, 'lon': 0} # Fallback
            
        for config in trucks_config:
            trucks[config['id']] = {
                'id': config['id'],
                'type': config['type'],
                'speed': config['speed'],
                'capacity': config['capacity'],
                'current_inventory': config['capacity'],
                'current_time': 0.0,
                'current_node_id': first_node_id,
                'total_distance_km': 0.0,
                'total_adjusted_time_hr': 0.0,
                'total_emissions_kg': 0.0
            }
        return {'log': [], 'segments': pd.DataFrame(), 'final_truck_states': trucks, 'max_simulation_time': 0.0}


    simulation_log = []
    all_segments_for_animation = []
    
    demand_map = demand_map_initial.copy()

    trucks = {}
    for config in trucks_config:
        trucks[config['id']] = {
            'id': config['id'],
            'type': config['type'],
            'speed': config['speed'],
            'capacity': config['capacity'],
            'current_inventory': config['capacity'], # Start fully loaded
            'current_time': 0.0,
            'current_node_id': route_ids[0], # All trucks start at the first node (DC)
            'total_distance_km': 0.0,
            'total_adjusted_time_hr': 0.0,
            'total_emissions_kg': 0.0 # Initialize total emissions for each truck
        }

    num_trucks = len(trucks_config)
    truck_route_segments = {truck['id']: [] for truck in trucks_config}
    
    for i in range(len(route_ids) - 1):
        from_node = route_ids[i]
        to_node = route_ids[i+1]
        truck_idx = i % num_trucks
        truck_route_segments[trucks_config[truck_idx]['id']].append((from_node, to_node))

    max_overall_time = 0.0

    try:
        network_df_for_coords = pd.read_csv('data/network.csv')
        node_coords_map = network_df_for_coords.set_index('node_id')[['lat', 'lon']].to_dict('index')
    except FileNotFoundError:
        print("Error: 'network.csv' not found. Cannot retrieve node coordinates for simulation.")
        return {'log': [], 'segments': pd.DataFrame(), 'final_truck_states': {}, 'max_simulation_time': 0.0}

    for truck_id, truck_data in trucks.items():
        current_truck_time = truck_data['current_time']
        current_inventory = truck_data['current_inventory']
        
        # Get the emission rate and EV consumption rate for the current truck type
        truck_config_details = next((t for t in trucks_config if t['id'] == truck_id), {})
        truck_emission_rate = truck_config_details.get('emission_rate_kg_per_km', 0.0)
        ev_consumption_kwh_per_km = truck_config_details.get('ev_consumption_kwh_per_km', 0.2) # Default for EV

        for from_node_id, to_node_id in truck_route_segments[truck_id]:
            from_node_coords = node_coords_map.get(from_node_id)
            to_node_coords = node_coords_map.get(to_node_id)

            if not from_node_coords or not to_node_coords:
                print(f"Warning: Missing coordinates for node {from_node_id} or {to_node_id}. Skipping segment.")
                continue

            dist_idx_from = node_id_to_index[from_node_id]
            dist_idx_to = node_id_to_index[to_node_id]
            base_distance_km = distance_matrix[dist_idx_from, dist_idx_to]
            base_travel_time_hr = base_distance_km / truck_data['speed']

            traffic_factor = get_traffic_factor_func(from_node_coords['lat'], from_node_coords['lon'])
            weather_info = get_weather_factor_func(from_node_coords['lat'], from_node_coords['lon'])
            carbon_factor_api = get_carbon_intensity_func(from_node_coords['lat'], from_node_coords['lon'])
            
            carbon_impact_on_time_factor = carbon_factor_api if truck_data['type'] == 'EV' else 1.0

            adjusted_travel_time_hr = base_travel_time_hr * traffic_factor * weather_info['multiplier'] * carbon_impact_on_time_factor

            # Calculate Emissions for this segment
            segment_emissions_kg = 0.0
            if truck_data['type'] == 'EV':
                energy_consumption_kwh = base_distance_km * ev_consumption_kwh_per_km
                segment_emissions_kg = (energy_consumption_kwh * carbon_factor_api) / 1000.0 # Convert gCO2 to kgCO2
            else: # Diesel
                segment_emissions_kg = base_distance_km * truck_emission_rate

            arrival_time_at_to_node = current_truck_time + adjusted_travel_time_hr

            delivered_quantity = 0
            if to_node_id in demand_map and demand_map[to_node_id] > 0:
                deliverable = min(current_inventory, demand_map[to_node_id])
                delivered_quantity = deliverable
                current_inventory -= deliverable
                demand_map[to_node_id] -= deliverable

            simulation_log.append({
                'truckId': truck_id,
                'type': truck_data['type'],
                'from': from_node_id,
                'to': to_node_id,
                'distance_km': round(base_distance_km, 2),
                'base_travel_time_hr': round(base_travel_time_hr, 2),
                'adjusted_travel_time_hr': round(adjusted_travel_time_hr, 2),
                'arrival_time_hr': round(arrival_time_at_to_node, 2),
                'delivered': delivered_quantity,
                'remaining_inventory': current_inventory,
                'carbon_factor': round(carbon_factor_api, 2), # Raw intensity
                'traffic_factor': round(traffic_factor, 2),
                'weather_condition': weather_info['condition'],
                'weather_factor': round(weather_info['multiplier'], 2),
                'emissions_kg': round(segment_emissions_kg, 4) # Emissions added to log
            })

            all_segments_for_animation.append({
                'truckId': truck_id,
                'coordinates': [[from_node_coords['lon'], from_node_coords['lat']],
                                [to_node_coords['lon'], to_node_coords['lat']]],
                'startTime': current_truck_time,
                'endTime': arrival_time_at_to_node,
                'type': truck_data['type']
            })

            current_truck_time = arrival_time_at_to_node
            truck_data['current_inventory'] = current_inventory
            truck_data['current_node_id'] = to_node_id
            truck_data['total_distance_km'] += base_distance_km
            truck_data['total_adjusted_time_hr'] += adjusted_travel_time_hr
            truck_data['total_emissions_kg'] += segment_emissions_kg # Accumulate total emissions for truck

        max_overall_time = max(max_overall_time, current_truck_time)

    segments_df = pd.DataFrame(all_segments_for_animation)

    return {
        'log': simulation_log,
        'segments': segments_df,
        'final_truck_states': trucks,
        'max_simulation_time': max_overall_time
    }
