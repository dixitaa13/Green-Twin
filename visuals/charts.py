import plotly.graph_objects as go

def plot_network(df, G):
    fig = go.Figure()

    # Plot nodes
    for _, row in df.iterrows():
        color = "blue" if row["type"] == "dc" else "green"
        fig.add_trace(go.Scattergeo(
            lat=[row["latitude"]],
            lon=[row["longitude"]],
            text=row["name"],
            mode='markers+text',
            marker=dict(size=10, color=color),
            name=row["name"]
        ))

    # Plot edges (routes)
    for u, v, d in G.edges(data=True):
        lat1 = G.nodes[u]['pos'][0]
        lon1 = G.nodes[u]['pos'][1]
        lat2 = G.nodes[v]['pos'][0]
        lon2 = G.nodes[v]['pos'][1]
        fig.add_trace(go.Scattergeo(
            lat=[lat1, lat2],
            lon=[lon1, lon2],
            mode='lines',
            line=dict(width=1, color='gray'),
            opacity=0.6,
            showlegend=False
        ))

    fig.update_layout(
        title='Supply Chain Network',
        geo=dict(
            scope='asia',
            projection_type='natural earth',
            showland=True,
            landcolor='rgb(243, 243, 243)',
            countrycolor='rgb(204, 204, 204)',
        ),
        height=600
    )

    return fig

