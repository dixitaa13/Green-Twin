def multi_truck_simulation(routes, dist_matrix, node_ids, trucks, node_coords_df):
    import simpy
    import pandas as pd
    from utils.api_helpers import get_carbon_intensity_factor, get_traffic_factor, get_weather_factor

    env = simpy.Environment()
    all_logs = []

    # Load demand
    demand_df = pd.read_csv("data/demand.csv")
    demand_dict = dict(zip(demand_df['node_id'], demand_df['demand']))

    # Build id->(lat, lon) mapping once
    id_to_coord = {row["id"]: (row["latitude"], row["longitude"]) for _, row in node_coords_df.iterrows()}

    def truck_process(env, truck_id, route, vehicle_type, speed, demand_dict, capacity=30, service_time=1):
        inventory = capacity
        current_time = 0

        for i in range(len(route) - 1):
            from_node = route[i]
            to_node = route[i + 1]
            distance = dist_matrix[from_node][to_node]
            travel_time = distance / speed

            # Fetch coordinates quickly
            from_id = node_ids[from_node]
            to_id = node_ids[to_node]
            lat1, lon1 = id_to_coord[from_id]
            lat2, lon2 = id_to_coord[to_id]

            # Get real-world factors
            carbon_factor = get_carbon_intensity_factor(vehicle_type, lat1, lon1)
            traffic_factor = get_traffic_factor(lat1, lon1, lat2, lon2)
            weather_factor = get_weather_factor(lat1, lon1)
            multiplier = carbon_factor * traffic_factor * weather_factor

            adjusted_travel_time = travel_time * multiplier

            yield env.timeout(adjusted_travel_time)
            current_time += adjusted_travel_time

            delivered = 0
            if to_id in demand_dict:
                required = demand_dict[to_id]
                delivered = min(inventory, required)
                inventory -= delivered
                demand_dict[to_id] -= delivered

            all_logs.append({
                "Truck": truck_id,
                "Type": vehicle_type,
                "From": from_id,
                "To": to_id,
                "Distance (km)": round(distance, 2),
                "Travel Time (hr)": round(travel_time, 2),
                "Adjusted Travel Time (hr)": round(adjusted_travel_time, 2),
                "Arrival Time (hr)": round(current_time, 2),
                "Delivered": delivered,
                "Remaining Inventory": inventory,
                "Carbon Factor": round(carbon_factor, 2),
                "Traffic Factor": round(traffic_factor, 2),
                "Weather Factor": round(weather_factor, 2)
            })

            yield env.timeout(service_time)
            current_time += service_time

    # Start processes for each truck, consider copying demand_dict if needed
    for truck_id, route in routes.items():
        vehicle = trucks[truck_id]
        env.process(truck_process(env, truck_id, route, vehicle["type"], vehicle["speed"], demand_dict))
        # If demand isolated per truck: use demand_dict.copy() instead

    env.run()
    log_df = pd.DataFrame(all_logs)
    total_time = round(log_df["Arrival Time (hr)"].max(), 2) if not log_df.empty else 0
    return log_df, total_time
