import pandas as pd
import numpy as np
import random # Ensure random is imported for mock data

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
    real-time factors, inventory management, carbon emission calculation,
    and generating conceptual re-route opportunities with cost analysis.

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
              conceptual re-route events (list of dicts),
              final truck states, and max simulation time.
    """
    if not route_ids:
        print("Warning: multi_truck_simulation received an empty route. Skipping simulation.")
        return {'log': [], 'segments': pd.DataFrame(), 're_route_events': [], 'final_truck_states': {}, 'max_simulation_time': 0.0}
    
    if len(route_ids) < 2:
        print("Warning: Route contains less than 2 nodes. No segments to simulate.")
        trucks = {}
        first_node_id = route_ids[0]
        try:
            network_df_for_coords = pd.read_csv('data/network.csv')
            node_coords_map = network_df_for_coords.set_index('node_id')[['lat', 'lon']].to_dict('index')
            initial_coords = node_coords_map.get(first_node_id, {'lat': 0, 'lon': 0})
        except FileNotFoundError:
            initial_coords = {'lat': 0, 'lon': 0}
            
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
                'total_emissions_kg': 0.0,
                'total_cost': 0.0
            }
        return {'log': [], 'segments': pd.DataFrame(), 're_route_events': [], 'final_truck_states': {}, 'max_simulation_time': 0.0}


    simulation_log = []
    all_segments_for_animation = []
    re_route_events = []
    
    demand_map = demand_map_initial.copy()

    # Define simple cost model: $/km
    COST_PER_KM_EV = 0.5 # Example: $0.5 per km (includes charging, maintenance, etc.)
    COST_PER_KM_DIESEL = 1.0 # Example: $1.0 per km (includes fuel, maintenance, etc.)

    trucks = {}
    for config in trucks_config:
        trucks[config['id']] = {
            'id': config['id'],
            'type': config['type'],
            'speed': config['speed'],
            'capacity': config['capacity'],
            'current_inventory': config['capacity'],
            'current_time': 0.0,
            'current_node_id': route_ids[0],
            'total_distance_km': 0.0,
            'total_adjusted_time_hr': 0.0,
            'total_emissions_kg': 0.0,
            'total_cost': 0.0
        }

    num_trucks = len(trucks_config)
    truck_route_segments = {truck['id']: [] for truck in trucks_config}
    
    # Distribute segments as contiguous blocks to ensure each truck has a meaningful path
    all_route_segments_list = []
    for i in range(len(route_ids) - 1):
        all_route_segments_list.append((route_ids[i], route_ids[i+1]))

    total_segments = len(all_route_segments_list)
    segments_per_truck = total_segments // num_trucks
    remainder_segments = total_segments % num_trucks

    current_segment_idx = 0
    for i, truck_config in enumerate(trucks_config):
        start_idx = current_segment_idx
        end_idx = start_idx + segments_per_truck
        if i < remainder_segments:
            end_idx += 1
        
        truck_route_segments[truck_config['id']] = all_route_segments_list[start_idx:end_idx]
        current_segment_idx = end_idx


    max_overall_time = 0.0

    try:
        network_df_for_coords = pd.read_csv('data/network.csv')
        node_coords_map = network_df_for_coords.set_index('node_id')[['lat', 'lon']].to_dict('index')
    except FileNotFoundError:
        print("Error: 'network.csv' not found. Cannot retrieve node coordinates for simulation.")
        return {'log': [], 'segments': pd.DataFrame(), 're_route_events': [], 'final_truck_states': {}, 'max_simulation_time': 0.0}

    # --- NEW: Randomly select a subset of EV trucks to trigger re-routes ---
    GUARANTEED_REROUTE_ACTIVE = True # Overall flag to enable/disable this feature
    
    reroute_ev_trucks_and_segments = {} # Stores {truck_id: segment_tuple_to_trigger_on}

    if GUARANTEED_REROUTE_ACTIVE:
        active_ev_truck_ids = [t['id'] for t in trucks_config if t['type'] == 'EV' and truck_route_segments[t['id']]]
        
        if active_ev_truck_ids: # Only proceed if there are active EV trucks
            num_rerouting_evs = random.randint(1, len(active_ev_truck_ids)) # Random number of EVs to reroute
            selected_ev_truck_ids_for_reroute = random.sample(active_ev_truck_ids, num_rerouting_evs)
            
            for truck_id in selected_ev_truck_ids_for_reroute:
                # Assign the first segment of the selected EV truck as the re-route trigger
                if truck_route_segments[truck_id]: # Ensure the truck actually has segments
                    reroute_ev_trucks_and_segments[truck_id] = truck_route_segments[truck_id][0]
                else:
                    print(f"Warning: Selected EV truck {truck_id} has no segments to reroute.")

    REROUTE_ALTERNATIVE_DISTANCE_MULTIPLIER = 1.1
    REROUTE_ALTERNATIVE_EMISSIONS_MULTIPLIER = 0.6
    REROUTE_ALTERNATIVE_COST_MULTIPLIER = 1.05

    # Alpha factor for carbon penalty on EV speed.
    ALPHA_CARBON_PENALTY_FACTOR = 0.002

    for truck_id, truck_data in trucks.items():
        current_truck_time = truck_data['current_time']
        current_inventory = truck_data['current_inventory']
        
        truck_config_details = next((t for t in trucks_config if t['id'] == truck_id), {})
        truck_emission_rate = truck_config_details.get('emission_rate_kg_per_km', 0.0)
        ev_consumption_kwh_per_km = truck_config_details.get('ev_consumption_kwh_per_km', 0.2)

        if not truck_route_segments[truck_id]:
            print(f"Info: Truck {truck_id} has no assigned route segments for this run. It will not move.")
            truck_data['total_distance_km'] = 0.0
            truck_data['total_adjusted_time_hr'] = 0.0
            truck_data['total_emissions_kg'] = 0.0
            truck_data['total_cost'] = 0.0
            continue

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
            
            adjusted_travel_time_hr = base_travel_time_hr * traffic_factor * weather_info['multiplier']
            
            if truck_data['type'] == 'EV':
                carbon_time_penalty_hr = (carbon_factor_api * ALPHA_CARBON_PENALTY_FACTOR) * base_travel_time_hr
                adjusted_travel_time_hr += carbon_time_penalty_hr


            segment_emissions_kg = 0.0
            segment_cost = 0.0
            if truck_data['type'] == 'EV':
                energy_consumption_kwh = base_distance_km * ev_consumption_kwh_per_km
                segment_emissions_kg = (energy_consumption_kwh * carbon_factor_api) / 1000.0
                segment_cost = base_distance_km * COST_PER_KM_EV
            else: # Diesel
                segment_emissions_kg = base_distance_km * truck_emission_rate
                segment_cost = base_distance_km * COST_PER_KM_DIESEL

            arrival_time_at_to_node = current_truck_time + adjusted_travel_time_hr

            # --- NEW: Re-route Event Trigger Logic (Random EV selection) ---
            if (truck_id in reroute_ev_trucks_and_segments and
                (from_node_id, to_node_id) == reroute_ev_trucks_and_segments[truck_id]):
                
                alt_distance_km = base_distance_km * REROUTE_ALTERNATIVE_DISTANCE_MULTIPLIER
                alt_travel_time_hr = alt_distance_km / truck_data['speed']
                
                alt_carbon_factor_api = random.uniform(50, 150)
                alt_emissions_kg = (alt_distance_km * ev_consumption_kwh_per_km * alt_carbon_factor_api) / 1000.0
                alt_cost = alt_distance_km * COST_PER_KM_EV * REROUTE_ALTERNATIVE_COST_MULTIPLIER

                emission_change_kg = segment_emissions_kg - alt_emissions_kg
                cost_change_usd = alt_cost - segment_cost
                time_change_hr = alt_travel_time_hr - adjusted_travel_time_hr

                offset_lat = random.uniform(-0.05, 0.05)
                offset_lon = random.uniform(-0.05, 0.05)
                alt_path_coords = [
                    [from_node_coords['lon'] + offset_lon, from_node_coords['lat'] + offset_lat],
                    [to_node_coords['lon'] + offset_lon, to_node_coords['lat'] + offset_lat]
                ]

                re_route_events.append({
                    'truckId': truck_id,
                    'original_from': from_node_id,
                    'original_to': to_node_id,
                    'trigger_time_hr': current_truck_time + (adjusted_travel_time_hr / 2),
                    'reason': f'High Carbon Grid Intensity ({carbon_factor_api:.0f} gCO2/kWh) on Original Path',
                    'original_emissions_kg': round(segment_emissions_kg, 4),
                    'original_cost_usd': round(segment_cost, 2),
                    'original_time_hr': round(adjusted_travel_time_hr, 2),
                    'alternative_emissions_kg': round(alt_emissions_kg, 4),
                    'alternative_cost_usd': round(alt_cost, 2),
                    'alternative_time_hr': round(alt_travel_time_hr, 2),
                    'emissions_change_kg': round(emission_change_kg, 4),
                    'cost_change_usd': round(cost_change_usd, 2),
                    'time_change_hr': round(time_change_hr, 2),
                    'original_path_coords': [[from_node_coords['lon'], from_node_coords['lat']], [to_node_coords['lon'], to_node_coords['lat']]],
                    'alternative_path_coords': alt_path_coords
                })

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
                'carbon_factor': round(carbon_factor_api, 2),
                'traffic_factor': round(traffic_factor, 2),
                'weather_condition': weather_info['condition'],
                'weather_factor': round(weather_info['multiplier'], 2),
                'emissions_kg': round(segment_emissions_kg, 4),
                'cost_usd': round(segment_cost, 2)
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
            truck_data['total_emissions_kg'] += segment_emissions_kg
            truck_data['total_cost'] += segment_cost

        max_overall_time = max(max_overall_time, current_truck_time)

    segments_df = pd.DataFrame(all_segments_for_animation)

    return {
        'log': simulation_log,
        'segments': segments_df,
        're_route_events': re_route_events,
        'final_truck_states': trucks,
        'max_simulation_time': max_overall_time
    }
