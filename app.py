import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
from datetime import datetime, timedelta

# Import custom modules
from utils.api_helpers import load_network, create_graph, build_distance_matrix, get_mock_traffic_factor, get_mock_weather_factor, get_mock_carbon_intensity
from optimization.route_solver import solve_advanced_tsp
from simulation.sim_core import multi_truck_simulation
from visuals.charts import plot_network_pydeck, build_truck_segments, get_positions_at_time

# --- Streamlit Page Configuration ---
# Ensure this is at the very top of your script
st.set_page_config(
    page_title="GreenTwin: Sustainable Logistics Digital Twin",
    layout="wide", # Use wide layout for more space
    initial_sidebar_state="expanded",
    # Theming is handled by .streamlit/config.toml, but explicit icons can be set here
)

# --- Global Data Loading (Cached to avoid re-running on every interaction) ---
@st.cache_data
def load_all_data():
    """Loads network and demand data."""
    try:
        network_df = load_network('data/network.csv')
        demand_df = pd.read_csv('data/demand.csv')
        # Convert demand_df to a dictionary for easy lookup
        demand_map = demand_df.set_index('node_id')['demand'].to_dict()
        return network_df, demand_map
    except FileNotFoundError:
        st.error("Error: 'network.csv' or 'demand.csv' not found in the 'data/' directory. Please ensure these files are in the 'data/' folder.")
        st.stop() # Stop the app if crucial files are missing

network_df, demand_map = load_all_data()
G = create_graph(network_df)
distance_matrix, node_id_to_index, index_to_node_id = build_distance_matrix(G)

# --- Session State Initialization ---
# This is crucial for maintaining state across page changes in Streamlit
if 'trucks_config' not in st.session_state:
    st.session_state.trucks_config = [
        {'id': 'EV-01', 'type': 'EV', 'speed': 60, 'capacity': 500, 'color': [34, 197, 94]}, # Tailwind green-500
        {'id': 'Diesel-01', 'type': 'Diesel', 'speed': 80, 'capacity': 700, 'color': [234, 179, 8]}, # Tailwind yellow-500
    ]
if 'optimized_route' not in st.session_state:
    st.session_state.optimized_route = []
if 'simulation_results' not in st.session_state:
    st.session_state.simulation_results = None
if 'max_simulation_time' not in st.session_state:
    st.session_state.max_simulation_time = 0.0
if 'simulation_time_slider' not in st.session_state:
    st.session_state.simulation_time_slider = 0.0

# --- Sidebar Navigation ---
st.sidebar.title("GreenTwin Dashboard")
st.sidebar.markdown("---")

# Using a selectbox for main navigation, acting like dropdown sections
page = st.sidebar.selectbox(
    "Navigate Sections",
    ("📊 Overview", "🌐 Network & Optimization", "🚚 Simulation & Animation", "⚙️ Configuration", "📜 Raw Logs"),
    key="main_nav_selector"
)

st.sidebar.markdown("---")
st.sidebar.info("Developed for a National Level Hackathon")

# --- Main Content Area ---
st.title(page) # Display current page title

if page == "📊 Overview":
    st.header("Sustainable Logistics Digital Twin")
    st.markdown("""
        This dashboard presents a sophisticated digital twin prototype for sustainable logistics.
        It integrates advanced route optimization with dynamic simulation, considering real-time factors
        like traffic, weather, and grid carbon intensity across multiple global locations.
    """)

    # Display summary insights if simulation results are available
    if st.session_state.simulation_results and st.session_state.simulation_results['log']:
        log_df = pd.DataFrame(st.session_state.simulation_results['log'])
        total_deliveries = log_df["delivered"].sum()
        ev_trips = log_df[log_df["type"] == "EV"].shape[0]
        diesel_trips = log_df[log_df["type"] == "Diesel"].shape[0]
        # Calculate average adjusted travel time
        avg_adjusted_time = 0
        if not log_df.empty:
            avg_adjusted_time = log_df["adjusted_travel_time_hr"].mean()

        total_simulation_time = st.session_state.max_simulation_time

        st.subheader("🔍 Summary Insights")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total Deliveries", int(total_deliveries))
        with col2:
            st.metric("EV Trips", ev_trips)
        with col3:
            st.metric("Diesel Trips", diesel_trips)
        with col4:
            st.metric("Avg. Adj. Travel Time (hr)", f"{avg_adjusted_time:.2f}")
        with col5:
            st.metric("Total Sim Time (hr)", f"{total_simulation_time:.2f}")

        st.markdown("""
        **Problem Solved & Innovation:**
        - **Real-world Dynamic Simulation:** Simulates delivery operations accounting for live traffic, weather, and crucial grid carbon intensity for various global locations.
        - **Optimized Routing:** Utilizes advanced algorithms (conceptually OR-Tools) for complex, multi-stop route optimization, providing efficient and realistic paths.
        - **Sustainability Focus:** Highlights the impact of vehicle types (EV vs. Diesel) and carbon-aware scheduling on environmental footprint.
        - **Interactive Decision Support:** Allows stakeholders to visualize "what-if" scenarios and gain actionable insights for greener, more efficient logistics.
        - **Scalable Architecture:** Designed with modular components, ready for integration with streaming data and larger networks.
        """)
    else:
        st.info("Run a simulation in the 'Simulation & Animation' section to see insights.")

