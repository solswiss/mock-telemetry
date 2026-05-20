import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time

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

# program values
SLEEP_DURATION = 1


# init data storage
COLS = ['Time', 'Altitude', 'Battery', 'Motor_Temperature']
def empty_session():
    st.session_state.flight_history = pd.DataFrame(columns=COLS)
    st.session_state.current_time = 0
    st.session_state.current_battery = BATTERY_MAX
    st.session_state.alerts = []

if "flight_history" not in st.session_state:
    empty_session()


# base architecture
st.title('Drone Dash')
sidebar = st.sidebar
sidebar.header('Hardware')

run_sim = sidebar.toggle('Connect Telemetry Stream',value=False)

sidebar.subheader('Settings')
inject_thermal_fault = sidebar.checkbox('overheat motor',value=False)
inject_alt_tampering = sidebar.checkbox('spoofing attack',value=False)
inject_bat_tampering = sidebar.checkbox('DOS',value=False)

clear_data = sidebar.button('Reset')

status = st.empty()

if clear_data:
    empty_session()
    st.rerun()


def populate_metrics(history_df, anomalies):
    if not history_df.empty:
        latest_row = history_df.iloc[-1] # get most recent read
    else:
        latest_row = latest_row = pd.Series([0,0.0,BATTERY_MAX,0.0], index=COLS)
    col1, col2, col3 = st.columns(3)
    col1.metric('Altitude', f"{latest_row['Altitude']} ft")
    col2.metric('Battery', f"{latest_row['Battery']}%")
    if 'overheat' in anomalies:
        col3.metric('Motor Temperature', f"{latest_row['Motor_Temperature']} °F", delta='Critical overheat', delta_color='inverse')
    else:
        col3.metric('Motor Temperature', f"{latest_row['Motor_Temperature']} °F")

def populate_chart(history_df, anomalies):
    st.header('Live Telemetry Stream')
    data = history_df.tail(30)
    if 'overheat' in anomalies or (temp > TEMP_CEILING for temp in data['Motor_Temperature']):
        mask = data['Motor_Temperature'] > TEMP_CEILING
        data['Overheated'] = data[mask]['Motor_Temperature']
        st.line_chart(data, x='Time', y=['Altitude','Motor_Temperature','Overheated'], color=['#0068c9','#83c9ff','red'])
    else:
        st.line_chart(data, x='Time', y=['Altitude','Motor_Temperature'])

def populate_log(history_df, anomalies):
    st.header('Raw Data')
    st.dataframe(history_df.tail(10), width='stretch')
    st.subheader('Alert Log')
    st.dataframe(pd.DataFrame(st.session_state.alerts).tail(5))

@st.fragment(run_every=SLEEP_DURATION)
def drone_dashboard():
    if st.session_state.current_battery == 0:
        st.info('System offline. Restart the connection in the sidebar to stream telemetry live.')
    elif not (run_sim and st.session_state.current_battery > 0):
        st.info('System offline. Toggle connection in the sidebar to stream telemetry live.')
        st.session_state.flight_history.to_csv('data.csv',index=False) # store data
    else:
        # generate data - constants are listed for convenience
        st.session_state.current_time += 1 # clock
        alt_noise = 1.5
        alt_tampering_noise = 100.0
        temp_noise = .8
        temp_thermal_fault_noise = 3.0

        if inject_alt_tampering: alt = np.random.normal(ALT_DEFAULT*2.5,alt_tampering_noise)
        else: alt = np.random.normal(ALT_DEFAULT,alt_noise) # altitude
        
        if inject_thermal_fault: temp = np.random.normal(TEMP_THERMAL_FAULT,temp_thermal_fault_noise)
        else: temp = np.random.normal(TEMP_DEFAULT,temp_noise) # motor temperature
        
        if inject_bat_tampering: st.session_state.current_battery -= np.random.uniform(BAT_DRAIN_CEIL,BAT_DRAIN_CEIL*2)
        else: st.session_state.current_battery -= np.random.uniform(BAT_DRAIN_MIN,BAT_DRAIN_MAX) # drain battery
        st.session_state.current_battery = max(0.0, st.session_state.current_battery) # 0 min

        df = pd.DataFrame([[st.session_state.current_time,round(alt,2),round(st.session_state.current_battery,1),round(temp,2)]], columns=COLS)

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
        
        if latest_row['Motor_Temperature'] > TEMP_CEILING:
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
        latest_row = pd.Series([0,0.0,BATTERY_MAX,0.0], index=COLS)

    # live render
    populate_metrics(history_df, anomalies)
    populate_chart(history_df, anomalies)
    populate_log(history_df, anomalies)

drone_dashboard()