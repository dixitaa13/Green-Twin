import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
from datetime import datetime, timedelta

# Import custom modules
# Ensure calculate_zoom_level is explicitly imported here
from utils.api_helpers import load_network, create_graph, build_distance_matrix, get_mock_traffic_factor, get_mock_weather_factor, get_mock_carbon_intensity
from optimization.route_solver import solve_advanced_tsp
from simulation.sim_core import multi_truck_simulation
from visuals.charts import plot_network_pydeck, get_positions_at_time, calculate_bounding_box, calculate_zoom_level # ALL NECESSARY IMPORTS HERE

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="GreenTwin: Sustainable Logistics Digital Twin",
    layout="wide", # Use wide layout for more space
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
        st.stop() # Stop the app if crucial files are missing

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
    ("📊 Overview", "🌐 Network & Optimization", "🚚 Simulation & Animation", "⚙️ Configuration", "📜 Raw Logs"),
    key="main_nav_selector"
)

st.sidebar.markdown("---")
st.sidebar.info("Developed for a National Level Hackathon")

# --- Filter Data Based on Selected Country ---
network_df = full_network_df[full_network_df['country'] == st.session_state.selected_country].copy()
# Filter demand map to include only nodes present in the current country's network_df
country_node_ids = network_df['node_id'].tolist()
demand_map_filtered = {k: v for k, v in full_demand_map.items() if k in country_node_ids}

G = create_graph(network_df)
distance_matrix, node_id_to_index, index_to_node_id = build_distance_matrix(G)


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

        **Try this:** Go to "⚙️ Configuration", adjust an EV's "EV Consumption (kWh/km)" or a Diesel truck's "Emissions (kg CO2/km)", then re-run the simulation in the '🚚 Simulation & Animation' section and observe the impact on total emissions! You can also switch countries to see how different geographies with potentially different simulated grid intensities might affect results.
        """)

        st.markdown("""
        **Problem Solved & Innovation:**
        - **Real-world Dynamic Simulation:** Simulates delivery operations accounting for live traffic, weather, and crucial grid carbon intensity for various global locations.
        - **Optimized Routing:** Utilizes advanced algorithms (conceptually OR-Tools) for complex, multi-stop route optimization, providing efficient and realistic paths.
        - **Sustainability Focus:** Highlights the impact of vehicle types (EV vs. Diesel) and carbon-aware scheduling on environmental footprint by quantifying CO2 emissions.
        - **Interactive Decision Support:** Allows stakeholders to visualize "what-if" scenarios and gain actionable insights for greener, more efficient logistics.
        - **Scalable Architecture:** Designed with modular components, ready for integration with streaming data and larger networks.
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
        # Pass the calculated bounding box for the current country
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
            with st.spinner("Running simulation with real-time factors..."):
                sim_results = multi_truck_simulation(
                    st.session_state.optimized_route,
                    distance_matrix,
                    node_id_to_index,
                    index_to_node_id,
                    demand_map_filtered, # Use filtered demand map
                    st.session_state.trucks_config,
                    get_mock_traffic_factor,
                    get_mock_weather_factor,
                    get_mock_carbon_intensity
                )
                st.session_state.simulation_results = sim_results
                st.session_state.max_simulation_time = sim_results['max_simulation_time']
                st.session_state.simulation_time_slider = 0.0
                st.success("Simulation complete!")

    if st.session_state.simulation_results and not st.session_state.simulation_results['segments'].empty:
        segments_for_animation = st.session_state.simulation_results['segments']
        log_df_sim = pd.DataFrame(st.session_state.simulation_results['log']) # For current factors lookup

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
                    # Make output more readable regarding carbon factor
                    carbon_text = f"Carbon Intensity: `{seg_data['carbon_factor']:.2f} gCO2/kWh`" if truck_pos['type'] == 'EV' else "N/A (Diesel)"
                    st.write(f"**{truck_pos['id']} ({truck_pos['type']})**: Traffic: `{seg_data['traffic_factor']:.2f}x` | Weather: `{seg_data['weather_condition']} ({seg_data['weather_factor']:.2f}x)` | {carbon_text}")
                else:
                    st.write(f"**{truck_pos['id']} ({truck_pos['type']})**: At stop or awaiting start.")
        else:
            st.info("No trucks currently moving. Adjust slider or run simulation.")
        st.markdown("---")

        # Calculate bounding box for current country for Pydeck view
        bbox = calculate_bounding_box(network_df)
        
        # Pydeck Layers for animation
        view_state = pdk.ViewState(
            latitude=(bbox[0] + bbox[1]) / 2, # Center lat
            longitude=(bbox[2] + bbox[3]) / 2, # Center lon
            zoom=calculate_zoom_level(bbox), # Dynamic zoom
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

        segment_layers = []
        if not segments_for_animation.empty:
            for truck_config in st.session_state.trucks_config:
                truck_segments_data = segments_for_animation[segments_for_animation['truckId'] == truck_config['id']]
                
                active_segments_data = []
                for idx, seg in truck_segments_data.iterrows():
                    if seg['startTime'] <= st.session_state.simulation_time_slider:
                        if st.session_state.simulation_time_slider < seg['endTime']:
                            progress = (st.session_state.simulation_time_slider - seg['startTime']) / (seg['endTime'] - seg['startTime'])
                            current_lon = seg['coordinates'][0][0] + (seg['coordinates'][1][0] - seg['coordinates'][0][0]) * progress
                            current_lat = seg['coordinates'][0][1] + (seg['coordinates'][1][1] - seg['coordinates'][0][1]) * progress
                            active_segments_data.append({
                                'path': [seg['coordinates'][0], [current_lon, current_lat]],
                                'color': truck_config['color'] + [200],
                            })
                        else:
                            active_segments_data.append({
                                'path': seg['coordinates'],
                                'color': truck_config['color'] + [200],
                            })
                
                if active_segments_data:
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
        if truck_layer:
            all_layers.append(truck_layer)
        all_layers.extend(segment_layers)

        st.pydeck_chart(pdk.Deck(
            initial_view_state=view_state,
            layers=all_layers,
            tooltip={"text": "{name}"}
        ))
    else:
        st.info(f"Run the simulation for {st.session_state.selected_country} to see the animation.")


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
                help="Direct CO2 emissions per km for Diesel. For EV, this represents inherent vehicle efficiency for converting grid carbon intensity.",
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
        st.info(f"Run a simulation for {st.session_state.selected_country} to see raw logs here.")
