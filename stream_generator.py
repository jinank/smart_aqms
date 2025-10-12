#!/usr/bin/env python3
"""
Smart AQMS Data Generator - Populates Azure PostgreSQL with realistic air quality data
Usage: python stream_generator.py --duration 5 --rate 100
"""

import os
import time
import math
import random
import datetime as dt
import argparse
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

# Azure PostgreSQL connection
DEFAULT_URL = 'postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require'

# -----------------------------------------------------------------------------
# Synthetic Sensor Model
# -----------------------------------------------------------------------------
class SensorState:
    def __init__(self, seed=42):
        random.seed(seed)
        np.random.seed(seed)
        self.state = {}

    def step(self, sid, minute):
        if sid not in self.state:
            self.state[sid] = {
                "pm25": np.random.uniform(5, 25),
                "co2": np.random.uniform(400, 700),
                "temp": np.random.uniform(10, 25),
                "hum": np.random.uniform(40, 70),
                "wind": np.random.uniform(0, 5)
            }
        s = self.state[sid]
        
        # Diurnal pattern
        diurnal = 10 + 10 * math.sin(2 * math.pi * (minute / 1440.0))
        
        # PM2.5 with occasional spikes
        s["pm25"] = max(0, s["pm25"] + np.random.normal(0, 1))
        if random.random() < 0.02:  # 2% chance of pollution spike
            s["pm25"] += np.random.uniform(20, 60)
        
        # CO2 variation
        s["co2"] += np.random.normal(0, 5)
        
        # Temperature with diurnal pattern
        temp = 18 + 7 * math.sin(2 * math.pi * (minute / 1440.0)) + np.random.normal(0, 0.5)
        
        # Humidity inversely related to temperature
        hum = np.clip(60 - (temp - 18) * 1.2 + np.random.normal(0, 2), 15, 95)
        
        # Wind speed
        wind = np.clip(s["wind"] + np.random.normal(0, 0.2), 0, 12)
        
        s.update({"temp": temp, "hum": hum, "wind": wind})
        return s["pm25"] + diurnal, s["co2"], temp, hum, wind

# -----------------------------------------------------------------------------
# Database Operations
# -----------------------------------------------------------------------------
def get_connection(url):
    """Create database connection"""
    return psycopg2.connect(url)

def get_stations_and_sensors(conn):
    """Get all active stations and their sensors"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.station_id, sn.sensor_id, sn.sensor_type
            FROM scaqms.stations s
            JOIN scaqms.sensors sn ON s.station_id = sn.station_id
            WHERE s.status = 'Active' AND sn.status = 'Active'
            ORDER BY s.station_id, sn.sensor_id
        """)
        return cur.fetchall()

def insert_readings_batch(conn, readings):
    """Insert batch of air quality readings"""
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO scaqms.air_quality_readings 
            (station_id, sensor_id, timestamp, pm25, co2_ppm, temperature_c, 
             humidity_percent, wind_speed_ms, data_quality_score)
            VALUES %s
            RETURNING reading_id
        """, readings)
        reading_ids = [row[0] for row in cur.fetchall()]
    conn.commit()
    return reading_ids

def insert_predictions_batch(conn, predictions):
    """Insert batch of ML predictions"""
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO scaqms.predictions 
            (reading_id, station_id, model_version, predicted_aqi_category, confidence_score)
            VALUES %s
            ON CONFLICT (reading_id) DO NOTHING
        """, predictions)
    conn.commit()

