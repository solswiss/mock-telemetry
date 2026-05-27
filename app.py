from typing import Any, cast
import warnings
from typing import Any, cast
import warnings
import streamlit as st
import pandas as pd
import numpy as np
import friendlywords as fw
from geopy.geocoders import ArcGIS
import geopy.distance
from streamlit.delta_generator import DeltaGenerator


fw.preload() # type: ignore
# mostly to ignore empty display warnings
warnings.filterwarnings("ignore") # type: ignore
geolocator = ArcGIS()


# drone values
ALT_DEFAULT = 150.0
ALT_GAIN_CEILING = 110.0
TEMP_DEFAULT = 120.0
TEMP_CEILING = 140.0
TEMP_THERMAL_FAULT = 210.0
BATTERY_MAX = 100.0
BATTERY_MIN = 0.0
BAT_WARN_FLOOR = 20.0
BAT_DRAIN_MIN = .1
BAT_DRAIN_MAX = .3
BAT_DRAIN_CEIL = 2

# sim values
DEFAULT_START_LOC = geolocator.geocode('175 5th Avenue NYC',timeout=10) # type: ignore
DELTA = 1 # 1 time per sec


# init data storage
COLS = ['Time', 'Altitude', 'Battery', 'Motor Temperature','Longitude','Latitude']
def empty_session():
    if 'start_loc' in st.session_state:
        del st.session_state.start_loc
        del st.session_state.start_x
        del st.session_state.start_y
        #del st.session_state.session_name
    # if 'connection_toggle' in st.session_state:
    #     st.session_state.connection_toggle = False
    st.session_state.departed = False
    st.session_state.start_loc = DEFAULT_START_LOC.address # type: ignore
    st.session_state.start_x = DEFAULT_START_LOC.latitude # type: ignore
    st.session_state.start_y = DEFAULT_START_LOC.longitude # type: ignore
    st.session_state.flight_history = pd.DataFrame(columns=COLS)
    st.session_state.lat = st.session_state.start_x
    st.session_state.lon = st.session_state.start_y
    st.session_state.current_time = 0
    st.session_state.current_battery = BATTERY_MAX
    st.session_state.alerts = []
    st.session_state.session_name = "mock telemetry "+fw.generate(3) # type: ignore
    st.session_state.session_name = "mock telemetry "+fw.generate(3) # type: ignore

if "flight_history" not in st.session_state:
    empty_session()


# base architecture
st.title('Mock Telemetry Dashboard')
sidebar = st.sidebar

def connection_changed():
    if not st.session_state.departed and st.session_state.connection_toggle:
        st.session_state.departed = True
run_sim = sidebar.toggle('Connect Telemetry Stream',value=False,key='connection_toggle',on_change=connection_changed)

session_string = sidebar.text_input('Session Name', value=st.session_state.session_name)

sidebar.subheader('Settings')

# physics
heading = sidebar.slider("heading (deg)",min_value=0,max_value=360,value=45)
speed = sidebar.slider("speed (m/s)",min_value=1,max_value=30,value=10)

# coords
def update_start_loc():
    loc = geolocator.reverse((str(st.session_state.start_x),str(st.session_state.start_y)),timeout=10) #type: ignore
    if loc:
        st.session_state.start_loc = loc.address # type: ignore
        st.session_state.lat = st.session_state.start_x # type: ignore
        st.session_state.lon = st.session_state.start_y # type: ignore
        populate_map()
def update_start_coords():
    loc = geolocator.geocode(st.session_state.start_loc,timeout=10) #type: ignore
    if loc:
        st.session_state.start_x = st.session_state.lat = loc.latitude # type: ignore
        st.session_state.start_y = st.session_state.lon = loc.longitude # type: ignore
        populate_map()
start_coord_loc = sidebar.text_input('address',key='start_loc',on_change=update_start_coords,disabled=st.session_state.departed) # type: ignore
start_coord_col1, start_coord_col2 = sidebar.columns(2)
start_x = start_coord_col1.number_input('longitude',key='start_x',on_change=update_start_loc,disabled=st.session_state.departed) # type: ignore
start_y = start_coord_col2.number_input('latitude',key='start_y',on_change=update_start_loc,disabled=st.session_state.departed) # type: ignore

