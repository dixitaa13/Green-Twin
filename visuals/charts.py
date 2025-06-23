import plotly.graph_objects as go
import pandas as pd
import numpy as np


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
    

def build_truck_segments(log_df, node_coords_df):
    """
    From the simulation log DataFrame, build a DataFrame of segments:
    Each row: truck, start_time, end_time, start_lat, start_lon, end_lat, end_lon
    """
    segments = []
    # Group by truck
    for truck_id, group in log_df.groupby("Truck"):
        # Sort by Arrival Time to ensure order
        grp = group.sort_values("Arrival Time (hr)").reset_index(drop=True)
        # We need also the departure times: for first segment, start at time 0 from the first 'From'
        prev_time = 0.0
        # For each row in grp, we have arrival at 'To' at time grp.loc[i, "Arrival Time (hr)"]
        for idx, row in grp.iterrows():
            from_id = row["From"]
            to_id = row["To"]
            arrival_time = row["Arrival Time (hr)"]
            # Lookup coordinates
            from_row = node_coords_df[node_coords_df["id"] == from_id].iloc[0]
            to_row = node_coords_df[node_coords_df["id"] == to_id].iloc[0]
            lat1, lon1 = from_row["latitude"], from_row["longitude"]
            lat2, lon2 = to_row["latitude"], to_row["longitude"]
            segment = {
                "Truck": truck_id,
                "start_time": prev_time,
                "end_time": arrival_time,
                "start_lat": lat1,
                "start_lon": lon1,
                "end_lat": lat2,
                "end_lon": lon2
            }
            segments.append(segment)
            # After service_time at arrival, departure = arrival_time + service_time
            # But for interpolation of travel, we consider travel until arrival_time; next segment starts after service.
            # If you want to include service wait, you could add a stationary segment.
            service_time = row.get("Remaining Inventory", None)  # not used here
            # For next segment start_time, we assume departure = arrival_time + service_time. But our segments represent only travel.
            prev_time = arrival_time  # next segment starts from this time
        # End group
    seg_df = pd.DataFrame(segments)
    return seg_df
    

def get_positions_at_time(seg_df, t):
    """
    For each truck, determine its position at time t.
    - If t < first segment start_time: assume at initial location (could be DC)
    - If within a segment (start_time <= t <= end_time): interpolate between start and end coords
    - If t > last end_time: assume at final location (last 'To')
    Returns a DataFrame with columns: Truck, lat, lon
    """
    positions = []
    for truck_id, group in seg_df.groupby("Truck"):
        grp = group.sort_values("start_time")
        # Find segment where start_time <= t <= end_time
        seg = grp[(grp["start_time"] <= t) & (grp["end_time"] >= t)]
        if not seg.empty:
            row = seg.iloc[0]
            # Interpolate fraction
            duration = row["end_time"] - row["start_time"]
            if duration <= 0:
                frac = 1.0
            else:
                frac = (t - row["start_time"]) / duration
            lat = row["start_lat"] + frac * (row["end_lat"] - row["start_lat"])
            lon = row["start_lon"] + frac * (row["end_lon"] - row["start_lon"])
        else:
            # t not in any travel segment: either before first or after last or in a gap (service time)
            if t < grp["start_time"].min():
                # before first departure: position = first segment's start coords
                row0 = grp.iloc[0]
                lat, lon = row0["start_lat"], row0["start_lon"]
            elif t > grp["end_time"].max():
                # after last arrival: position = last segment's end coords
                row_last = grp.iloc[-1]
                lat, lon = row_last["end_lat"], row_last["end_lon"]
            else:
                # In a gap between segments: find the last segment with end_time < t
                prev_segs = grp[grp["end_time"] < t]
                if not prev_segs.empty:
                    last = prev_segs.iloc[-1]
                    lat, lon = last["end_lat"], last["end_lon"]
                else:
                    # Fallback
                    row0 = grp.iloc[0]
                    lat, lon = row0["start_lat"], row0["start_lon"]
        positions.append({"Truck": truck_id, "lat": lat, "lon": lon})
    pos_df = pd.DataFrame(positions)
    return pos_df



