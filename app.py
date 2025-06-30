import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
from datetime import datetime, timedelta

# Import custom modules
from utils.api_helpers import load_network, create_graph, build_distance_matrix, get_mock_traffic_factor, get_mock_weather_factor, get_mock_carbon_intensity
from optimization.route_solver import solve_advanced_tsp
from simulation.sim_core import multi_truck_simulation
from visuals.charts import plot_network_pydeck, get_positions_at_time, calculate_bounding_box, highlight_impacted_segments

# --- Function moved from visuals/charts.py to app.py for NameError fix ---
def calculate_zoom_level(bbox, map_width_px=1000, map_height_px=600):
    """
    Estimates a PyDeck zoom level based on a bounding box.
    This is a simplified heuristic and might need fine-tuning.
    Moved to app.py to resolve NameError.
    """
    min_lat, max_lat, min_lon, max_lon = bbox
    
    # Add a small buffer to the bounding box
    lat_buffer = (max_lat - min_lat) * 0.1
    lon_buffer = (max_lon - min_lon) * 0.1
    min_lat -= lat_buffer
    max_lat += lat_buffer
    min_lon -= lon_buffer
    max_lon += lon_buffer

    # Handle single point or very small bounds to avoid division by zero or extreme zoom
    if min_lat == max_lat: max_lat += 0.001
    if min_lon == max_lon: min_lon += 0.001

    # Approximate Earth's circumference at equator in meters
    EARTH_CIRCUMFERENCE = 40075017 # meters

    # Calculate meters per pixel at zoom 0
    # From Mapbox GL JS documentation, meters per pixel at zoom 0 (equator) is approx 78271.517
    # Or, 2 * pi * 6378137 / 256 (where 256 is tile size)
    METERS_PER_PIXEL_ZOOM_0 = 78271.517

    # Calculate approximate width/height in meters
    width_meters = np.cos(np.radians((min_lat + max_lat) / 2)) * EARTH_CIRCUMFERENCE * (max_lon - min_lon) / 360
    height_meters = EARTH_CIRCUMFERENCE * (max_lat - min_lat) / 360

    # Calculate zoom based on the larger dimension
    if width_meters > height_meters:
        zoom = np.log2(METERS_PER_PIXEL_ZOOM_0 * map_width_px / width_meters)
    else:
        zoom = np.log2(METERS_PER_PIXEL_ZOOM_0 * map_height_px / height_meters)
    
    # Clamp zoom to a reasonable range
    return max(0.5, min(zoom, 10)) # Max zoom 10 to prevent over-zooming on small clusters


# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="GreenTwin: Sustainable Logistics Digital Twin",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Global Data Loading (Cached to avoid re-running on every interaction) ---
@st.cache_data
def load_all_initial_data():
    """Loads ALL network and demand data without filtering."""
    try:
        full_network_df = load_network('data/network.csv')
        full_demand_df = pd.read_csv('data/demand.csv')
        full_demand_map = full_demand_df.set_index('node_id')['demand'].to_dict()
        return full_network_df, full_demand_map
    except FileNotFoundError:
        st.error("Error: 'network.csv' or 'demand.csv' not found in the 'data/' directory. Please ensure these files are in the 'data/' folder.")
        st.stop()

# Load all data once at the start
full_network_df, full_demand_map = load_all_initial_data()

# --- Session State Initialization ---
if 'trucks_config' not in st.session_state:
    st.session_state.trucks_config = [
        {'id': 'EV-01', 'type': 'EV', 'speed': 60, 'capacity': 500, 'color': [34, 197, 94], 'emission_rate_kg_per_km': 0.0, 'ev_consumption_kwh_per_km': 0.2}, # EV: 0 direct, but impacted by grid
        {'id': 'Diesel-01', 'type': 'Diesel', 'speed': 80, 'capacity': 700, 'color': [234, 179, 8], 'emission_rate_kg_per_km': 0.26, 'ev_consumption_kwh_per_km': 0.0}, # Diesel: fixed rate
    ]
