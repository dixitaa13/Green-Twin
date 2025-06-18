import streamlit as st
from utils.api_helpers import load_network, create_graph, build_distance_matrix
from visuals.charts import plot_network
from optimization.route_solver import solve_tsp

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
    st.header("Step 3: Route Optimization")
    # -------------------------------

    if st.button("Compute Optimal Route"):
        dist_matrix, node_ids = build_distance_matrix(G)
        route = solve_tsp(dist_matrix)

        if route:
            st.success(f"Optimized Route (Node IDs): {route}")
            ordered_names = [df[df['id'] == node_ids[node]]['name'].values[0] for node in route]
            st.markdown("**→ Route:** " + " → ".join(ordered_names))
        else:
            st.error("Could not find a valid route.")

if __name__ == "__main__":
    main()