elif page == "🌐 Network & Optimization":
    st.header("Supply Chain Network Overview & Route Optimization")
    st.write("Visualizing the nodes in your supply chain and the optimized route.")

    st.subheader("Network Configuration")
    st.markdown(f"**Distribution Centers:** {len(network_df[network_df['type'] == 'dc'])}")
    st.markdown(f"**Stores:** {len(network_df[network_df['type'] == 'store'])}")
    st.markdown(f"**Total Nodes:** {len(network_df)}")
    st.markdown(f"**Optimization Algorithm:** Advanced TSP (conceptually OR-Tools for real-world scenarios)")

    # Button to trigger optimization
    if st.button("Compute Optimal Route", key="compute_route_btn"):
        if network_df.empty:
            st.warning("Cannot compute route: Network data is empty. Please check data/network.csv.")
        elif len(network_df) <= 1:
            st.info("Only one node in the network or no valid route can be formed. No complex route needed.")
            st.session_state.optimized_route = [network_df['node_id'].iloc[0]] if not network_df.empty else []
        else:
            with st.spinner("Computing optimal route... (using advanced TSP)"):
                st.session_state.optimized_route = solve_advanced_tsp(distance_matrix, node_id_to_index, index_to_node_id)
                if not st.session_state.optimized_route:
                    st.error("Route computation failed or resulted in an empty route. Please check your data and solver logic.")
                else:
                    st.success("Optimal route computed!")

    # Display the map with nodes and optimized route
    st.subheader("Supply Chain Network Map")
    if not network_df.empty:
        st.pydeck_chart(plot_network_pydeck(network_df, st.session_state.optimized_route))
    else:
        st.warning("No network data loaded. Please check data/network.csv.")

elif page == "🚚 Simulation & Animation":
    st.header("Delivery Simulation & Truck Animation")
    st.write("Simulate multi-truck deliveries with real-time factor adjustments and visualize their movement.")

    st.subheader("Simulation Controls")
    # Conditionally enable the simulation button
    run_sim_disabled = not st.session_state.optimized_route or len(st.session_state.optimized_route) < 2
    run_sim_help = "Compute optimal route first (requires at least 2 nodes)." if run_sim_disabled else ""

    if st.button("Run Simulation", key="run_sim_btn", disabled=run_sim_disabled, help=run_sim_help):
        if not st.session_state.optimized_route or len(st.session_state.optimized_route) < 2:
            st.warning("Please compute an optimal route with at least two nodes first in the 'Network & Optimization' section.")
        else:
            with st.spinner("Running simulation with real-time factors..."):
                sim_results = multi_truck_simulation(
                    st.session_state.optimized_route,
                    distance_matrix,
                    node_id_to_index,
                    index_to_node_id,
                    demand_map,
                    st.session_state.trucks_config,
                    get_mock_traffic_factor, # Pass mock API functions
                    get_mock_weather_factor,
                    get_mock_carbon_intensity
                )
                st.session_state.simulation_results = sim_results
                st.session_state.max_simulation_time = sim_results['max_simulation_time']
                st.session_state.simulation_time_slider = 0.0 # Reset slider
                st.success("Simulation complete!")

    if st.session_state.simulation_results and not st.session_state.simulation_results['segments'].empty: # Check if segments DataFrame is not empty
        segments_for_animation = st.session_state.simulation_results['segments']

        # Slider for animation
        st.session_state.simulation_time_slider = st.slider(
            "Simulation Time (hours)",
            0.0,
            st.session_state.max_simulation_time + 0.1, # Add a small buffer
            st.session_state.simulation_time_slider,
            step=0.1,
            key="animation_time_slider"
        )

        current_truck_positions = get_positions_at_time(segments_for_animation, st.session_state.simulation_time_slider, network_df)

        # Pydeck Layers for animation
        view_state = pdk.ViewState(
            latitude=network_df['lat'].mean(),
            longitude=network_df['lon'].mean(),
            zoom=1.5,
            pitch=45,
        )

        # Layer for static nodes
        node_layer = pdk.Layer(
            'ScatterplotLayer',
            data=network_df,
            get_position='[lon, lat]',
            get_color='[255, 0, 0, 160]' if network_df['type'].iloc[0] == 'dc' else '[255, 100, 100, 160]',
            get_radius=10000, # Radius in meters
            pickable=True,
            auto_highlight=True,
            tooltip={"text": "{name}\n{type}"}
        )

        # Layer for animated trucks
        truck_color_map = {truck_conf['id']: truck_conf['color'] for truck_conf in st.session_state.trucks_config}
        
        # Ensure current_truck_positions is a DataFrame for PyDeck
        truck_layer_data = pd.DataFrame(current_truck_positions)
        if not truck_layer_data.empty: # Only create layer if there are positions
            truck_layer = pdk.Layer(
                'ScatterplotLayer',
                data=truck_layer_data,
                get_position='[lon, lat]',
                get_color=lambda d: truck_color_map.get(d['id'], [255, 255, 255, 200]), # Use configured color, default to white
                get_radius=15000,
                pickable=True,
                auto_highlight=True,
                tooltip={"text": "Truck: {id}\nType: {type}"}
            )
        else:
            truck_layer = None # No truck layer if no positions

        # Layer for animated segments (trails)
        segment_layers = []
        if not segments_for_animation.empty: # Only process if segments DataFrame is not empty
            for truck_config in st.session_state.trucks_config:
                # Filter DataFrame rows using boolean indexing
                truck_segments_data = segments_for_animation[segments_for_animation['truckId'] == truck_config['id']]
                
                # Filter segments that are active up to the current simulation time
                active_segments_data = []
                for idx, seg in truck_segments_data.iterrows(): # Iterate over rows of filtered DataFrame
                    if seg['startTime'] <= st.session_state.simulation_time_slider:
                        # Calculate end position based on current time if segment is ongoing
                        if st.session_state.simulation_time_slider < seg['endTime']:
                            progress = (st.session_state.simulation_time_slider - seg['startTime']) / (seg['endTime'] - seg['startTime'])
                            current_lon = seg['coordinates'][0][0] + (seg['coordinates'][1][0] - seg['coordinates'][0][0]) * progress
                            current_lat = seg['coordinates'][0][1] + (seg['coordinates'][1][1] - seg['coordinates'][0][1]) * progress
                            active_segments_data.append({
                                'path': [seg['coordinates'][0], [current_lon, current_lat]],
                                'color': truck_config['color'] + [200], # Add alpha for vividness
                            })
                        else:
                            active_segments_data.append({
                                'path': seg['coordinates'],
                                'color': truck_config['color'] + [200],
                            })
                
                if active_segments_data: # Only add layer if there's data for it
                    segment_layers.append(
                        pdk.Layer(
                            'PathLayer',
                            data=active_segments_data,
                            get_path='path',
                            get_color='color',
                            get_width=5,
                            width_scale=1,
                            width_min_pixels=2,
                            pickable=True,
                        )
                    )

        # OSM base map is now handled inside plot_network_pydeck
        # We need to explicitly add the OSM layer to the simulation chart too for consistency
        osm_tile_layer = pdk.Layer(
            "BitmapLayer",
            data=[
                {
                    "image": "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
                    "bounds": [-180, -85.05112878, 180, 85.05112878], # Global bounds
                }
            ],
            id="osm-base-map",
            opacity=0.8 # Adjust opacity as needed
        )

        all_layers = [osm_tile_layer, node_layer]
        if truck_layer: # Add truck layer only if it exists
            all_layers.append(truck_layer)
        all_layers.extend(segment_layers) # Add segment layers

        st.pydeck_chart(pdk.Deck(
            initial_view_state=view_state,
            layers=all_layers,
            tooltip={"text": "{name}"}
        ))
    else:
        st.info("Run the simulation to see the animation.")