if 'optimized_route' not in st.session_state:
    st.session_state.optimized_route = []
if 'simulation_results' not in st.session_state:
    st.session_state.simulation_results = None
if 'max_simulation_time' not in st.session_state:
    st.session_state.max_simulation_time = 0.0
if 'simulation_time_slider' not in st.session_state:
    st.session_state.simulation_time_slider = 0.0
if 'selected_country' not in st.session_state:
    st.session_state.selected_country = full_network_df['country'].unique()[0] if not full_network_df.empty else 'USA'
if 'scenario_results' not in st.session_state:
    st.session_state.scenario_results = {} # Stores results for comparison scenarios
if 'scenario_counter' not in st.session_state:
    st.session_state.scenario_counter = 0

# --- Sidebar Navigation ---
st.sidebar.title("GreenTwin Dashboard")
st.sidebar.markdown("---")

# Country Selection Dropdown
all_countries = sorted(full_network_df['country'].unique().tolist())
st.session_state.selected_country = st.sidebar.selectbox(
    "Select Country",
    all_countries,
    index=all_countries.index(st.session_state.selected_country) if st.session_state.selected_country in all_countries else 0,
    key="country_selector"
)

st.sidebar.markdown("---")

page = st.sidebar.selectbox(
    "Navigate Sections",
    ("📊 Overview", "🌐 Network & Optimization", "🚚 Simulation & Animation", "⚖️ Scenario Comparison", "⚙️ Configuration", "📜 Raw Logs"), # Added new page
    key="main_nav_selector"
)

st.sidebar.markdown("---")
st.sidebar.info("Developed for a National Level Hackathon")

# --- Filter Data Based on Selected Country ---
network_df = full_network_df[full_network_df['country'] == st.session_state.selected_country].copy()
country_node_ids = network_df['node_id'].tolist()
demand_map_filtered = {k: v for k, v in full_demand_map.items() if k in country_node_ids}

G = create_graph(network_df)
distance_matrix, node_id_to_index, index_to_node_id = build_distance_matrix(G)

# --- Function to run a simulation (re-usable for scenarios) ---
def run_simulation_and_store(route, dist_matrix, node_idx_map, idx_node_map, demand, trucks_cfg):
    st.session_state.scenario_counter += 1
    scenario_name = f"Run {st.session_state.scenario_counter} ({st.session_state.selected_country})"

    fleet_summary = []
    ev_count = sum(1 for t in trucks_cfg if t['type'] == 'EV')
    diesel_count = sum(1 for t in trucks_cfg if t['type'] == 'Diesel')
    if ev_count > 0: fleet_summary.append(f"{ev_count} EV")
    if diesel_count > 0: fleet_summary.append(f"{diesel_count} Diesel")
    if fleet_summary:
        scenario_name += f" - ({', '.join(fleet_summary)})"


    with st.spinner(f"Running simulation for '{scenario_name}'..."):
        sim_results = multi_truck_simulation(
            route,
            dist_matrix,
            node_idx_map,
            idx_node_map,
            demand,
            trucks_cfg,
            get_mock_traffic_factor,
            get_mock_weather_factor,
            get_mock_carbon_intensity
        )
        
        log_df_for_calc = pd.DataFrame(sim_results['log'])
        
        total_emissions = float(log_df_for_calc["emissions_kg"].sum()) if not log_df_for_calc.empty else 0.0
        total_sim_time = float(sim_results['max_simulation_time']) if sim_results['max_simulation_time'] is not None else 0.0

        st.session_state.scenario_results[scenario_name] = {
            'total_emissions_kg': total_emissions,
            'total_sim_time_hr': total_sim_time,
            'log': sim_results['log'],
            'segments': sim_results['segments'],
            're_route_events': sim_results['re_route_events'],
            'truck_config': trucks_cfg
        }
        return sim_results

# --- Main Content Area ---
st.title(page)

