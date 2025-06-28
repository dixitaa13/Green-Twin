import pydeck as pdk
import pandas as pd
import numpy as np

def calculate_bounding_box(network_df):
    """
    Calculates the bounding box (min_lat, max_lat, min_lon, max_lon)
    for a given set of nodes.
    """
    if network_df.empty:
        return (0, 0, 0, 0)
    
    min_lat = network_df['lat'].min()
    max_lat = network_df['lat'].max()
    min_lon = network_df['lon'].min()
    max_lon = network_df['lon'].max()
    
    return (min_lat, max_lat, min_lon, max_lon)

def calculate_zoom_level(bbox, map_width_px=1000, map_height_px=600):
    """
    Estimates a PyDeck zoom level based on a bounding box.
    This is a simplified heuristic and might need fine-tuning.
    """
    min_lat, max_lat, min_lon, max_lon = bbox
    
    lat_buffer = (max_lat - min_lat) * 0.1
    lon_buffer = (max_lon - min_lon) * 0.1
    min_lat -= lat_buffer
    max_lat += lat_buffer
    min_lon -= lon_buffer
    max_lon += lon_buffer

    if min_lat == max_lat: max_lat += 0.001
    if min_lon == max_lon: max_lon += 0.001

    EARTH_CIRCUMFERENCE = 40075017 # meters
    METERS_PER_PIXEL_ZOOM_0 = 78271.517

    width_meters = np.cos(np.radians((min_lat + max_lat) / 2)) * EARTH_CIRCUMFERENCE * (max_lon - min_lon) / 360
    height_meters = EARTH_CIRCUMFERENCE * (max_lat - min_lat) / 360

    if width_meters > height_meters:
        zoom = np.log2(METERS_PER_PIXEL_ZOOM_0 * map_width_px / width_meters)
    else:
        zoom = np.log2(METERS_PER_PIXEL_ZOOM_0 * map_height_px / height_meters)
    
    return max(0.5, min(zoom, 10))

def plot_network_pydeck(network_df, optimized_route_ids=[], bbox=None):
    """
    Generates a PyDeck chart for the supply chain network, including nodes and
    an optional optimized route, using OpenStreetMap as a base map.
    The map view state is adjusted based on the provided bounding box.
    """
    if bbox and bbox != (0,0,0,0):
        view_state = pdk.ViewState(
            latitude=(bbox[0] + bbox[1]) / 2,
            longitude=(bbox[2] + bbox[3]) / 2,
            zoom=calculate_zoom_level(bbox),
            pitch=45,
        )
    elif not network_df.empty:
        view_state = pdk.ViewState(
            latitude=network_df['lat'].mean(),
            longitude=network_df['lon'].mean(),
            zoom=1.5,
            pitch=45,
        )
    else:
        view_state = pdk.ViewState(latitude=0, longitude=0, zoom=1)

    route_data = []
    if optimized_route_ids and len(optimized_route_ids) > 1:
        for i in range(len(optimized_route_ids) - 1):
            from_node = network_df[network_df['node_id'] == optimized_route_ids[i]].iloc[0]
            to_node = network_df[network_df['node_id'] == optimized_route_ids[i+1]].iloc[0]
            route_data.append({
                'path': [[from_node['lon'], from_node['lat']], [to_node['lon'], to_node['lat']]],
                'from_id': from_node['node_id'],
                'to_id': to_node['node_id']
            })
    
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

    layers = [
        osm_tile_layer,
        pdk.Layer(
            'ScatterplotLayer',
            data=network_df,
            get_position='[lon, lat]',
            get_color='[255, 0, 0, 160]' if network_df['type'].iloc[0] == 'dc' else '[255, 100, 100, 160]',
            get_radius=10000,
            pickable=True,
            auto_highlight=True,
            tooltip={"text": "{name}\nType: {type}\nCountry: {country}"}
        )
    ]

    if route_data:
        layers.append(
            pdk.Layer(
                'PathLayer',
                data=route_data,
                get_path='path',
                get_color='[239, 68, 68, 200]',
                get_width=5,
                width_scale=1,
                width_min_pixels=2,
                pickable=True,
            )
        )

    return pdk.Deck(
        initial_view_state=view_state,
        layers=layers,
        tooltip={"text": "{name}"}
    )