def insert_alerts_batch(conn, alerts):
    """Insert batch of alerts"""
    if not alerts:
        return
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO scaqms.alerts 
            (reading_id, station_id, alert_type, severity, status, message)
            VALUES %s
        """, alerts)
    conn.commit()

def generate_aqi_category(pm25):
    """Generate AQI category based on PM2.5 value"""
    if pm25 <= 12:
        return "Good"
    elif pm25 <= 35:
        return "Moderate"
    elif pm25 <= 55:
        return "Unhealthy"
    else:
        return "Hazardous"

# -----------------------------------------------------------------------------
# Main streaming loop
# -----------------------------------------------------------------------------
def run_stream(url, rate_per_min=100, duration_min=5):
    """Main data generation loop"""
    
    print("=" * 60)
    print("🌆 Smart AQMS Data Generator")
    print("=" * 60)
    print(f"Target rate: {rate_per_min} readings/minute")
    print(f"Duration: {duration_min} minutes")
    print(f"Connecting to Azure PostgreSQL...")
    
    conn = get_connection(url)
    
    # Get stations and sensors
    stations_sensors = get_stations_and_sensors(conn)
    if not stations_sensors:
        print("❌ No active stations/sensors found. Please run deploy_schema.py first.")
        return
    
    print(f"✅ Found {len(stations_sensors)} active sensor(s)")
    
    # Initialize sensor state
    state = SensorState()
    
    # Calculate timing
    readings_per_cycle = max(1, rate_per_min // 6)  # 6 cycles per minute (every 10 seconds)
    sleep_time = 10  # seconds between cycles
    
    print(f"📊 Generating {readings_per_cycle} readings every {sleep_time} seconds")
    print("=" * 60)
    
    total_inserted = 0
    total_predictions = 0
    total_alerts = 0
    start_time = time.time()
    end_time = start_time + (duration_min * 60)
    
    try:
        while time.time() < end_time:
            cycle_start = time.time()
            now = dt.datetime.now()
            minute = now.hour * 60 + now.minute
            
            readings = []
            predictions = []
            alerts = []
            
            # Generate readings for this cycle
            for _ in range(readings_per_cycle):
                # Pick random station/sensor
                station_id, sensor_id, sensor_type = random.choice(stations_sensors)
                
                # Generate sensor data
                pm25, co2, temp, hum, wind = state.step(station_id, minute)
                
                # Create reading tuple
                reading = (
                    station_id,
                    sensor_id,
                    now,
                    round(pm25, 2),
                    round(co2, 2),
                    round(temp, 2),
                    round(hum, 2),
                    round(wind, 2),
                    round(random.uniform(0.90, 1.0), 2)  # data_quality_score
                )
                readings.append(reading)
            
            # Insert readings and get IDs
            reading_ids = insert_readings_batch(conn, readings)
            total_inserted += len(reading_ids)
            
            # Generate predictions for inserted readings
            for i, reading_id in enumerate(reading_ids):
                station_id, sensor_id, timestamp, pm25, co2, temp, hum, wind, quality = readings[i]
                aqi_category = generate_aqi_category(pm25)
                confidence = round(random.uniform(0.75, 0.95), 3)
                
                predictions.append((
                    reading_id,
                    station_id,
                    'v1.0',
                    aqi_category,
                    confidence
                ))
                
                # Generate alert if PM2.5 is high
                if pm25 > 50:
                    severity = 'Critical' if pm25 > 100 else 'High' if pm25 > 75 else 'Moderate'
                    alerts.append((
                        reading_id,
                        station_id,
                        'PM2.5 High',
                        severity,
                        'Open',
                        f'PM2.5 level {pm25:.1f} μg/m³ exceeds safe threshold'
                    ))
            
            # Insert predictions and alerts
            insert_predictions_batch(conn, predictions)
            total_predictions += len(predictions)
            
            if alerts:
                insert_alerts_batch(conn, alerts)
                total_alerts += len(alerts)
            
            # Calculate stats
            elapsed = time.time() - start_time
            rate = (total_inserted / elapsed) * 60 if elapsed > 0 else 0
            remaining = max(0, end_time - time.time())
            
            # Progress report
            print(f"[{now:%H:%M:%S}] Inserted: {total_inserted:,} readings | "
                  f"Predictions: {total_predictions:,} | Alerts: {total_alerts:,} | "
                  f"Rate: {rate:.0f}/min | Remaining: {remaining:.0f}s")
            
            # Sleep until next cycle
            cycle_elapsed = time.time() - cycle_start
            sleep_duration = max(0, sleep_time - cycle_elapsed)
            if sleep_duration > 0:
                time.sleep(sleep_duration)
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    
    finally:
        conn.close()
        total_time = time.time() - start_time
        avg_rate = (total_inserted / total_time) * 60 if total_time > 0 else 0
        
        print("\n" + "=" * 60)
        print("✅ Data Generation Complete")
        print("=" * 60)
        print(f"Total readings inserted: {total_inserted:,}")
        print(f"Total predictions: {total_predictions:,}")
        print(f"Total alerts: {total_alerts:,}")
        print(f"Duration: {total_time:.1f} seconds")
        print(f"Average rate: {avg_rate:.0f} readings/minute")
        print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Smart AQMS Data Generator')
    parser.add_argument("--url", type=str, default=DEFAULT_URL, help="PostgreSQL connection URL")
    parser.add_argument("--rate", type=int, default=100, help="Target readings per minute")
    parser.add_argument("--duration", type=int, default=5, help="Duration in minutes")
    args = parser.parse_args()
    
    run_stream(args.url, args.rate, args.duration)