if page == "📊 Overview":
    st.header("Sustainable Logistics Digital Twin")
    st.markdown("""
        This dashboard presents a sophisticated digital twin prototype for sustainable logistics.
        It integrates advanced route optimization with dynamic simulation, considering real-time factors
        like traffic, weather, and grid carbon intensity across multiple global locations.
    """)

    if st.session_state.simulation_results and st.session_state.simulation_results['log']:
        log_df = pd.DataFrame(st.session_state.simulation_results['log'])
        total_deliveries = log_df["delivered"].sum()
        ev_trips = log_df[log_df["type"] == "EV"].shape[0]
        diesel_trips = log_df[log_df["type"] == "Diesel"].shape[0]
        
        avg_adjusted_time = log_df["adjusted_travel_time_hr"].mean() if not log_df.empty else 0
        total_emissions_kg = log_df["emissions_kg"].sum() if "emissions_kg" in log_df.columns else 0.0
        total_simulation_time = st.session_state.max_simulation_time

        st.subheader("🔍 Summary Insights")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Deliveries", int(total_deliveries))
        with col2:
            st.metric("EV Trips", ev_trips)
        with col3:
            st.metric("Diesel Trips", diesel_trips)
        
        col4, col5, col6 = st.columns(3)
        with col4:
            st.metric("Avg. Adj. Travel Time (hr)", f"{avg_adjusted_time:.2f}")
        with col5:
            st.metric("Total Sim Time (hr)", f"{total_simulation_time:.2f}")
        with col6:
            st.metric("Total Emissions (kg CO2)", f"{total_emissions_kg:.2f}")


        st.markdown("---")
        st.subheader("💡 Innovation in Action: Carbon-Aware Logistics")
        st.markdown(f"""
        The **Total Emissions (kg CO2)** metric for **{st.session_state.selected_country}** is a direct result of our unique carbon-aware simulation:

        * **EV Emissions aren't Zero:** For Electric Vehicles, emissions are dynamically calculated based on the **real-time (mocked) grid carbon intensity** at their location within {st.session_state.selected_country}. A "dirty" grid (higher carbon intensity) means higher effective CO2 emissions for EVs.
        * **Diesel Emissions are Fixed:** Diesel trucks have a constant emission rate per kilometer.
        * **Quantifiable Impact:** This allows you to immediately see the environmental cost of different fleet mixes and even implicitly, how operating EVs during different grid conditions could change overall emissions.

        **To truly understand the impact:** Visit the "⚖️ Scenario Comparison" page to run and compare different fleet configurations and see their impact on total emissions and time!
        """)

        st.markdown("""
        **Problem Solved & Innovation:**
        -   **Real-world Dynamic Simulation:** Simulates delivery operations accounting for live traffic, weather, and crucial grid carbon intensity for various global locations.
        -   **Optimized Routing:** Utilizes advanced algorithms (conceptually OR-Tools) for complex, multi-stop route optimization, providing efficient and realistic paths.
        -   **Sustainability Focus:** Highlights the impact of vehicle types (EV vs. Diesel) and carbon-aware scheduling on environmental footprint by quantifying CO2 emissions.
        -   **Interactive Decision Support:** Allows stakeholders to visualize "what-if" scenarios and gain actionable insights for greener, more efficient logistics.
        -   **Scalable Architecture:** Designed with modular components, ready for integration with streaming data and larger networks.
        """)
    else:
        st.info(f"Run a simulation for {st.session_state.selected_country} in the '🚚 Simulation & Animation' section to see insights.")