# faults
sidebar.subheader('Fault Injections')
inject_thermal_fault = sidebar.checkbox('overheat motor',value=False)
inject_alt_tampering = sidebar.checkbox('spoofing attack',value=False)
inject_bat_tampering = sidebar.checkbox('DOS',value=False)

# data
download_data = sidebar.download_button('Download Flight History', st.session_state.flight_history.to_csv(index=False), file_name=f'{st.session_state.session_name} flight history.csv')
download_alerts = sidebar.download_button('Download Alert Log', st.session_state.flight_history.to_csv(index=False), file_name=f'{st.session_state.session_name} alert log.csv')
clear_data = sidebar.button('Reset',key='clear_data',on_click=empty_session)

# visuals
sys_banner = st.empty()
status: DeltaGenerator = st.empty()

st.markdown('## Metrics')
col1, col2, col3 = st.columns(3)
col_altitude = col1.empty()
col_battery = col2.empty()
col_motor_temp = col3.empty()

st.markdown('### Live Telemetry Stream')
tracks = st.multiselect('Tracked data', COLS[1:], default=['Altitude','Motor Temperature'])
chart_display = st.empty()

st.markdown('## Location')
map_display = st.empty()

st.markdown('## Raw Data')
raw_data = st.empty()

st.subheader('Alert Log')
alert_log = st.empty()


def populate_metrics(history_df, anomalies):
    if not history_df.empty:
        latest_row = history_df.iloc[-1] # get most recent read
    else:
        latest_row = latest_row = pd.Series([0,0.0,BATTERY_MAX,0.0,st.session_state.lon,st.session_state.lat], index=COLS)
    col_altitude.metric('Altitude', f"{latest_row['Altitude']} ft")
    col_battery.metric('Battery', f"{latest_row['Battery']}%")
    if 'overheat' in anomalies:
        col_motor_temp.metric('Motor Temperature', f"{latest_row['Motor Temperature']} °F", delta='Critical overheat', delta_color='inverse')
        col_motor_temp.metric('Motor Temperature', f"{latest_row['Motor Temperature']} °F", delta='Critical overheat', delta_color='inverse')
    else:
        col_motor_temp.metric('Motor Temperature', f"{latest_row['Motor Temperature']} °F")
        col_motor_temp.metric('Motor Temperature', f"{latest_row['Motor Temperature']} °F")

def populate_chart(history_df, anomalies):
    chart_colors = ['#0068c9','#83c9ff','#29b09d']
    data = history_df.tail(30)
    if 'overheat' in anomalies or (temp > TEMP_CEILING for temp in data['Motor Temperature']):
        mask = data['Motor Temperature'] > TEMP_CEILING
        data['Overheated'] = data[mask]['Motor Temperature']
        chart_display.line_chart(data, x='Time', y=tracks+['Overheated'], color=chart_colors[:len(tracks)]+['red']) # type: ignore
        chart_display.line_chart(data, x='Time', y=tracks+['Overheated'], color=chart_colors[:len(tracks)]+['red']) # type: ignore
    else:
        chart_display.line_chart(data, x='Time', y=tracks, color=chart_colors[:len(tracks)]) # type: ignore

def populate_map():
    map_display.map(pd.DataFrame({'lat': [st.session_state.lat], 'lon': [st.session_state.lon]}))

def populate_log(history_df, anomalies):
    raw_data.dataframe(history_df.tail(10), width='stretch')
    alert_log.dataframe(pd.DataFrame(st.session_state.alerts).tail(5))

# drone physics
def move_drone(lat, lon, bearing_deg, speed_mps, delta):
    dist_m = speed_mps*delta
    start_coords = (lat,lon)
    moving_dist = geopy.distance.distance(meters=dist_m)
    dest = moving_dist.destination(point=start_coords,bearing=bearing_deg)
    return dest.latitude, dest.longitude


