#!/usr/bin/env python3
"""
Azure PostgreSQL Streaming Data Generator (Windows Compatible)
Continuously generates air quality data at high volume for streaming analytics testing.
"""

import argparse
import time
import datetime
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from psycopg2.extras import execute_values
import threading
import signal
import sys

# Azure PostgreSQL connection - URL encoded password
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123%21%40%23@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

class StreamingDataGenerator:
    def __init__(self):
        self.engine = create_engine(
            AZURE_CONNECTION_STRING,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True
        )
        self.running = False
        self.records_generated = 0
        self.start_time = None
        
    def get_active_stations(self):
        """Get list of active monitoring stations"""
        with self.engine.begin() as conn:
            stations = pd.read_sql(
                "SELECT station_id, city_zone, latitude, longitude FROM scaqms.stations WHERE is_active", 
                conn
            )
        return stations.to_dict('records')
    
    def generate_realistic_reading(self, station, timestamp):
        """Generate a single realistic air quality reading"""
        station_id = station['station_id']
        zone = station['city_zone']
        
        # Time-based patterns
        hour_float = timestamp.hour + timestamp.minute / 60
        diurnal = (1 + np.sin(2 * np.pi * hour_float / 24 - np.pi / 2)) / 2
        rush_hour = 1.0 + (0.4 if (7 <= timestamp.hour <= 9 or 17 <= timestamp.hour <= 19) else 0.0)
        
        # Seasonal patterns
        month = timestamp.month
        seasonal = 1.0 + 0.3 * np.sin(2 * np.pi * (month - 1) / 12)
        
        # Zone-specific pollution levels
        zone_multipliers = {
            "Industrial": 1.8, "Urban Core": 1.5, "Transportation": 1.6,
            "Green Space": 0.6, "Marine": 0.8, "Coastal": 0.7,
            "Residential": 1.0, "Educational": 0.8, "Commercial": 1.3,
            "Suburban": 0.9
        }
        zone_mult = zone_multipliers.get(zone, 1.0)
        
        # Base pollution levels with realistic ranges
        base_pm25 = 12 + 25 * diurnal + np.random.normal(0, 4)
        base_co2 = 380 + 120 * diurnal + np.random.normal(0, 20)
        
        # Apply all multipliers
        pm25 = max(0, base_pm25 * rush_hour * seasonal * zone_mult + np.random.normal(0, 2))
        co2 = max(0, base_co2 * rush_hour * seasonal * zone_mult + np.random.normal(0, 15))
        pm10 = pm25 * (1.1 + np.random.normal(0, 0.1))
        
        # Other pollutants
        no2 = max(0, 0.015 + 0.025 * diurnal * zone_mult + np.random.normal(0, 0.008))
        o3 = max(0, 0.025 + 0.015 * (1 - diurnal) * seasonal + np.random.normal(0, 0.005))
        
        # Weather conditions
        temp = 8 + 22 * diurnal + 12 * np.sin(2 * np.pi * (month - 1) / 12) + np.random.normal(0, 2)
        humidity = max(15, min(95, 55 + 25 * np.sin(2 * np.pi * (hour_float + 8) / 24) + np.random.normal(0, 8)))
        wind_speed = max(0, np.random.lognormal(mean=1.2, sigma=0.7))
        wind_direction = np.random.uniform(0, 360)
        pressure = 1013 + 12 * np.sin(2 * np.pi * hour_float / 24) + np.random.normal(0, 4)
        
        # Data quality (simulate sensor reliability)
        quality_score = np.random.beta(9, 1.5)  # High quality with occasional issues
        
        # Status determination
        if pm25 > 100 or co2 > 850:
            status = "Critical"
        elif pm25 > 55 or co2 > 700:
            status = "Alert"
        elif pm25 > 35 or co2 > 600:
            status = "Warning"
        else:
            status = "Normal"
        
        return (
            int(station_id), timestamp, float(round(co2, 2)), float(round(pm25, 2)), float(round(pm10, 2)),
            float(round(no2, 3)), float(round(o3, 3)), float(round(temp, 2)), float(round(humidity, 2)),
            float(round(wind_speed, 2)), float(round(wind_direction, 2)), float(round(pressure, 2)),
            status, float(round(quality_score, 2))
        )
    
    def generate_batch(self, stations, batch_size=100):
        """Generate a batch of readings"""
        current_time = datetime.datetime.now(datetime.timezone.utc)
        records = []
        
        for i in range(batch_size):
            # Select random station
            station = stations[i % len(stations)]
            
            # Add slight time variation
            timestamp = current_time + datetime.timedelta(
                seconds=np.random.uniform(-30, 30),
                microseconds=np.random.uniform(0, 999999)
            )
            
            # Generate reading
            record = self.generate_realistic_reading(station, timestamp)
            records.append(record)
        
        return records
    
    def insert_batch(self, records):
        """Insert batch of records into database"""
        insert_sql = """
            INSERT INTO scaqms.air_quality 
            (station_id, ts, co2_ppm, pm25, pm10, no2_ppm, o3_ppm, temperature_c, 
             humidity, wind_speed, wind_direction, atmospheric_pressure, status, data_quality_score)
            VALUES %s;
        """
        
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cur:
                execute_values(cur, insert_sql, records)
            raw.commit()
            return len(records)
        except Exception as e:
            print(f"Database error: {e}")
            raw.rollback()
            return 0
        finally:
            raw.close()
    
    def continuous_stream(self, records_per_minute=200, batch_size=50):
        """Run continuous streaming (until stopped)"""
        print(f"Starting continuous data stream...")
        print(f"Target: {records_per_minute} records/minute")
        print("Press Ctrl+C to stop")
        
        stations = self.get_active_stations()
        if not stations:
            print("No active stations found!")
            return
        
        print(f"Using {len(stations)} monitoring stations")
        
        self.running = True
        self.start_time = time.time()
        
        records_per_second = records_per_minute / 60
        batch_interval = batch_size / records_per_second
        
        batch_count = 0
        last_report_time = time.time()
        
        try:
            while self.running:
                batch_start = time.time()
                
                # Generate and insert batch
                records = self.generate_batch(stations, batch_size)
                inserted = self.insert_batch(records)
                
                self.records_generated += inserted
                batch_count += 1
                
                # Report progress every 60 seconds
                current_time = time.time()
                if current_time - last_report_time >= 60:
                    elapsed = current_time - self.start_time
                    rate = self.records_generated / elapsed * 60
                    print(f"Progress: {self.records_generated} records, {rate:.1f} records/min, {batch_count} batches")
                    last_report_time = current_time
                
                # Control timing
                batch_time = time.time() - batch_start
                sleep_time = max(0, batch_interval - batch_time)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            print(f"\nStopping stream...")
            self.running = False
            
            elapsed = time.time() - self.start_time
            avg_rate = self.records_generated / elapsed * 60
            print(f"Final stats: {self.records_generated} records, {avg_rate:.1f} records/min")
    
    def stop(self):
        """Stop the streaming process"""
        self.running = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print(f"\nReceived interrupt signal...")
    if 'generator' in globals():
        generator.stop()
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='Azure PostgreSQL Streaming Data Generator')
    parser.add_argument('--rate', type=int, default=200, help='Records per minute (default: 200)')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size (default: 50)')
    parser.add_argument('--continuous', action='store_true', help='Run continuously until stopped')
    
    args = parser.parse_args()
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    global generator
    generator = StreamingDataGenerator()
    
    try:
        if args.continuous:
            generator.continuous_stream(args.rate, args.batch_size)
        else:
            print("Use --continuous flag to run streaming")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
