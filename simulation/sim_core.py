def multi_truck_simulation(routes, dist_matrix, node_ids, trucks):
    """
    Simulates multiple trucks with individual routes and vehicle types.
    Includes inventory delivery logic.

    Parameters:
        routes (dict): {truck_id: [route_indices]}
        dist_matrix: 2D list of distances
        node_ids: list of actual node IDs (to match with demand)
        trucks (dict): {truck_id: {"type": "EV"/"Diesel", "speed": kmph}}

    Returns:
        logs: DataFrame of all truck events
        total_time: max end time across all trucks
    """
    import simpy
    import pandas as pd
    from utils.api_helpers import get_carbon_intensity_factor, get_traffic_factor, get_weather_factor

    traffic_factor = get_traffic_factor()
    weather_factor = get_weather_factor()

    env = simpy.Environment()
    all_logs = []

    # Load demand per node from CSV
    demand_df = pd.read_csv("data/demand.csv")
    demand_dict = dict(zip(demand_df['node_id'], demand_df['demand']))

    def truck_process(env, truck_id, route, vehicle_type, speed, demand_dict, capacity=30, service_time=1):
        inventory = capacity
        current_time = 0

        carbon_factor = get_carbon_intensity_factor(vehicle_type)
        multiplier = carbon_factor * traffic_factor * weather_factor

        for i in range(len(route) - 1):
            from_node = route[i]
            to_node = route[i + 1]
            distance = dist_matrix[from_node][to_node]
            travel_time = distance / speed
            adjusted_travel_time = travel_time * multiplier

            yield env.timeout(adjusted_travel_time)
            current_time += adjusted_travel_time

            delivered = 0
            actual_to_node_id = node_ids[to_node]
            if actual_to_node_id in demand_dict:
                required = demand_dict[actual_to_node_id]
                delivered = min(inventory, required)
                inventory -= delivered
                demand_dict[actual_to_node_id] -= delivered  # update remaining demand

            all_logs.append({
                "Truck": truck_id,
                "Type": vehicle_type,
                "From": node_ids[from_node],
                "To": actual_to_node_id,
                "Distance": round(distance, 2),
                "Travel Time": round(travel_time, 2),
                "Adjusted Travel Time": round(adjusted_travel_time, 2),
                "Arrival Time": round(current_time, 2),
                "Delivered": delivered,
                "Remaining Inventory": inventory,
                "Carbon Factor": round(carbon_factor, 2),
                "Traffic Factor": round(traffic_factor, 2),
                "Weather Factor": round(weather_factor, 2)
            })

            yield env.timeout(service_time)
            current_time += service_time

    for truck_id, route in routes.items():
        vehicle = trucks[truck_id]
        env.process(truck_process(env, truck_id, route, vehicle["type"], vehicle["speed"], demand_dict))

    env.run()
    log_df = pd.DataFrame(all_logs)
    total_time = round(log_df["Arrival Time"].max(), 2) if not log_df.empty else 0
    return log_df, total_time