# This function remains largely the same, but comments highlight its purpose
def build_truck_segments(simulation_log_df, network_df):
    """
    Transforms simulation log into a DataFrame of travel segments for animation.
    This DataFrame now contains all log details, which will be used for highlighting.
    """
    # simulation_core now returns a DataFrame for 'segments', so we don't need to rebuild it here.
    # The 'emissions_kg', 'carbon_factor', 'traffic_factor', 'weather_factor'
    # are in the log_df returned by sim_core. We will use the log_df for factor lookups.
    return simulation_log_df # simulation_core now returns log as DataFrame

def get_positions_at_time(segments_for_animation_df, current_time, network_df):
    """
    Calculates the interpolated positions of trucks at a given simulation time.
    """
    truck_current_positions = []
    
    unique_truck_ids = segments_for_animation_df['truckId'].unique()

    for truck_id in unique_truck_ids:
        truck_segments = segments_for_animation_df[segments_for_animation_df['truckId'] == truck_id]
        
        truck_segments = truck_segments.sort_values(by='startTime').reset_index(drop=True)
        
        current_segment = None
        for idx, segment_row in truck_segments.iterrows():
            # Check if current time is within this segment
            if current_time >= segment_row['startTime'] and current_time < segment_row['endTime']:
                current_segment = segment_row
                break
            # Check if current time is past this segment and this is the latest segment for the truck
            elif current_time >= segment_row['endTime'] and (idx + 1 == len(truck_segments) or current_time < truck_segments.iloc[idx+1]['startTime']):
                current_segment = segment_row
                # If segment is completed, truck is at its 'to' node
                truck_current_positions.append({
                    'id': truck_id,
                    'type': segment_row['type'],
                    'lat': segment_row['coordinates'][1][1],
                    'lon': segment_row['coordinates'][1][0]
                })
                break

        if current_segment is not None:
            # Ensure 'coordinates' is treated as a list, not a Series if pandas did something unexpected
            segment_path_coords = current_segment['coordinates'].item() if isinstance(current_segment['coordinates'], pd.Series) else current_segment['coordinates']

            from_lon, from_lat = segment_path_coords[0]
            to_lon, to_lat = segment_path_coords[1]
            
            segment_duration = current_segment['endTime'] - current_segment['startTime']

            if segment_duration > 0:
                progress = (current_time - current_segment['startTime']) / segment_duration
                progress = max(0, min(1, progress))

                current_lon = from_lon + (to_lon - from_lon) * progress
                current_lat = from_lat + (to_lat - from_lat) * progress
            else: # Instantaneous movement or start of simulation (if duration is 0)
                current_lon, current_lat = from_lon, from_lat
            
            if not any(t['id'] == truck_id for t in truck_current_positions):
                truck_current_positions.append({
                    'id': truck_id,
                    'type': current_segment['type'],
                    'lat': current_lat,
                    'lon': current_lon
                })
        else:
            if current_time < (truck_segments['startTime'].min() if not truck_segments.empty else 0):
                 dc_nodes = network_df[network_df['type'] == 'dc']
                 if not dc_nodes.empty:
                    start_node_coords = dc_nodes.iloc[0]
                    truck_current_positions.append({
                        'id': truck_id,
                        'type': truck_segments['type'].iloc[0] if not truck_segments.empty else 'EV',
                        'lat': start_node_coords['lat'],
                        'lon': start_node_coords['lon']
                    })
            elif current_time > (truck_segments['endTime'].max() if not truck_segments.empty else 0):
                 final_segment = truck_segments.iloc[-1]
                 final_path_coords = final_segment['coordinates'].item() if isinstance(final_segment['coordinates'], pd.Series) else final_segment['coordinates']

                 truck_current_positions.append({
                    'id': truck_id,
                    'type': final_segment['type'],
                    'lat': final_path_coords[1][1],
                    'lon': final_path_coords[1][0]
                })

    return truck_current_positions

