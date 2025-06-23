import streamlit as st
from utils.api_helpers import load_network, create_graph, build_distance_matrix
from visuals.charts import plot_network
from optimization.route_solver import solve_tsp
from simulation.sim_core import multi_truck_simulation
import pydeck as pdk
from visuals.charts import build_truck_segments, get_positions_at_time

def main():
    st.set_page_config(page_title="GreenTwin Prototype", layout="wide")
    st.title("GreenTwin: Sustainable Logistics Prototype")
    
    # -------------------------------
    st.header("Step 2: Supply Chain Network")
    # -------------------------------

    df = load_network()
    G = create_graph(df)
    st.success(f"Loaded network with {len(G.nodes)} locations and {len(G.edges)} routes.")

    fig = plot_network(df, G)
    st.plotly_chart(fig, use_container_width=True)

    # -------------------------------
    st.header("Step 3: Route Optimization + Digital Twin Simulation")
    # -------------------------------

    if st.button("Compute Optimal Route and Simulate"):
        dist_matrix, node_ids = build_distance_matrix(G)
        route = solve_tsp(dist_matrix)

        if not route:
            st.error("Could not find a valid route.")
            return  # or just skip further code in this block

        # 1. Show the optimized route text
        st.success(f"Optimized Route (Node IDs): {route}")
        ordered_names = [df[df['id'] == node_ids[node]]['name'].values[0] for node in route]
        st.markdown("**→ Route:** " + " → ".join(ordered_names))

        # 2. Multi-Truck Simulation
        st.subheader("Step 4: Multi-Truck Simulation")
        routes = {
            "T1": route,
            "T2": route[::-1]  # Reverse route for second truck example
        }
        trucks = {
            "T1": {"type": "EV", "speed": 50},
            "T2": {"type": "Diesel", "speed": 40}
        }
        # Pass df (node_coords_df) for coordinate lookups in simulation
        log_df, total_time = multi_truck_simulation(routes, dist_matrix, node_ids, trucks, df)

        st.success(f"Total Simulation Time (Latest Arrival): {total_time} hours")
        st.dataframe(log_df)

        # Show per-truck completion times
        # e.g., bar chart of final arrival by truck
        # We can group by truck and plot max Arrival Time
        try:
            final_times = log_df.groupby("Truck")["Arrival Time (hr)"].max()
            st.bar_chart(final_times)
        except Exception:
            # In case column naming differs
            pass

        # 3. Build segments only after we have log_df
        seg_df = build_truck_segments(log_df, df)

        # 4. Animated Map Playback with Slider
        st.header("Step 5: Animated Route Playback")
        t = st.slider("Simulation Time (hours)", 0.0, float(total_time), 0.0, step=0.1)

        pos_df = get_positions_at_time(seg_df, t)

        if not pos_df.empty:
            # Center map view
            mid_lat = float(pos_df["lat"].mean())
            mid_lon = float(pos_df["lon"].mean())
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=pos_df,
                get_position='[lon, lat]',
                get_color='[200, 30, 0, 160]',
                get_radius=3000,  # adjust based on geographic scale
                pickable=True
            )
            view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=10)
            deck = pdk.Deck(layers=[layer], initial_view_state=view_state)
            st.pydeck_chart(deck)
            st.table(pos_df)
        else:
            st.write("No truck positions available at this time.")

        # 5. (Optional) TripsLayer animation
        if st.checkbox("Show animated path (TripsLayer)"):
            # Prepare trips_data
            trips_data = []
            for truck_id, group in seg_df.groupby("Truck"):
                group_sorted = group.sort_values("start_time")
                path = []
                for _, row in group_sorted.iterrows():
                    # Convert hours to seconds
                    start_ts = int(row["start_time"] * 3600)
                    end_ts = int(row["end_time"] * 3600)
                    path.append([row["start_lon"], row["start_lat"], start_ts])
                    path.append([row["end_lon"], row["end_lat"], end_ts])
                trips_data.append({"path": path, "truck": truck_id})

            t_sec = int(t * 3600)
            trips_layer = pdk.Layer(
                "TripsLayer",
                data=trips_data,
                get_path="path",
                get_tilt=15,
                get_color=[253, 128, 93],
                opacity=0.8,
                width_min_pixels=5,
                rounded=True,
                trail_length=600,  # seconds
                current_time=t_sec
            )
            deck2 = pdk.Deck(layers=[trips_layer], initial_view_state=view_state)
            st.pydeck_chart(deck2)

if __name__ == "__main__":
    main()
