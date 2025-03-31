import streamlit as st
import pandas as pd
import minimalmodbus
import time
import sqlite3
from datetime import datetime
import plotly.graph_objects as go
import asyncio
import json

def load_config(config_file='config.json'):
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        st.error("Config file not found.")
        st.stop()
    except json.JSONDecodeError:
        st.error("Invalid config file format.")
        st.stop()

def setup_modbus(config):
    try:
        instrument = minimalmodbus.Instrument(config['serial_port'], config['slave_address'])
        instrument.serial.baudrate = config['baudrate']
        instrument.serial.bytesize = config['bytesize']
        instrument.serial.parity = config['parity']
        instrument.serial.stopbits = config['stopbits']
        instrument.serial.serial.timeout = config['timeout']
        return instrument
    except Exception as e:
        st.error(f"Error initializing Modbus: {e}")
        st.stop()

def create_connection(db_file='energy_data.db'):
    conn = sqlite3.connect(db_file)
    return conn

def create_table(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS readings (
            timestamp TEXT PRIMARY KEY,
            voltage REAL,
            current REAL,
            power_factor REAL,
            power REAL,
            energy REAL,
            anomaly INTEGER
        )
    ''')
    conn.commit()

async def read_modbus_data_async(instrument):
    try:
        voltage = instrument.read_register(0, 3, signed=False) / 100.0
        current = instrument.read_register(2, 3, signed=False) / 100.0
        power_factor = instrument.read_register(4, 3, signed=False) / 1000.0
        power = instrument.read_register(6, 3, signed=False) / 100.0
        energy = instrument.read_register(8, 3, signed=False) / 1000.0
        return voltage, current, power_factor, power, energy
    except Exception as e:
        st.error(f"Modbus read error: {e}")
        return None, None, None, None, None

def detect_anomaly(voltage, current, power, config):
    anomaly = 0
    if voltage > config['anomaly_voltage_high'] or voltage < config['anomaly_voltage_low']:
        anomaly = 1
    if current > config['anomaly_current_high']:
        anomaly = 1
    if power > config['anomaly_power_high']:
        anomaly = 1
    return anomaly

def store_data(conn, timestamp, voltage, current, power_factor, power, energy, anomaly):
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO readings (timestamp, voltage, current, power_factor, power, energy, anomaly)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, voltage, current, power_factor, power, energy, anomaly))
    conn.commit()

async def update_dashboard(placeholder, instrument, config):
    conn = create_connection()
    create_table(conn)

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        voltage, current, power_factor, power, energy = await read_modbus_data_async(instrument)

        if voltage is not None:
            anomaly = detect_anomaly(voltage, current, power, config)
            store_data(conn, timestamp, voltage, current, power_factor, power, energy, anomaly)

            with placeholder.container():
                st.subheader("Current Readings")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Voltage (V)", f"{voltage:.2f}")
                col2.metric("Current (A)", f"{current:.2f}")
                col3.metric("Power Factor", f"{power_factor:.2f}")
                col4.metric("Power (W)", f"{power:.2f}")
                col5.metric("Energy (kWh)", f"{energy:.2f}")

                if anomaly:
                    st.warning("Anomaly Detected!")

                df = pd.read_sql_query("SELECT * FROM readings ORDER BY timestamp DESC LIMIT 10", conn)
                st.dataframe(df)

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df['timestamp'], y=df['voltage'], mode='lines+markers', name='Voltage'))
                fig.add_trace(go.Scatter(x=df['timestamp'], y=df['current'], mode='lines+markers', name='Current'))
                fig.add_trace(go.Scatter(x=df['timestamp'], y=df['power'], mode='lines+markers', name='Power'))
                st.plotly_chart(fig)

        await asyncio.sleep(config['refresh_rate'])
    conn.close()

def main():
    st.title("Energy Monitoring Dashboard")
    config = load_config()
    instrument = setup_modbus(config)
    placeholder = st.empty()

    asyncio.run(update_dashboard(placeholder, instrument, config))

if __name__ == "__main__":
    main()