elif page == "⚙️ Configuration":
    st.header("Configure Fleet and Simulation Parameters")
    st.write("Adjust truck types, speeds, and capacities.")

    st.subheader("Truck Fleet Configuration")
    for i, truck in enumerate(st.session_state.trucks_config):
        st.subheader(f"Truck {i+1}: {truck['id']}")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            # Ensuring unique keys for text_input
            truck['id'] = st.text_input("ID", truck['id'], key=f"truck_id_{i}")
        with col2:
            truck['type'] = st.selectbox("Type", ["EV", "Diesel"], index=0 if truck['type'] == "EV" else 1, key=f"truck_type_{i}")
        with col3:
            truck['speed'] = st.number_input("Speed (km/hr)", min_value=10, max_value=120, value=truck['speed'], step=5, key=f"truck_speed_{i}")
        with col4:
            truck['capacity'] = st.number_input("Capacity (units)", min_value=100, max_value=2000, value=truck['capacity'], step=50, key=f"truck_cap_{i}")
        
        # Add a remove button for each truck (except if only one remains)
        if len(st.session_state.trucks_config) > 1:
            if st.button(f"Remove Truck {truck['id']}", key=f"remove_truck_{i}"):
                st.session_state.trucks_config.pop(i)
                st.rerun() # Rerun to update the list

    if st.button("Add New Truck", key="add_truck_btn"):
        new_truck_id = f"Truck-{len(st.session_state.trucks_config) + 1:02d}"
        st.session_state.trucks_config.append(
            {'id': new_truck_id, 'type': 'EV', 'speed': 70, 'capacity': 600, 'color': [34, 197, 94]} # Default color for new EV truck
        )
        st.rerun() # Rerun to show the new truck

    st.subheader("API Key & Data Sources (Mocked for Demo)")
    st.markdown("""
    In a production environment, you would configure actual API keys for:
    - **Google Maps Directions API:** For accurate travel times and traffic data.
    - **OpenWeatherMap API:** For real-time weather conditions.
    - **ElectricityMap / WattTime API:** For grid carbon intensity at specific locations/times for EV optimization.
    
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
        st.info("Run a simulation to see raw logs here.")