elif page == "🌐 Network & Optimization":
    st.header(f"Supply Chain Network Overview & Route Optimization for {st.session_state.selected_country}")
    st.write(f"Visualizing the nodes in your supply chain and the optimized route for {st.session_state.selected_country}.")

    st.subheader("Network Configuration")
    st.markdown(f"**Distribution Centers:** {len(network_df[network_df['type'] == 'dc'])}")
    st.markdown(f"**Stores:** {len(network_df[network_df['type'] == 'store'])}")
    st.markdown(f"**Total Nodes (in {st.session_state.selected_country}):** {len(network_df)}")
    st.markdown(f"**Optimization Algorithm:** Advanced TSP (conceptually OR-Tools for real-world scenarios)")

    if st.button("Compute Optimal Route", key="compute_route_btn"):
        if network_df.empty:
            st.warning("Cannot compute route: No network data for the selected country. Please check data/network.csv.")
            st.session_state.optimized_route = []
        elif len(network_df) <= 1:
            st.info("Only one node in the network or no valid route can be formed for the selected country. No complex route needed.")
            st.session_state.optimized_route = [network_df['node_id'].iloc[0]]
        else:
            with st.spinner("Computing optimal route... (using advanced TSP)"):
                st.session_state.optimized_route = solve_advanced_tsp(distance_matrix, node_id_to_index, index_to_node_id)
                if not st.session_state.optimized_route:
                    st.error("Route computation failed or resulted in an empty route. Please check your data and solver logic.")
                else:
                    st.success("Optimal route computed!")
    
    st.subheader(f"Supply Chain Network Map for {st.session_state.selected_country}")
    if not network_df.empty:
        bbox = calculate_bounding_box(network_df)
        st.pydeck_chart(plot_network_pydeck(network_df, st.session_state.optimized_route, bbox))
    else:
        st.warning(f"No network data loaded for {st.session_state.selected_country}. Please check data/network.csv.")