@st.fragment(run_every=DELTA)
def drone_dashboard():
    if st.session_state.current_battery == 0:
        sys_banner.info('System offline. Restart the connection in the sidebar to stream telemetry live.')
    elif not (run_sim and st.session_state.current_battery > 0):
        sys_banner.info('System offline. Toggle connection in the sidebar to stream telemetry live.')
    else:
        # generate data
        # 'constants' are listed for convenience
        st.session_state.current_time += 1 # clock
        alt_noise = 1.5
        alt_tampering_noise = 100.0
        temp_noise = .8
        temp_thermal_fault_noise = 3.0

        lat, lon = move_drone(st.session_state.lat,st.session_state.lon,heading,speed,DELTA)
        st.session_state.lat = lat
        st.session_state.lon = lon

        if inject_alt_tampering: alt = np.random.normal(ALT_DEFAULT*2.5,alt_tampering_noise)
        else: alt = np.random.normal(ALT_DEFAULT,alt_noise) # altitude
        
        if inject_thermal_fault: temp = np.random.normal(TEMP_THERMAL_FAULT,temp_thermal_fault_noise)
        else: temp = np.random.normal(TEMP_DEFAULT,temp_noise) # motor temperature
        
        if inject_bat_tampering: st.session_state.current_battery -= np.random.uniform(BAT_DRAIN_CEIL,BAT_DRAIN_CEIL*2)
        else: st.session_state.current_battery -= np.random.uniform(BAT_DRAIN_MIN,BAT_DRAIN_MAX) # drain battery
        st.session_state.current_battery = max(0.0, st.session_state.current_battery) # 0 min

        df = pd.DataFrame([[
            st.session_state.current_time,
            round(alt,2),
            round(st.session_state.current_battery,1),
            round(temp,2),
            lon,
            lat,
            ]],
            columns=COLS)

        st.session_state.flight_history = pd.concat([st.session_state.flight_history,df], ignore_index=True)

    history_df = st.session_state.flight_history

    anomalies = {}

    if len(history_df) > 1:
        latest_row = history_df.iloc[-1]
        prev_row = history_df.iloc[-2]
        if run_sim:
            status.success('Systems operating within safety thresholds')
        
        # tracked anomalies in a somewhat relative increasing order of importance
        if latest_row['Battery'] < BAT_WARN_FLOOR:
            status.warning(f'Warning: battery level is below {BAT_WARN_FLOOR}')
            st.session_state.alerts.append({
                'Time':latest_row['Time'],
                'Type':'Warning',
                'Subject':'Battery',
                'Message':f'Warning: battery level is below {BAT_WARN_FLOOR}'
            })
        
        if latest_row['Motor Temperature'] > TEMP_CEILING:
            anomalies['overheat'] = f'Motor overheating detected at {latest_row['Time']}s: current temperatures exceed safety threshold'
            status.error(anomalies['overheat'])
            st.session_state.alerts.append({
                'Time':latest_row['Time'],
                'Type':'Critical',
                'Subject':'Motor Temperature',
                'Message':anomalies['overheat']
            })
        
        bat_diff = prev_row['Battery']-latest_row['Battery']
        if bat_diff > BAT_DRAIN_CEIL:
            anomalies['dos'] = f'Battery anomaly detected at {latest_row['Time']}s: battery level drain of {round(bat_diff,1)}% exceeds expectation'
            status.error(anomalies['dos'])
            st.session_state.alerts.append({
                'Time':latest_row['Time'],
                'Type':'Critical',
                'Subject':'Battery',
                'Message':anomalies['dos']
            })

        alt_diff = abs(latest_row['Altitude']-prev_row['Altitude'])
        if alt_diff > ALT_GAIN_CEILING:
            anomalies['spoof'] = f'Altitude anomaly detected at {latest_row['Time']}s: altitude spike of {round(alt_diff,1)} ft exceeds expectation'
            status.error(anomalies['spoof'])
            st.session_state.alerts.append({
                'Time':latest_row['Time'],
                'Type':'Critical',
                'Subject':'Altitude',
                'Message':anomalies['spoof']
            })
    else:
        latest_row = pd.Series([0,0.0,BATTERY_MAX,0.0,st.session_state.lon,st.session_state.lat], index=COLS)

    # live render
    populate_metrics(history_df, anomalies)
    populate_chart(history_df, anomalies)
    populate_map()
    populate_log(history_df, anomalies)

drone_dashboard()