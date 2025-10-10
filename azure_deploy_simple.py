#!/usr/bin/env python3
"""
Azure PostgreSQL Streaming Analytics Pipeline Deployment Script
Smart City Air Quality Monitoring System (AQMS)

This script deploys the complete streaming analytics pipeline on Azure PostgreSQL.
"""

import os
import sys
import time
import datetime
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from psycopg2.extras import execute_values
from faker import Faker
import random
import threading
import schedule
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from joblib import dump, load
import pathlib

# Azure PostgreSQL connection - URL encoded password
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123%21%40%23@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

class AzureAQMSDeployer:
    def __init__(self):
        self.engine = create_engine(
            AZURE_CONNECTION_STRING,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.fake = Faker()
        self.model_path = "aqi_model_azure.joblib"
        self.labels = ["Good", "Moderate", "Unhealthy", "Hazardous"]
        self.label_to_idx = {l: i for i, l in enumerate(self.labels)}
        
    def deploy_schema(self):
        """Deploy the complete database schema on Azure PostgreSQL"""
        print("Deploying schema to Azure PostgreSQL...")
        
        ddl_schema = """
        -- Create schema and types
        CREATE SCHEMA IF NOT EXISTS scaqms;
        
        DO $$ BEGIN
            CREATE TYPE scaqms.severity AS ENUM ('Low','Moderate','High','Critical');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        -- Stations table (Reference table)
        CREATE TABLE IF NOT EXISTS scaqms.stations (
            station_id SERIAL PRIMARY KEY,
            city_zone VARCHAR(100) NOT NULL,
            latitude NUMERIC(9,6) NOT NULL,
            longitude NUMERIC(9,6) NOT NULL,
            installation_date DATE DEFAULT CURRENT_DATE,
            is_active BOOLEAN DEFAULT TRUE,
            sensor_type VARCHAR(50) DEFAULT 'Multi-sensor',
            last_maintenance DATE,
            CONSTRAINT uq_station UNIQUE (city_zone, latitude, longitude)
        );

        -- Air Quality measurements (Main streaming table)
        CREATE TABLE IF NOT EXISTS scaqms.air_quality (
            record_id BIGSERIAL,
            station_id INT NOT NULL REFERENCES scaqms.stations(station_id) ON DELETE CASCADE,
            ts TIMESTAMPTZ NOT NULL DEFAULT now(),
            co2_ppm NUMERIC(10,2) CHECK (co2_ppm >= 0),
            pm25 NUMERIC(10,2) CHECK (pm25 >= 0),
            pm10 NUMERIC(10,2) CHECK (pm10 >= 0),
            no2_ppm NUMERIC(8,3) CHECK (no2_ppm >= 0),
            o3_ppm NUMERIC(8,3) CHECK (o3_ppm >= 0),
            temperature_c NUMERIC(5,2),
            humidity NUMERIC(5,2) CHECK (humidity BETWEEN 0 AND 100),
            wind_speed NUMERIC(5,2) CHECK (wind_speed >= 0),
            wind_direction NUMERIC(5,2) CHECK (wind_direction BETWEEN 0 AND 360),
            atmospheric_pressure NUMERIC(7,2) CHECK (atmospheric_pressure >= 0),
            status VARCHAR(20) DEFAULT 'Normal',
            data_quality_score NUMERIC(3,2) DEFAULT 1.0 CHECK (data_quality_score BETWEEN 0 AND 1),
            aqi_bucket TEXT GENERATED ALWAYS AS (
                CASE
                    WHEN pm25 IS NULL THEN NULL
                    WHEN pm25 <= 12 THEN 'Good'
                    WHEN pm25 <= 35 THEN 'Moderate'
                    WHEN pm25 <= 55 THEN 'Unhealthy'
                    ELSE 'Hazardous'
                END
            ) STORED,
            CONSTRAINT uq_record UNIQUE (record_id, ts)
        ) PARTITION BY RANGE (ts);

        -- Alerts table (Outlier detection results)
        CREATE TABLE IF NOT EXISTS scaqms.alerts (
            alert_id SERIAL PRIMARY KEY,
            record_id BIGINT NOT NULL,
            station_id INT NOT NULL,
            alert_type VARCHAR(50) NOT NULL,
            severity scaqms.severity NOT NULL,
            message TEXT,
            anomaly_score NUMERIC(6,5),
            detection_method VARCHAR(50) DEFAULT 'IsolationForest',
            created_at TIMESTAMPTZ DEFAULT now(),
            resolved_at TIMESTAMPTZ,
            is_resolved BOOLEAN DEFAULT FALSE,
            CONSTRAINT uq_alert UNIQUE (record_id, alert_type)
        );

        -- Predictions table (ML model outputs)
        CREATE TABLE IF NOT EXISTS scaqms.predictions (
            prediction_id SERIAL PRIMARY KEY,
            record_id BIGINT NOT NULL,
            station_id INT NOT NULL,
            aqi_pred TEXT,
            proba_good NUMERIC(6,5),
            proba_moderate NUMERIC(6,5),
            proba_unhealthy NUMERIC(6,5),
            proba_hazardous NUMERIC(6,5),
            confidence_score NUMERIC(6,5),
            model_version VARCHAR(20) DEFAULT 'v1.0',
            predicted_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_pred UNIQUE (record_id)
        );

        -- System metrics table (Performance monitoring)
        CREATE TABLE IF NOT EXISTS scaqms.system_metrics (
            metric_id SERIAL PRIMARY KEY,
            metric_name VARCHAR(100) NOT NULL,
            metric_value NUMERIC(15,5),
            metric_unit VARCHAR(20),
            recorded_at TIMESTAMPTZ DEFAULT now(),
            tags JSONB DEFAULT '{}'
        );

        -- Performance indexes
        CREATE INDEX IF NOT EXISTS idx_aq_station_ts ON scaqms.air_quality (station_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_aq_ts_desc ON scaqms.air_quality (ts DESC);
        CREATE INDEX IF NOT EXISTS idx_alerts_station ON scaqms.alerts (station_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON scaqms.alerts (is_resolved, severity);
        CREATE INDEX IF NOT EXISTS idx_predictions_station ON scaqms.predictions (station_id, predicted_at DESC);
        CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON scaqms.system_metrics (metric_name, recorded_at DESC);

        -- Partition management function
        CREATE OR REPLACE FUNCTION scaqms.ensure_month_partition(month_start date)
        RETURNS void AS $$
        DECLARE
            part_name text := 'air_quality_' || to_char(month_start, 'YYYYMM');
            start_ts timestamptz := month_start::timestamptz;
            end_ts   timestamptz := (month_start + INTERVAL '1 month')::timestamptz;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname='scaqms' AND c.relname=part_name
            ) THEN
                EXECUTE format('CREATE TABLE scaqms.%I PARTITION OF scaqms.air_quality
                                FOR VALUES FROM (%L) TO (%L);',
                                part_name, start_ts, end_ts);
                EXECUTE format('CREATE INDEX IF NOT EXISTS %I_station_ts ON scaqms.%I (station_id, ts DESC);', part_name, part_name);
                EXECUTE format('CREATE INDEX IF NOT EXISTS %I_ts ON scaqms.%I (ts DESC);', part_name, part_name);
            END IF;
        END $$ LANGUAGE plpgsql;

        -- Create partitions for current and next 3 months
        SELECT scaqms.ensure_month_partition(date_trunc('month', now())::date);
        SELECT scaqms.ensure_month_partition((date_trunc('month', now()) + INTERVAL '1 month')::date);
        SELECT scaqms.ensure_month_partition((date_trunc('month', now()) + INTERVAL '2 months')::date);
        SELECT scaqms.ensure_month_partition((date_trunc('month', now()) + INTERVAL '3 months')::date);
        """
        
        with self.engine.begin() as conn:
            conn.execute(text(ddl_schema))
        
        print("Schema deployed successfully!")
        return True

    def seed_stations(self):
        """Seed the stations table with realistic sensor locations"""
        print("Seeding monitoring stations...")
        
        stations_data = [
            ("Downtown Business", 40.7128, -74.0060, "Urban Core"),
            ("Residential North", 40.7870, -73.9754, "Residential"),
            ("Industrial Zone", 40.6782, -73.9442, "Industrial"),
            ("Harbor District", 40.7003, -74.0122, "Marine"),
            ("Central Park", 40.7712, -73.9742, "Green Space"),
            ("Airport Vicinity", 40.6413, -73.7781, "Transportation"),
            ("University Campus", 40.7505, -73.9934, "Educational"),
            ("Shopping District", 40.7614, -73.9776, "Commercial"),
            ("Suburban East", 40.7282, -73.7949, "Suburban"),
            ("Waterfront", 40.6892, -74.0445, "Coastal")
        ]
        
        seed_sql = """
        INSERT INTO scaqms.stations (city_zone, latitude, longitude, sensor_type)
        VALUES (:zone, :lat, :lon, :sensor_type)
        ON CONFLICT (city_zone, latitude, longitude) DO NOTHING;
        """
        
        with self.engine.begin() as conn:
            for zone, lat, lon, sensor_type in stations_data:
                conn.execute(text(seed_sql), {
                    "zone": zone, 
                    "lat": lat, 
                    "lon": lon,
                    "sensor_type": sensor_type
                })
        
        print("Stations seeded successfully!")

    def generate_initial_data(self, num_records=1000):
        """Generate initial realistic air quality data"""
        print(f"Generating {num_records} initial air quality records...")
        
        def diurnal_pattern(hour_float):
            return (1 + np.sin(2 * np.pi * hour_float / 24 - np.pi / 2)) / 2
        
        def seasonal_factor(month):
            return 1.0 + 0.2 * np.sin(2 * np.pi * (month - 1) / 12)
        
        # Get station IDs
        with self.engine.begin() as conn:
            stations = pd.read_sql("SELECT station_id, city_zone FROM scaqms.stations WHERE is_active", conn)
        
        if stations.empty:
            print("No active stations found!")
            return
        
        records = []
        base_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
        
        for i in range(num_records):
            station = stations.iloc[i % len(stations)]
            station_id = station['station_id']
            zone = station['city_zone']
            
            # Time progression
            ts = base_time + datetime.timedelta(minutes=i * 2)
            hour_float = ts.hour + ts.minute / 60
            month = ts.month
            
            # Base patterns
            diurnal = diurnal_pattern(hour_float)
            seasonal = seasonal_factor(month)
            rush_hour = 1.0 + (0.3 if (7 <= ts.hour <= 9 or 17 <= ts.hour <= 19) else 0.0)
            
            # Zone-specific multipliers
            zone_multipliers = {
                "Industrial": 1.5, "Urban Core": 1.3, "Transportation": 1.4,
                "Green Space": 0.6, "Marine": 0.8, "Coastal": 0.7
            }
            zone_mult = zone_multipliers.get(zone, 1.0)
            
            # Generate realistic values with patterns
            base_pm25 = 15 + 20 * diurnal + np.random.normal(0, 4)
            base_co2 = 420 + 80 * diurnal + np.random.normal(0, 20)
            
            # Apply multipliers and seasonal effects
            pm25 = max(0, base_pm25 * rush_hour * seasonal * zone_mult + np.random.normal(0, 2))
            co2 = max(0, base_co2 * rush_hour * seasonal * zone_mult + np.random.normal(0, 10))
            pm10 = pm25 * (1.2 + np.random.normal(0, 0.1))
            
            # Other pollutants
            no2 = max(0, 0.02 + 0.03 * diurnal * zone_mult + np.random.normal(0, 0.01))
            o3 = max(0, 0.03 + 0.02 * (1 - diurnal) * seasonal + np.random.normal(0, 0.005))
            
            # Weather conditions
            temp = 10 + 20 * diurnal + 10 * np.sin(2 * np.pi * (month - 1) / 12) + np.random.normal(0, 2)
            humidity = max(15, min(95, 60 + 20 * np.sin(2 * np.pi * (hour_float + 8) / 24) + np.random.normal(0, 8)))
            wind_speed = max(0, np.random.lognormal(mean=1.0, sigma=0.6))
            wind_direction = np.random.uniform(0, 360)
            pressure = 1013 + 10 * np.sin(2 * np.pi * hour_float / 24) + np.random.normal(0, 3)
            
            # Data quality (simulate occasional sensor issues)
            quality_score = np.random.beta(8, 2)  # Skewed towards high quality
            
            # Status determination
            status = "Normal"
            if pm25 > 100 or co2 > 800:
                status = "Alert"
            elif pm25 > 55 or co2 > 600:
                status = "Warning"
            
            records.append((
                int(station_id), ts, float(round(co2, 2)), float(round(pm25, 2)), float(round(pm10, 2)),
                float(round(no2, 3)), float(round(o3, 3)), float(round(temp, 2)), float(round(humidity, 2)),
                float(round(wind_speed, 2)), float(round(wind_direction, 2)), float(round(pressure, 2)),
                status, float(round(quality_score, 2))
            ))
        
        # Batch insert
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
            print(f"Generated {len(records)} air quality records!")
        finally:
            raw.close()

def main():
    """Main deployment function"""
    print("Azure PostgreSQL Streaming Analytics Pipeline Deployment")
    print("=" * 60)
    
    deployer = AzureAQMSDeployer()
    
    try:
        # 1. Deploy schema
        deployer.deploy_schema()
        
        # 2. Seed stations
        deployer.seed_stations()
        
        # 3. Generate initial data
        deployer.generate_initial_data(num_records=2000)
        
        print("\nDeployment completed successfully!")
        print("\nNext steps:")
        print("1. Run the dashboard: streamlit run app.py")
        print("2. Start streaming simulation: python azure_stream.py --continuous")
        print("3. Monitor system: python azure_monitor.py")
        
    except Exception as e:
        print(f"Deployment failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    main()