elif page == "🚚 Simulation & Animation":
    st.header(f"Delivery Simulation & Truck Animation for {st.session_state.selected_country}")
    st.write(f"Simulate multi-truck deliveries with real-time factor adjustments and visualize their movement within {st.session_state.selected_country}.")

    st.subheader("Simulation Controls")
    run_sim_disabled = not st.session_state.optimized_route or len(st.session_state.optimized_route) < 2
    run_sim_help = "Compute optimal route first (requires at least 2 nodes)." if run_sim_disabled else ""

    if st.button("Run Simulation", key="run_sim_btn", disabled=run_sim_disabled, help=run_sim_help):
        if not st.session_state.optimized_route or len(st.session_state.optimized_route) < 2:
            st.warning("Please compute an optimal route with at least two nodes first in the 'Network & Optimization' section.")
        else:
            current_sim_results = run_simulation_and_store(
                st.session_state.optimized_route,
                distance_matrix,
                node_id_to_index,
                index_to_node_id,
                demand_map_filtered,
                st.session_state.trucks_config
            )
            st.session_state.simulation_results = current_sim_results
            st.session_state.max_simulation_time = current_sim_results['max_simulation_time']
            st.session_state.simulation_time_slider = 0.0
            st.success("Simulation complete!")


    if st.session_state.simulation_results and not st.session_state.simulation_results['segments'].empty:
        segments_for_animation = st.session_state.simulation_results['segments']
        log_df_sim = pd.DataFrame(st.session_state.simulation_results['log'])
        re_route_events_df = pd.DataFrame(st.session_state.simulation_results['re_route_events'])

        st.session_state.simulation_time_slider = st.slider(
            "Simulation Time (hours)",
            0.0,
            st.session_state.max_simulation_time + 0.1,
            st.session_state.simulation_time_slider,
            step=0.1,
            key="animation_time_slider"
        )

        current_truck_positions = get_positions_at_time(segments_for_animation, st.session_state.simulation_time_slider, network_df)

        st.subheader("🚚 Current Simulation Factors")
        if current_truck_positions:
            for truck_pos in current_truck_positions:
                current_segment_info = log_df_sim[
                    (log_df_sim['truckId'] == truck_pos['id']) &
                    (log_df_sim['arrival_time_hr'] - log_df_sim['adjusted_travel_time_hr'] <= st.session_state.simulation_time_slider) &
                    (log_df_sim['arrival_time_hr'] > st.session_state.simulation_time_slider)
                ]
                
                if not current_segment_info.empty:
                    seg_data = current_segment_info.iloc[0]
                    carbon_text = f"Carbon Intensity: `{seg_data['carbon_factor']:.2f} gCO2/kWh`" if truck_pos['type'] == 'EV' else "N/A (Diesel)"
                    st.write(f"**{truck_pos['id']} ({truck_pos['type']})**: Traffic: `{seg_data['traffic_factor']:.2f}x` | Weather: `{seg_data['weather_condition']} ({seg_data['weather_factor']:.2f}x)` | {carbon_text}")
                else:
                    st.write(f"**{truck_pos['id']} ({truck_pos['type']})**: At stop or awaiting start.")
        else:
            st.info("No trucks currently moving. Adjust slider or run simulation.")
        st.markdown("---")

        bbox = calculate_bounding_box(network_df)
        
        view_state = pdk.ViewState(
            latitude=(bbox[0] + bbox[1]) / 2,
            longitude=(bbox[2] + bbox[3]) / 2,
            zoom=calculate_zoom_level(bbox),
            pitch=45,
        )

        node_layer = pdk.Layer(
            'ScatterplotLayer',
            data=network_df,
            get_position='[lon, lat]',
            get_color='[255, 0, 0, 160]' if network_df['type'].iloc[0] == 'dc' else '[255, 100, 100, 160]',
            get_radius=10000,
            pickable=True,
            auto_highlight=True,
            tooltip={"text": "{name}\n{type}"}
        )

        truck_color_map = {truck_conf['id']: truck_conf['color'] for truck_conf in st.session_state.trucks_config}
        
        truck_layer_data = pd.DataFrame(current_truck_positions)
        truck_layer = None
        if not truck_layer_data.empty:
            truck_layer = pdk.Layer(
                'ScatterplotLayer',
                data=truck_layer_data,
                get_position='[lon, lat]',
                get_color=lambda d: truck_color_map.get(d['id'], [255, 255, 255, 200]),
                get_radius=15000,
                pickable=True,
                auto_highlight=True,
                tooltip={"text": "Truck: {id}\nType: {type}"}
            )

        highlight_layer = highlight_impacted_segments(segments_for_animation, st.session_state.simulation_time_slider, st.session_state.trucks_config, log_df_sim, re_route_events_df)

        osm_tile_layer = pdk.Layer(
            "BitmapLayer",
            data=[
                {
                    "image": "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
                    "bounds": [-180, -85.05112878, 180, 85.05112878],
                }
            ],
            id="osm-base-map",
            opacity=0.8
        )

        all_layers = [osm_tile_layer, node_layer]
        if highlight_layer:
            all_layers.append(highlight_layer)
        if truck_layer:
            all_layers.append(truck_layer)

        st.pydeck_chart(pdk.Deck(
            initial_view_state=view_state,
            layers=all_layers,
            tooltip={"text": "{name}"}
        ))

        # --- Dynamic Re-route Table (as before) ---
        st.subheader("🔄 Dynamic Re-route Opportunities")
        if not re_route_events_df.empty:
            active_re_route_events = re_route_events_df[re_route_events_df['trigger_time_hr'] <= st.session_state.simulation_time_slider]
            
            if not active_re_route_events.empty:
                st.write("Below are potential re-route opportunities detected up to the current simulation time:")
                re_route_truck_ids = sorted(active_re_route_events['truckId'].unique().tolist())
                selected_re_route_truck = st.selectbox("Select Truck to Observe Re-routes", re_route_truck_ids, key="re_route_truck_selector")

                if selected_re_route_truck:
                    truck_re_routes = active_re_route_events[active_re_route_events['truckId'] == selected_re_route_truck]
                    
                    if not truck_re_routes.empty:
                        for idx, event in truck_re_routes.iterrows():
                            with st.expander(f"Re-route for {event['truckId']} from {event['original_from']} to {event['original_to']} (Triggered at {event['trigger_time_hr']:.2f} hr)"):
                                st.markdown(f"**Reason:** {event['reason']}")
                                st.markdown(f"Original Route Segment: `{event['original_from']} -> {event['original_to']}`")
                                
                                re_route_comparison_data = {
                                    'Metric': ['Emissions (kg CO2)', 'Cost (USD)', 'Time (hr)'],
                                    'Original Path': [event['original_emissions_kg'], event['original_cost_usd'], event['original_time_hr']],
                                    'Alternative Path': [event['alternative_emissions_kg'], event['alternative_cost_usd'], event['alternative_time_hr']]
                                }
                                comparison_table = pd.DataFrame(re_route_comparison_data).set_index('Metric')
                                st.table(comparison_table)

                                st.markdown(f"**Impact:**")
                                if event['emissions_change_kg'] > 0:
                                    st.success(f"Reduced Emissions by: `{event['emissions_change_kg']:.2f} kg CO2`")
                                else:
                                    st.warning(f"Increased Emissions by: `{abs(event['emissions_change_kg']):.2f} kg CO2`")

                                if event['cost_change_usd'] > 0:
                                    st.warning(f"Increased Cost by: `${event['cost_change_usd']:.2f}`")
                                else:
                                    st.success(f"Reduced Cost by: `${abs(event['cost_change_usd']):.2f}`")

                                if event['time_change_hr'] > 0:
                                    st.warning(f"Increased Time by: `{event['time_change_hr']:.2f} hr`")
                                else:
                                    st.success(f"Reduced Time by: `{abs(event['time_change_hr']):.2f} hr`")
                    else:
                        st.info(f"No re-route opportunities for {selected_re_route_truck} up to current time.")
                
            else:
                st.info("No re-route opportunities detected yet in the simulation up to current time.")
        else:
            st.info("No re-route opportunities detected in this simulation run. Check simulation parameters or data.")

        st.markdown("---") # Separator before final summary

        # --- NEW: Final Simulation Summary Section ---
        st.subheader("🏁 Final Simulation Summary")
        if not re_route_events_df.empty:
            st.markdown("All re-route opportunities detected during this simulation:")
            final_re_route_summary = []
            for idx, event in re_route_events_df.iterrows():
                final_re_route_summary.append({
                    'Truck': event['truckId'],
                    'Original Segment': f"{event['original_from']} -> {event['original_to']}",
                    'Reason': event['reason'],
                    'Emissions Change (kg CO2)': f"{event['emissions_change_kg']:.2f}",
                    'Cost Change (USD)': f"{event['cost_change_usd']:.2f}",
                    'Time Change (hr)': f"{event['time_change_hr']:.2f}"
                })
            st.dataframe(pd.DataFrame(final_re_route_summary), use_container_width=True)
        else:
            st.markdown("No re-route opportunities were detected during this simulation run. Here is the final planned route for each truck:")
            final_routes_summary = []
            for truck_id, truck_data in st.session_state.simulation_results['final_truck_states'].items():
                # Get the segments assigned to this truck from the full log
                truck_segments_log = log_df_sim[log_df_sim['truckId'] == truck_id]
                if not truck_segments_log.empty:
                    route_path = " -> ".join(truck_segments_log['from'].unique().tolist() + [truck_segments_log['to'].iloc[-1]])
                else:
                    route_path = "No segments assigned"
                
                final_routes_summary.append({
                    'Truck': truck_id,
                    'Type': truck_data['type'],
                    'Final Route': route_path,
                    'Total Distance (km)': f"{truck_data['total_distance_km']:.2f}",
                    'Total Time (hr)': f"{truck_data['total_adjusted_time_hr']:.2f}",
                    'Total Emissions (kg CO2)': f"{truck_data['total_emissions_kg']:.2f}",
                    'Total Cost (USD)': f"${truck_data['total_cost']:.2f}"
                })
            st.dataframe(pd.DataFrame(final_routes_summary), use_container_width=True)

    else:
        st.info(f"Run the simulation for {st.session_state.selected_country} to see the animation and re-route insights.")

