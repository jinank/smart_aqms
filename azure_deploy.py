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

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

# Azure PostgreSQL connection
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123!@#@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

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
        print("🚀 Deploying schema to Azure PostgreSQL...")
        
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
        
        print("✅ Schema deployed successfully!")
        return True

    def seed_stations(self):
        """Seed the stations table with realistic sensor locations"""
        print("🌍 Seeding monitoring stations...")
        
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
        
        print("✅ Stations seeded successfully!")

    def generate_realistic_data(self, num_records=1000):
        """Generate realistic air quality data with seasonal and daily patterns"""
        print(f"📊 Generating {num_records} realistic air quality records...")
        
        def diurnal_pattern(hour_float):
            """Generate diurnal pattern for air quality"""
            return (1 + np.sin(2 * np.pi * hour_float / 24 - np.pi / 2)) / 2
        
        def seasonal_factor(month):
            """Seasonal variation in air quality"""
            return 1.0 + 0.2 * np.sin(2 * np.pi * (month - 1) / 12)
        
        # Get station IDs
        with self.engine.begin() as conn:
            stations = pd.read_sql("SELECT station_id, city_zone FROM scaqms.stations WHERE is_active", conn)
        
        if stations.empty:
            print("❌ No active stations found!")
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
                station_id, ts, round(co2, 2), round(pm25, 2), round(pm10, 2),
                round(no2, 3), round(o3, 3), round(temp, 2), round(humidity, 2),
                round(wind_speed, 2), round(wind_direction, 2), round(pressure, 2),
                status, round(quality_score, 2)
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
            print(f"✅ Generated {len(records)} air quality records!")
        finally:
            raw.close()

    def detect_outliers(self, window_minutes=60, contamination=0.05):
        """Detect outliers using Isolation Forest"""
        print("🔍 Running outlier detection...")
        
        query = """
            SELECT record_id, station_id, ts, co2_ppm, pm25, pm10, temperature_c, humidity
            FROM scaqms.air_quality
            WHERE ts >= now() - INTERVAL :win AND data_quality_score > 0.7
            ORDER BY ts ASC;
        """
        
        with self.engine.begin() as conn:
            df = pd.read_sql(text(query), conn, params={"win": f"{window_minutes} minutes"})
        
        if df.empty or len(df) < 10:
            print("⚠️ Insufficient data for outlier detection.")
            return 0
        
        # Use Isolation Forest for anomaly detection
        iso_forest = IsolationForest(
            contamination=contamination, 
            random_state=42,
            n_estimators=100
        )
        
        # Features for anomaly detection
        features = ['co2_ppm', 'pm25', 'pm10', 'temperature_c', 'humidity']
        df_clean = df[features].fillna(df[features].median())
        
        # Detect anomalies
        df['anomaly_score'] = iso_forest.fit_predict(df_clean)
        df['is_outlier'] = (df['anomaly_score'] == -1)
        
        outliers = df[df['is_outlier']]
        
        if outliers.empty:
            print("✅ No anomalies detected.")
            return 0
        
        # Insert alerts for outliers
        alert_records = []
        for _, row in outliers.iterrows():
            severity = 'Critical' if row['pm25'] > 100 or row['co2_ppm'] > 800 else 'High'
            message = f"Anomaly detected: PM2.5={row['pm25']:.1f}, CO2={row['co2_ppm']:.0f}ppm"
            
            alert_records.append((
                int(row['record_id']), int(row['station_id']), 'Anomaly', severity,
                message, 0.8, 'IsolationForest'
            ))
        
        if alert_records:
            alert_sql = """
                INSERT INTO scaqms.alerts (record_id, station_id, alert_type, severity, message, anomaly_score, detection_method)
                VALUES %s
                ON CONFLICT (record_id, alert_type) DO NOTHING;
            """
            
            raw = self.engine.raw_connection()
            try:
                with raw.cursor() as cur:
                    execute_values(cur, alert_sql, alert_records)
                raw.commit()
                print(f"🚨 Generated {len(alert_records)} anomaly alerts!")
            finally:
                raw.close()
        
        return len(alert_records)

    def train_ml_model(self, window_minutes=120):
        """Train and deploy ML model for AQI prediction"""
        print("🧠 Training ML model for AQI prediction...")
        
        # Load training data
        query = """
            SELECT record_id, station_id, co2_ppm, pm25, pm10, no2_ppm, o3_ppm, 
                   temperature_c, humidity, wind_speed, aqi_bucket
            FROM scaqms.air_quality
            WHERE ts >= now() - INTERVAL :mins AND aqi_bucket IS NOT NULL
            AND data_quality_score > 0.8;
        """
        
        with self.engine.begin() as conn:
            df = pd.read_sql(text(query), conn, params={"mins": f"{window_minutes} minutes"})
        
        if df.empty or len(df) < 50:
            print("⚠️ Insufficient training data.")
            return
        
        # Prepare features and labels
        feature_cols = ['co2_ppm', 'pm25', 'pm10', 'no2_ppm', 'o3_ppm', 'temperature_c', 'humidity', 'wind_speed']
        X = df[feature_cols].fillna(df[feature_cols].median())
        y = df['aqi_bucket'].map(self.label_to_idx)
        
        # Remove any unmapped labels
        valid_mask = ~y.isna()
        X = X[valid_mask]
        y = y[valid_mask]
        
        if len(X) < 20:
            print("⚠️ Insufficient valid training samples.")
            return
        
        # Load or initialize model
        if pathlib.Path(self.model_path).exists():
            model = load(self.model_path)
            print("📥 Loaded existing model for incremental training")
        else:
            model = Pipeline([
                ("scaler", StandardScaler()),
                ("clf", SGDClassifier(
                    loss="log_loss", 
                    max_iter=1, 
                    learning_rate="adaptive",
                    eta0=0.01,
                    random_state=42
                ))
            ])
            # Initialize with dummy data
            dummy_X = np.zeros((1, len(feature_cols)))
            dummy_y = np.array([0])
            model.named_steps["clf"].partial_fit(dummy_X, dummy_y, classes=np.arange(len(self.labels)))
            print("🆕 Initialized new model")
        
        # Train model incrementally
        model.named_steps["clf"].partial_fit(X, y)
        
        # Save model
        dump(model, self.model_path)
        print(f"💾 Model trained on {len(X)} samples and saved")
        
        # Generate predictions for recent data
        self.generate_predictions(model, window_minutes)

    def generate_predictions(self, model, window_minutes=60):
        """Generate predictions using the trained model"""
        print("📈 Generating AQI predictions...")
        
        query = """
            SELECT record_id, station_id, co2_ppm, pm25, pm10, no2_ppm, o3_ppm,
                   temperature_c, humidity, wind_speed
            FROM scaqms.air_quality
            WHERE ts >= now() - INTERVAL :mins AND data_quality_score > 0.7;
        """
        
        with self.engine.begin() as conn:
            df = pd.read_sql(text(query), conn, params={"mins": f"{window_minutes} minutes"})
        
        if df.empty:
            print("⚠️ No data for prediction.")
            return
        
        # Prepare features
        feature_cols = ['co2_ppm', 'pm25', 'pm10', 'no2_ppm', 'o3_ppm', 'temperature_c', 'humidity', 'wind_speed']
        X = df[feature_cols].fillna(df[feature_cols].median())
        
        # Generate predictions
        predictions = model.named_steps["clf"].predict(X)
        probabilities = model.named_steps["clf"].predict_proba(X)
        
        # Prepare prediction records
        pred_records = []
        for i, (_, row) in enumerate(df.iterrows()):
            pred_label = self.labels[predictions[i]]
            confidence = np.max(probabilities[i])
            
            pred_records.append((
                int(row['record_id']), int(row['station_id']), pred_label,
                float(probabilities[i][0]), float(probabilities[i][1]), 
                float(probabilities[i][2]), float(probabilities[i][3]),
                float(confidence)
            ))
        
        # Insert predictions
        if pred_records:
            pred_sql = """
                INSERT INTO scaqms.predictions 
                (record_id, station_id, aqi_pred, proba_good, proba_moderate, 
                 proba_unhealthy, proba_hazardous, confidence_score)
                VALUES %s
                ON CONFLICT (record_id) DO UPDATE SET
                    aqi_pred = EXCLUDED.aqi_pred,
                    proba_good = EXCLUDED.proba_good,
                    proba_moderate = EXCLUDED.proba_moderate,
                    proba_unhealthy = EXCLUDED.proba_unhealthy,
                    proba_hazardous = EXCLUDED.proba_hazardous,
                    confidence_score = EXCLUDED.confidence_score,
                    predicted_at = now();
            """
            
            raw = self.engine.raw_connection()
            try:
                with raw.cursor() as cur:
                    execute_values(cur, pred_sql, pred_records)
                raw.commit()
                print(f"🎯 Generated {len(pred_records)} AQI predictions!")
            finally:
                raw.close()

    def start_streaming_simulation(self, duration_minutes=60, records_per_minute=100):
        """Simulate continuous data streaming"""
        print(f"🌊 Starting streaming simulation for {duration_minutes} minutes...")
        print(f"📊 Target: {records_per_minute} records per minute")
        
        end_time = time.time() + (duration_minutes * 60)
        records_generated = 0
        
        # Get active stations
        with self.engine.begin() as conn:
            stations = pd.read_sql("SELECT station_id, city_zone FROM scaqms.stations WHERE is_active", conn)
        
        while time.time() < end_time:
            batch_start = time.time()
            batch_size = min(records_per_minute // 10, 50)  # Generate in smaller batches
            
            # Generate batch of records
            records = []
            current_time = datetime.datetime.now(datetime.timezone.utc)
            
            for i in range(batch_size):
                station = stations.iloc[i % len(stations)]
                station_id = station['station_id']
                
                # Add some randomness to timestamps
                ts = current_time + datetime.timedelta(seconds=np.random.uniform(-30, 30))
                hour_float = ts.hour + ts.minute / 60
                
                # Generate realistic values
                diurnal = (1 + np.sin(2 * np.pi * hour_float / 24 - np.pi / 2)) / 2
                rush_hour = 1.0 + (0.3 if (7 <= ts.hour <= 9 or 17 <= ts.hour <= 19) else 0.0)
                
                pm25 = max(0, 15 + 20 * diurnal + np.random.normal(0, 4)) * rush_hour
                co2 = max(0, 420 + 80 * diurnal + np.random.normal(0, 20)) * rush_hour
                
                # Add occasional spikes
                if np.random.random() < 0.02:  # 2% chance of spike
                    pm25 *= np.random.uniform(2.0, 5.0)
                    co2 *= np.random.uniform(1.5, 3.0)
                
                records.append((
                    station_id, ts, round(co2, 2), round(pm25, 2), 
                    round(pm25 * 1.2, 2), round(np.random.uniform(0.01, 0.05), 3),
                    round(np.random.uniform(0.02, 0.04), 3), round(15 + 20 * diurnal + np.random.normal(0, 2), 2),
                    round(60 + 20 * np.sin(2 * np.pi * (hour_float + 8) / 24) + np.random.normal(0, 8), 2),
                    round(np.random.lognormal(mean=1.0, sigma=0.6), 2), round(np.random.uniform(0, 360), 2),
                    round(1013 + np.random.normal(0, 3), 2), "Normal", round(np.random.beta(8, 2), 2)
                ))
            
            # Insert batch
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
                records_generated += len(records)
            finally:
                raw.close()
            
            # Control rate
            batch_time = time.time() - batch_start
            sleep_time = max(0, (60 / (records_per_minute / batch_size)) - batch_time)
            time.sleep(sleep_time)
            
            if records_generated % 100 == 0:
                print(f"📊 Generated {records_generated} records...")
        
        print(f"✅ Streaming simulation completed! Generated {records_generated} total records.")

    def run_monitoring_loop(self, interval_seconds=60):
        """Run continuous monitoring loop for outlier detection and ML updates"""
        print(f"🔄 Starting monitoring loop (interval: {interval_seconds}s)")
        
        def monitor_cycle():
            try:
                print(f"🔄 Monitoring cycle at {datetime.datetime.now()}")
                
                # Run outlier detection
                outliers_found = self.detect_outliers(window_minutes=60, contamination=0.05)
                
                # Update ML model
                self.train_ml_model(window_minutes=120)
                
                # Record system metrics
                with self.engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO scaqms.system_metrics (metric_name, metric_value, metric_unit)
                        VALUES ('outliers_detected', :outliers, 'count'),
                               ('monitoring_cycle_time', :cycle_time, 'seconds')
                    """), {
                        "outliers": outliers_found,
                        "cycle_time": interval_seconds
                    })
                
                print(f"✅ Monitoring cycle completed. Outliers: {outliers_found}")
                
            except Exception as e:
                print(f"❌ Error in monitoring cycle: {e}")
        
        # Schedule monitoring
        schedule.every(interval_seconds).seconds.do(monitor_cycle)
        
        # Run initial cycle
        monitor_cycle()
        
        # Continue monitoring
        while True:
            schedule.run_pending()
            time.sleep(1)

def main():
    """Main deployment function"""
    print("🚀 Azure PostgreSQL Streaming Analytics Pipeline Deployment")
    print("=" * 60)
    
    deployer = AzureAQMSDeployer()
    
    try:
        # 1. Deploy schema
        deployer.deploy_schema()
        
        # 2. Seed stations
        deployer.seed_stations()
        
        # 3. Generate initial data
        deployer.generate_realistic_data(num_records=2000)
        
        # 4. Run initial outlier detection
        deployer.detect_outliers()
        
        # 5. Train initial ML model
        deployer.train_ml_model()
        
        print("\n🎉 Deployment completed successfully!")
        print("\nNext steps:")
        print("1. Run the dashboard: streamlit run app.py")
        print("2. Start streaming simulation: python azure_stream.py")
        print("3. Monitor system: python azure_monitor.py")
        
    except Exception as e:
        print(f"❌ Deployment failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    main()
