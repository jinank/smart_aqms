#!/usr/bin/env python3
"""
Azure PostgreSQL Streaming Analytics Monitor
Continuous monitoring system for outlier detection and ML model updates.

Usage: python azure_monitor.py --interval 60
"""

import argparse
import time
import datetime
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from psycopg2.extras import execute_values
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from joblib import dump, load
import pathlib
import threading
import signal
import sys

# Azure PostgreSQL connection
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

class StreamingMonitor:
    def __init__(self):
        self.engine = create_engine(
            AZURE_CONNECTION_STRING,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.running = False
        self.model_path = "aqi_model_azure.joblib"
        self.labels = ["Good", "Moderate", "Unhealthy", "Hazardous"]
        self.label_to_idx = {l: i for i, l in enumerate(self.labels)}
        self.cycle_count = 0
        self.total_outliers = 0
        self.total_predictions = 0
        
    def detect_outliers(self, window_minutes=60, contamination=0.05):
        """Enhanced outlier detection with multiple methods"""
        try:
            print("🔍 Running outlier detection...")
            
            # Get recent data with good quality
            query = """
                SELECT record_id, station_id, ts, co2_ppm, pm25, pm10, no2_ppm, o3_ppm,
                       temperature_c, humidity, wind_speed, atmospheric_pressure
                FROM scaqms.air_quality
                WHERE ts >= now() - INTERVAL :win 
                AND data_quality_score > 0.7
                AND co2_ppm IS NOT NULL AND pm25 IS NOT NULL
                ORDER BY ts ASC;
            """
            
            with self.engine.begin() as conn:
                df = pd.read_sql(text(query), conn, params={"win": f"{window_minutes} minutes"})
            
            if df.empty or len(df) < 20:
                print("⚠️ Insufficient data for outlier detection.")
                return 0
            
            # Feature engineering for anomaly detection
            feature_cols = ['co2_ppm', 'pm25', 'pm10', 'no2_ppm', 'o3_ppm', 
                           'temperature_c', 'humidity', 'wind_speed', 'atmospheric_pressure']
            
            # Handle missing values
            df_features = df[feature_cols].fillna(df[feature_cols].median())
            
            # Statistical outlier detection (Z-score method)
            z_scores = np.abs((df_features - df_features.mean()) / df_features.std())
            statistical_outliers = (z_scores > 3).any(axis=1)
            
            # Isolation Forest
            iso_forest = IsolationForest(
                contamination=contamination,
                random_state=42,
                n_estimators=200,
                max_samples=min(1000, len(df_features))
            )
            
            iso_scores = iso_forest.fit_predict(df_features)
            isolation_outliers = (iso_scores == -1)
            
            # Combine detection methods
            df['is_statistical_outlier'] = statistical_outliers
            df['is_isolation_outlier'] = isolation_outliers
            df['is_outlier'] = statistical_outliers | isolation_outliers
            
            outliers = df[df['is_outlier']]
            
            if outliers.empty:
                print("✅ No anomalies detected.")
                return 0
            
            # Generate detailed alerts
            alert_records = []
            for _, row in outliers.iterrows():
                # Determine severity based on pollution levels
                if row['pm25'] > 150 or row['co2_ppm'] > 1000:
                    severity = 'Critical'
                elif row['pm25'] > 100 or row['co2_ppm'] > 800:
                    severity = 'High'
                elif row['pm25'] > 55 or row['co2_ppm'] > 600:
                    severity = 'Moderate'
                else:
                    severity = 'Low'
                
                # Create detailed message
                message = (f"Anomaly detected at station {row['station_id']}: "
                          f"PM2.5={row['pm25']:.1f}μg/m³, CO2={row['co2_ppm']:.0f}ppm, "
                          f"Temp={row['temperature_c']:.1f}°C")
                
                # Calculate anomaly score
                anomaly_score = 0.8 if row['is_isolation_outlier'] else 0.6
                if row['is_statistical_outlier']:
                    anomaly_score += 0.2
                
                detection_method = []
                if row['is_statistical_outlier']:
                    detection_method.append("Statistical")
                if row['is_isolation_outlier']:
                    detection_method.append("IsolationForest")
                
                alert_records.append((
                    int(row['record_id']), int(row['station_id']), 'Anomaly', severity,
                    message, round(min(1.0, anomaly_score), 3), 
                    '|'.join(detection_method)
                ))
            
            # Insert alerts
            if alert_records:
                alert_sql = """
                    INSERT INTO scaqms.alerts 
                    (record_id, station_id, alert_type, severity, message, anomaly_score, detection_method)
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
            
        except Exception as e:
            print(f"❌ Outlier detection error: {e}")
            return 0
    
    def train_ml_model(self, window_minutes=120):
        """Enhanced ML model training with online learning"""
        try:
            print("🧠 Training ML model...")
            
            # Load training data
            query = """
                SELECT record_id, station_id, co2_ppm, pm25, pm10, no2_ppm, o3_ppm, 
                       temperature_c, humidity, wind_speed, atmospheric_pressure, aqi_bucket
                FROM scaqms.air_quality
                WHERE ts >= now() - INTERVAL :mins 
                AND aqi_bucket IS NOT NULL
                AND data_quality_score > 0.8
                AND co2_ppm IS NOT NULL AND pm25 IS NOT NULL;
            """
            
            with self.engine.begin() as conn:
                df = pd.read_sql(text(query), conn, params={"mins": f"{window_minutes} minutes"})
            
            if df.empty or len(df) < 30:
                print("⚠️ Insufficient training data.")
                return False
            
            # Feature engineering
            feature_cols = ['co2_ppm', 'pm25', 'pm10', 'no2_ppm', 'o3_ppm', 
                           'temperature_c', 'humidity', 'wind_speed', 'atmospheric_pressure']
            
            # Add derived features
            df['pm_ratio'] = df['pm10'] / (df['pm25'] + 0.001)  # Avoid division by zero
            df['temp_humidity'] = df['temperature_c'] * df['humidity']
            df['pollution_index'] = (df['pm25'] + df['no2_ppm'] * 100 + df['o3_ppm'] * 100)
            
            extended_features = feature_cols + ['pm_ratio', 'temp_humidity', 'pollution_index']
            
            X = df[extended_features].fillna(df[extended_features].median())
            y = df['aqi_bucket'].map(self.label_to_idx)
            
            # Remove unmapped labels
            valid_mask = ~y.isna()
            X = X[valid_mask]
            y = y[valid_mask]
            
            if len(X) < 20:
                print("⚠️ Insufficient valid training samples.")
                return False
            
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
                        random_state=42,
                        warm_start=True
                    ))
                ])
                # Initialize with dummy data
                dummy_X = np.zeros((1, len(extended_features)))
                dummy_y = np.array([0])
                model.named_steps["clf"].partial_fit(dummy_X, dummy_y, classes=np.arange(len(self.labels)))
                print("🆕 Initialized new model")
            
            # Online learning - partial fit
            model.named_steps["clf"].partial_fit(X, y)
            
            # Save updated model
            dump(model, self.model_path)
            print(f"💾 Model updated on {len(X)} samples")
            
            # Generate predictions
            self.generate_predictions(model, window_minutes)
            
            return True
            
        except Exception as e:
            print(f"❌ ML training error: {e}")
            return False
    
    def generate_predictions(self, model, window_minutes=60):
        """Generate predictions using trained model"""
        try:
            print("📈 Generating AQI predictions...")
            
            # Get recent data for prediction
            query = """
                SELECT record_id, station_id, co2_ppm, pm25, pm10, no2_ppm, o3_ppm,
                       temperature_c, humidity, wind_speed, atmospheric_pressure
                FROM scaqms.air_quality
                WHERE ts >= now() - INTERVAL :mins 
                AND data_quality_score > 0.7
                AND co2_ppm IS NOT NULL AND pm25 IS NOT NULL;
            """
            
            with self.engine.begin() as conn:
                df = pd.read_sql(text(query), conn, params={"mins": f"{window_minutes} minutes"})
            
            if df.empty:
                print("⚠️ No data for prediction.")
                return 0
            
            # Feature engineering (same as training)
            feature_cols = ['co2_ppm', 'pm25', 'pm10', 'no2_ppm', 'o3_ppm', 
                           'temperature_c', 'humidity', 'wind_speed', 'atmospheric_pressure']
            
            df['pm_ratio'] = df['pm10'] / (df['pm25'] + 0.001)
            df['temp_humidity'] = df['temperature_c'] * df['humidity']
            df['pollution_index'] = (df['pm25'] + df['no2_ppm'] * 100 + df['o3_ppm'] * 100)
            
            extended_features = feature_cols + ['pm_ratio', 'temp_humidity', 'pollution_index']
            X = df[extended_features].fillna(df[extended_features].median())
            
            # Generate predictions
            predictions = model.named_steps["clf"].predict(X)
            probabilities = model.named_steps["clf"].predict_proba(X)
            
            # Prepare prediction records
            pred_records = []
            for i, (_, row) in enumerate(df.iterrows()):
                pred_label = self.labels[predictions[i]]
                confidence = float(np.max(probabilities[i]))
                
                pred_records.append((
                    int(row['record_id']), int(row['station_id']), pred_label,
                    float(probabilities[i][0]), float(probabilities[i][1]), 
                    float(probabilities[i][2]), float(probabilities[i][3]),
                    confidence, 'v1.0'
                ))
            
            # Insert predictions
            if pred_records:
                pred_sql = """
                    INSERT INTO scaqms.predictions 
                    (record_id, station_id, aqi_pred, proba_good, proba_moderate, 
                     proba_unhealthy, proba_hazardous, confidence_score, model_version)
                    VALUES %s
                    ON CONFLICT (record_id) DO UPDATE SET
                        aqi_pred = EXCLUDED.aqi_pred,
                        proba_good = EXCLUDED.proba_good,
                        proba_moderate = EXCLUDED.proba_moderate,
                        proba_unhealthy = EXCLUDED.proba_unhealthy,
                        proba_hazardous = EXCLUDED.proba_hazardous,
                        confidence_score = EXCLUDED.confidence_score,
                        model_version = EXCLUDED.model_version,
                        predicted_at = now();
                """
                
                raw = self.engine.raw_connection()
                try:
                    with raw.cursor() as cur:
                        execute_values(cur, pred_sql, pred_records)
                    raw.commit()
                    print(f"🎯 Generated {len(pred_records)} AQI predictions!")
                    return len(pred_records)
                finally:
                    raw.close()
            
            return 0
            
        except Exception as e:
            print(f"❌ Prediction error: {e}")
            return 0
    
    def record_system_metrics(self, outliers_found, predictions_generated, cycle_time):
        """Record system performance metrics"""
        try:
            with self.engine.begin() as conn:
                # Record metrics
                metrics = [
                    ('outliers_detected', outliers_found, 'count'),
                    ('predictions_generated', predictions_generated, 'count'),
                    ('monitoring_cycle_time', cycle_time, 'seconds'),
                    ('total_cycles', self.cycle_count, 'count'),
                    ('avg_outliers_per_cycle', self.total_outliers / max(1, self.cycle_count), 'count'),
                    ('avg_predictions_per_cycle', self.total_predictions / max(1, self.cycle_count), 'count')
                ]
                
                for metric_name, value, unit in metrics:
                    conn.execute(text("""
                        INSERT INTO scaqms.system_metrics (metric_name, metric_value, metric_unit)
                        VALUES (:name, :value, :unit)
                    """), {"name": metric_name, "value": value, "unit": unit})
                
                # Clean up old metrics (keep last 1000 records)
                conn.execute(text("""
                    DELETE FROM scaqms.system_metrics 
                    WHERE metric_id NOT IN (
                        SELECT metric_id FROM scaqms.system_metrics 
                        ORDER BY recorded_at DESC LIMIT 1000
                    )
                """))
                
        except Exception as e:
            print(f"⚠️ Metrics recording error: {e}")
    
    def monitoring_cycle(self, outlier_window=60, ml_window=120):
        """Single monitoring cycle"""
        cycle_start = time.time()
        
        try:
            print(f"\n🔄 Monitoring cycle #{self.cycle_count + 1} at {datetime.datetime.now()}")
            
            # Run outlier detection
            outliers_found = self.detect_outliers(window_minutes=outlier_window, contamination=0.05)
            
            # Update ML model and generate predictions
            ml_success = self.train_ml_model(window_minutes=ml_window)
            predictions_generated = 0
            if ml_success:
                # Count new predictions
                with self.engine.begin() as conn:
                    result = conn.execute(text("""
                        SELECT COUNT(*) FROM scaqms.predictions 
                        WHERE predicted_at >= now() - INTERVAL '5 minutes'
                    """)).fetchone()
                    predictions_generated = result[0] if result else 0
            
            # Update counters
            self.cycle_count += 1
            self.total_outliers += outliers_found
            self.total_predictions += predictions_generated
            
            # Record metrics
            cycle_time = time.time() - cycle_start
            self.record_system_metrics(outliers_found, predictions_generated, cycle_time)
            
            print(f"✅ Cycle completed in {cycle_time:.1f}s - Outliers: {outliers_found}, Predictions: {predictions_generated}")
            
        except Exception as e:
            print(f"❌ Error in monitoring cycle: {e}")
    
    def run_monitoring(self, interval_seconds=60, outlier_window=60, ml_window=120):
        """Run continuous monitoring"""
        print(f"🔄 Starting monitoring system...")
        print(f"⏱️ Cycle interval: {interval_seconds} seconds")
        print(f"🔍 Outlier window: {outlier_window} minutes")
        print(f"🧠 ML training window: {ml_window} minutes")
        print("⏹️ Press Ctrl+C to stop")
        
        self.running = True
        
        try:
            while self.running:
                self.monitoring_cycle(outlier_window, ml_window)
                
                # Wait for next cycle
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print(f"\n⏹️ Stopping monitoring system...")
            self.running = False
            
            # Final report
            print(f"\n📊 Monitoring Summary:")
            print(f"   Total cycles: {self.cycle_count}")
            print(f"   Total outliers detected: {self.total_outliers}")
            print(f"   Total predictions generated: {self.total_predictions}")
            if self.cycle_count > 0:
                print(f"   Average outliers per cycle: {self.total_outliers / self.cycle_count:.1f}")
                print(f"   Average predictions per cycle: {self.total_predictions / self.cycle_count:.1f}")
    
    def stop(self):
        """Stop monitoring"""
        self.running = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print(f"\n⏹️ Received interrupt signal...")
    if 'monitor' in globals():
        monitor.stop()
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='Azure PostgreSQL Streaming Analytics Monitor')
    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval in seconds (default: 60)')
    parser.add_argument('--outlier-window', type=int, default=60, help='Outlier detection window in minutes (default: 60)')
    parser.add_argument('--ml-window', type=int, default=120, help='ML training window in minutes (default: 120)')
    
    args = parser.parse_args()
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    global monitor
    monitor = StreamingMonitor()
    
    try:
        monitor.run_monitoring(args.interval, args.outlier_window, args.ml_window)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