def highlight_impacted_segments(segments_for_animation_df, current_time, trucks_config, log_df_sim): # Updated signature
    """
    Generates PyDeck PathLayer data for animated segments,
    with colors indicating high traffic or high carbon intensity.
    Now correctly uses segments_for_animation_df for coordinates and log_df_sim for factors.
    """
    segment_layers_data = []
    
    # Define thresholds for highlighting (these can be adjusted)
    HIGH_TRAFFIC_THRESHOLD = 1.3
    HIGH_CARBON_THRESHOLD = 350 # gCO2/kWh

    for truck_config in trucks_config:
        # Filter segments data for the current truck from segments_for_animation_df
        truck_segments_data = segments_for_animation_df[segments_for_animation_df['truckId'] == truck_config['id']]
        
        for idx, segment_row in truck_segments_data.iterrows():
            # Find the corresponding log entry for factor information
            # We match by truckId and the approximate start time of the segment
            # This assumes that log_df_sim contains corresponding entries for each segment in segments_for_animation_df
            matching_log_entries = log_df_sim[
                (log_df_sim['truckId'] == segment_row['truckId']) &
                (np.isclose(log_df_sim['arrival_time_hr'] - log_df_sim['adjusted_travel_time_hr'], segment_row['startTime'], atol=0.01))
            ]

            log_entry_for_segment = matching_log_entries.iloc[0] if not matching_log_entries.empty else None

            # Get the path coordinates for this segment from segment_row
            segment_coords = segment_row['coordinates'].item() if isinstance(segment_row['coordinates'], pd.Series) else segment_row['coordinates']

            is_active_segment = segment_row['startTime'] <= current_time and current_time < segment_row['endTime']
            
            segment_color = truck_config['color'] + [200]

            # Apply highlighting based on factor values from log_entry_for_segment
            if log_entry_for_segment is not None:
                is_high_carbon = log_entry_for_segment['type'] == 'EV' and log_entry_for_segment['carbon_factor'] > HIGH_CARBON_THRESHOLD
                is_high_traffic = log_entry_for_segment['traffic_factor'] > HIGH_TRAFFIC_THRESHOLD

                if is_high_carbon:
                    segment_color = [255, 0, 255, 250] # Magenta for high carbon EV segments
                elif is_high_traffic:
                    segment_color = [255, 140, 0, 250] # Orange for high traffic segments
            
            opacity = 200 if is_active_segment else 80
            final_color = segment_color[:-1] + [opacity]

            current_path = []
            if segment_row['startTime'] <= current_time:
                if current_time < segment_row['endTime']:
                    progress = (current_time - segment_row['startTime']) / (segment_row['endTime'] - segment_row['startTime'])
                    current_lon = segment_coords[0][0] + (segment_coords[1][0] - segment_coords[0][0]) * progress
                    current_lat = segment_coords[0][1] + (segment_coords[1][1] - segment_coords[0][1]) * progress
                    current_path = [segment_coords[0], [current_lon, current_lat]]
                else:
                    current_path = segment_coords
            
            if current_path:
                factor_info = "N/A"
                if log_entry_for_segment is not None:
                     factor_info = f"Traffic: {log_entry_for_segment['traffic_factor']:.2f}x, Carbon: {log_entry_for_segment['carbon_factor']:.2f} gCO2/kWh"
                
                segment_layers_data.append({
                    'path': current_path,
                    'color': final_color,
                    'truckId': segment_row['truckId'],
                    'factor_info': factor_info
                })
    
    if segment_layers_data:
        return pdk.Layer(
            'PathLayer',
            data=segment_layers_data,
            get_path='path',
            get_color='color',
            get_width=8,
            width_scale=1,
            width_min_pixels=3,
            pickable=True,
            tooltip={"text": "{truckId}\nFactors: {factor_info}"}
        )
    return None