elif page == "⚖️ Scenario Comparison":
    st.header("Scenario Comparison: Fleet Optimization & Sustainability")
    st.markdown("""
    Compare the overall impact of different fleet configurations or operational strategies on total emissions and simulation time.
    Use the '⚙️ Configuration' page to adjust truck settings, then run simulations from the '🚚 Simulation & Animation' page.
    Each successful simulation will be stored here for comparison.
    """)

    if not st.session_state.scenario_results:
        st.info("No scenarios to compare yet. Run at least one simulation from the '🚚 Simulation & Animation' page.")
    else:
        scenario_names = list(st.session_state.scenario_results.keys())
        st.subheader("Stored Scenarios")
        st.dataframe(pd.DataFrame([
            {'Scenario': name,
             'Total Emissions (kg CO2)': f"{data['total_emissions_kg']:.2f}",
             'Total Time (hr)': f"{data['total_sim_time_hr']:.2f}",
             'Fleet Config': ', '.join([f"{t['id']} ({t['type']})" for t in data['truck_config']])
            } for name, data in st.session_state.scenario_results.items()
        ]), use_container_width=True)

        st.subheader("Compare Scenarios Visually")
        if len(scenario_names) >= 2:
            col1, col2 = st.columns(2)
            scenario_1_name = col1.selectbox("Select Scenario 1", scenario_names, key="scenario_1_select")
            scenario_2_name = col2.selectbox("Select Scenario 2", scenario_names, key="scenario_2_select")

            if scenario_1_name and scenario_2_name:
                s1_data = st.session_state.scenario_results[scenario_1_name]
                s2_data = st.session_state.scenario_results[scenario_2_name]

                comparison_df = pd.DataFrame({
                    'Metric': ['Total Emissions (kg CO2)', 'Total Time (hr)'],
                    scenario_1_name: [s1_data['total_emissions_kg'], s1_data['total_sim_time_hr']],
                    scenario_2_name: [s2_data['total_emissions_kg'], s2_data['total_sim_time_hr']]
                }).set_index('Metric')

                st.dataframe(comparison_df)

                try:
                    import plotly.graph_objects as go
                    from plotly.subplots import make_subplots

                    fig = make_subplots(rows=1, cols=2, subplot_titles=("Total Emissions (kg CO2)", "Total Time (hr)"))

                    fig.add_trace(go.Bar(
                        name=scenario_1_name,
                        x=['Emissions'],
                        y=[s1_data['total_emissions_kg']],
                        marker_color='red'
                    ), row=1, col=1)
                    fig.add_trace(go.Bar(
                        name=scenario_2_name,
                        x=['Emissions'],
                        y=[s2_data['total_emissions_kg']],
                        marker_color='green' if s2_data['total_emissions_kg'] < s1_data['total_emissions_kg'] else 'orange'
                    ), row=1, col=1)

                    fig.add_trace(go.Bar(
                        name=scenario_1_name,
                        x=['Time'],
                        y=[s1_data['total_sim_time_hr']],
                        marker_color='red',
                        showlegend=False
                    ), row=1, col=2)
                    fig.add_trace(go.Bar(
                        name=scenario_2_name,
                        x=['Time'],
                        y=[s2_data['total_sim_time_hr']],
                        marker_color='green' if s2_data['total_sim_time_hr'] < s1_data['total_sim_time_hr'] else 'orange',
                        showlegend=False
                    ), row=1, col=2)
                    
                    fig.update_layout(title_text=f"Comparison: {scenario_1_name} vs {scenario_2_name}",
                                      barmode='group',
                                      height=400,
                                      xaxis={'categoryorder':'total ascending'},
                                      plot_bgcolor='#1a1a1a',
                                      paper_bgcolor='#0A0A0A',
                                      font_color='#FAFAFA'
                                      )
                    fig.update_xaxes(showgrid=False)
                    fig.update_yaxes(showgrid=True, gridcolor='#333333')

                    st.plotly_chart(fig, use_container_width=True)
                except ImportError:
                    st.warning("Install `plotly` to visualize scenario comparisons: `pip install plotly`")
        elif len(scenario_names) == 1:
            st.info("Add another simulation to compare scenarios.")
        
        if st.button("Clear All Scenarios", key="clear_scenarios_btn"):
            st.session_state.scenario_results = {}
            st.rerun()


