import streamlit as st
from utils.api_helpers import load_network, create_graph
from visuals.charts import plot_network

def main():
    st.set_page_config(page_title="GreenTwin Prototype", layout="wide")
    st.title("GreenTwin: Sustainable Logistics Prototype")
    
    st.header("Step 2: Supply Chain Network")

    # Load and plot graph
    df = load_network()
    G = create_graph(df)
    st.success("Loaded network with {} locations and {} routes.".format(len(G.nodes), len(G.edges)))

    fig = plot_network(df, G)
    st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()
