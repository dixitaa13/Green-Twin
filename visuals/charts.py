import pydeck as pdk
import pandas as pd
import numpy as np

def calculate_bounding_box(network_df):
    """
    Calculates the bounding box (min_lat, max_lat, min_lon, max_lon)
    for a given set of nodes.
    """
    if network_df.empty:
        return (0, 0, 0, 0) # Default if no data
    
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
    
    # Add a small buffer to the bounding box
    lat_buffer = (max_lat - min_lat) * 0.1
    lon_buffer = (max_lon - min_lon) * 0.1
    min_lat -= lat_buffer
    max_lat += lat_buffer
    min_lon -= lon_buffer
    max_lon += lon_buffer

    # Handle single point or very small bounds to avoid division by zero or extreme zoom
    if min_lat == max_lat: max_lat += 0.001
    if min_lon == max_lon: max_lon += 0.001

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

def plot_network_pydeck(network_df, optimized_route_ids=[], bbox=None):
    """
    Generates a PyDeck chart for the supply chain network, including nodes and
    an optional optimized route, using OpenStreetMap as a base map.
    The map view state is adjusted based on the provided bounding box.
    """
    # Calculate initial view state based on bbox or network_df mean
    if bbox and bbox != (0,0,0,0):
        view_state = pdk.ViewState(
            latitude=(bbox[0] + bbox[1]) / 2, # Center lat
            longitude=(bbox[2] + bbox[3]) / 2, # Center lon
            zoom=calculate_zoom_level(bbox), # Dynamic zoom based on bbox
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

def build_truck_segments(simulation_log_df, network_df):
    """
    Transforms simulation log into a DataFrame of travel segments for animation.
    """
    segments = []
    node_coords_map = network_df.set_index('node_id')[['lat', 'lon']].to_dict('index')

    for index, row in simulation_log_df.iterrows():
        from_coords = node_coords_map[row['from']]
        to_coords = node_coords_map[row['to']]
        
        segments.append({
            'truckId': row['truckId'],
            'type': row['type'],
            'coordinates': [[from_coords['lon'], from_coords['lat']],
                     [to_coords['lon'], to_coords['lat']]],
            'startTime': row['arrival_time_hr'] - row['adjusted_travel_time_hr'],
            'endTime': row['arrival_time_hr']
        })
    return pd.DataFrame(segments)

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
            if current_time >= segment_row['startTime'] and current_time < segment_row['endTime']:
                current_segment = segment_row
                break
            elif current_time >= segment_row['endTime'] and (idx + 1 == len(truck_segments) or current_time < truck_segments.iloc[idx+1]['startTime']):
                current_segment = segment_row
                truck_current_positions.append({
                    'id': truck_id,
                    'type': segment_row['type'],
                    'lat': segment_row['coordinates'][1][1],
                    'lon': segment_row['coordinates'][1][0]
                })
                break

        if current_segment is not None:
            segment_path_coords = current_segment['coordinates'].item() if isinstance(current_segment['coordinates'], pd.Series) else current_segment['coordinates']

            from_lon, from_lat = segment_path_coords[0]
            to_lon, to_lat = segment_path_coords[1]
            
            segment_duration = current_segment['endTime'] - current_segment['startTime']

            if segment_duration > 0:
                progress = (current_time - current_segment['startTime']) / segment_duration
                progress = max(0, min(1, progress))

                current_lon = from_lon + (to_lon - from_lon) * progress
                current_lat = from_lat + (to_lat - from_lat) * progress
            else:
                current_lon, current_lat = from_lon, from_lat
            
            if not any(t['id'] == truck_id for t in truck_current_positions):
                truck_current_positions.append({
                    'id': truck_id,
                    'type': current_segment['type'],
                    'lat': current_lat,
                    'lon': current_lon
                })
        else:
            if current_time < truck_segments['startTime'].min() if not truck_segments.empty else 0:
                 dc_node_id = network_df[network_df['type'] == 'dc']['node_id'].iloc[0]
                 start_node_coords = network_df[network_df['node_id'] == dc_node_id].iloc[0]
                 
                 truck_current_positions.append({
                    'id': truck_id,
                    'type': truck_segments['type'].iloc[0] if not truck_segments.empty else 'EV',
                    'lat': start_node_coords['lat'],
                    'lon': start_node_coords['lon']
                })
            elif current_time > truck_segments['endTime'].max() if not truck_segments.empty else 0:
                 final_segment = truck_segments.iloc[-1]
                 final_path_coords = final_segment['coordinates'].item() if isinstance(final_segment['coordinates'], pd.Series) else final_segment['coordinates']

                 truck_current_positions.append({
                    'id': truck_id,
                    'type': final_segment['type'],
                    'lat': final_path_coords[1][1],
                    'lon': final_path_coords[1][0]
                })

    return truck_current_positions