elif page == "⚙️ Configuration":
    st.header("Configure Fleet and Simulation Parameters")
    st.write("Adjust truck types, speeds, and capacities.")

    st.subheader("Truck Fleet Configuration")
    for i, truck in enumerate(st.session_state.trucks_config):
        st.subheader(f"Truck {i+1}: {truck['id']}")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            truck['id'] = st.text_input("ID", truck['id'], key=f"truck_id_{i}")
        with col2:
            truck['type'] = st.selectbox("Type", ["EV", "Diesel"], index=0 if truck['type'] == "EV" else 1, key=f"truck_type_{i}")
        with col3:
            truck['speed'] = st.number_input("Speed (km/hr)", min_value=10, max_value=120, value=truck['speed'], step=5, key=f"truck_speed_{i}")
        with col4:
            truck['capacity'] = st.number_input("Capacity (units)", min_value=100, max_value=2000, value=truck['capacity'], step=50, key=f"truck_cap_{i}")
        with col5:
            default_emission_rate = 0.0 if truck['type'] == 'EV' else 0.26
            truck['emission_rate_kg_per_km'] = st.number_input(
                "Emissions (kg CO2/km)",
                min_value=0.0, max_value=1.0, value=truck.get('emission_rate_kg_per_km', default_emission_rate),
                step=0.01,
                format="%.2f",
                help="Direct CO2 emissions per km for Diesel. For EV, this represents inherent vehicle efficiency for converting grid carbon intensity (if consumption rate is high).",
                key=f"truck_emissions_{i}"
            )
        
        if truck['type'] == 'EV':
            st.session_state.trucks_config[i]['ev_consumption_kwh_per_km'] = st.number_input(
                "EV Consumption (kWh/km)",
                min_value=0.01, max_value=1.0, value=truck.get('ev_consumption_kwh_per_km', 0.2),
                step=0.01,
                format="%.2f",
                help="Energy consumption rate for EV trucks. Used with grid carbon intensity to calculate CO2 emissions.",
                key=f"ev_consumption_{i}"
            )

        if len(st.session_state.trucks_config) > 1:
            if st.button(f"Remove Truck {truck['id']}", key=f"remove_truck_{i}"):
                st.session_state.trucks_config.pop(i)
                st.rerun()

    if st.button("Add New Truck", key="add_truck_btn"):
        new_truck_id = f"Truck-{len(st.session_state.trucks_config) + 1:02d}"
        st.session_state.trucks_config.append(
            {'id': new_truck_id, 'type': 'EV', 'speed': 70, 'capacity': 600, 'color': [34, 197, 94], 'emission_rate_kg_per_km': 0.0, 'ev_consumption_kwh_per_km': 0.2}
        )
        st.rerun()

    st.subheader("API Key & Data Sources (Mocked for Demo)")
    st.markdown("""
    In a production environment, actual API keys for real-time data would be configured.
    For this hackathon prototype, all external API calls are **mocked** to ensure functionality without requiring live keys. This demonstrates the conceptual integration.
    """)

elif page == "📜 Raw Logs":
    st.header("Raw Simulation Logs")
    st.write("Detailed log of each segment simulated.")

    if st.session_state.simulation_results and st.session_state.simulation_results['log']:
        log_df_raw = pd.DataFrame(st.session_state.simulation_results['log'])
        st.download_button(
            label="Download Simulation Log as CSV",
            data=log_df_raw.to_csv(index=False).encode('utf-8'),
            file_name="greentwin_simulation_log.csv",
            mime="text/csv",
            key="download_log_btn"
        )
        st.dataframe(log_df_raw, use_container_width=True)
    else:
        st.info(f"Run a simulation for {st.session_state.selected_country} to see raw logs here.")
