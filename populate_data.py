#!/usr/bin/env python3
"""
Populate sample air quality data
"""

import psycopg2
from sqlalchemy import create_engine, text
import urllib.parse as urlparse
import random
import datetime
import numpy as np

# Azure PostgreSQL connection
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

def populate_data():
    """Populate sample air quality data"""
    
    print("📊 Populating Air Quality Data")
    print("=" * 35)
    
    # Parse connection
    parsed = urlparse.urlparse(AZURE_CONNECTION_STRING)
    PG_HOST = parsed.hostname
    PG_PORT = parsed.port
    PG_DB = parsed.path[1:]
    PG_USER = parsed.username
    PG_PASS = parsed.password

    engine = create_engine(
        "postgresql+psycopg2://",
        connect_args={
            "host": PG_HOST,
            "port": PG_PORT,
            "dbname": PG_DB,
            "user": PG_USER,
            "password": PG_PASS
        }
    )
    
    try:
        with engine.begin() as conn:
            # Get stations and sensors
            stations = conn.execute(text("SELECT station_id FROM scaqms.stations")).fetchall()
            sensors = conn.execute(text("SELECT sensor_id, sensor_type FROM scaqms.sensors")).fetchall()
            
            print(f"Found {len(stations)} stations and {len(sensors)} sensors")
            
            readings = []
            predictions = []
            alerts = []
            
            # Generate data for last 24 hours
            start_time = datetime.datetime.now() - datetime.timedelta(hours=24)
            
            for hour in range(24):
                timestamp = start_time + datetime.timedelta(hours=hour)
                
                for station_id, in stations:
                    # Get sensors for this station
                    station_sensors = conn.execute(text("SELECT sensor_id, sensor_type FROM scaqms.sensors WHERE station_id = :sid"), {"sid": station_id}).fetchall()
                    
                    for sensor_id, sensor_type in station_sensors:
                        # Generate realistic values
                        if sensor_type == 'PM2.5':
                            base_pm25 = 15 + 20 * np.sin(hour * np.pi / 12) + random.uniform(-5, 5)
                            pm25 = max(0, round(base_pm25, 2))
                            
                            reading = {
                                'station_id': station_id,
                                'sensor_id': sensor_id,
                                'timestamp': timestamp,
                                'pm25': pm25,
                                'co2_ppm': None,
                                'temperature_c': round(20 + 10 * np.sin(hour * np.pi / 12) + random.uniform(-2, 2), 2),
                                'humidity_percent': round(50 + 20 * np.sin((hour + 6) * np.pi / 12) + random.uniform(-5, 5), 2),
                                'wind_speed_ms': round(random.uniform(0.5, 5.0), 2),
                                'data_quality_score': round(random.uniform(0.9, 1.0), 2)
                            }
                            
                            # Generate prediction
                            aqi_category = "Good" if pm25 <= 12 else "Moderate" if pm25 <= 35 else "Unhealthy" if pm25 <= 55 else "Hazardous"
                            prediction = {
                                'reading_id': None,  # Will be set after reading insert
                                'station_id': station_id,
                                'model_version': 'v1.0',
                                'predicted_aqi_category': aqi_category,
                                'confidence_score': round(random.uniform(0.8, 0.95), 3)
                            }
                            
                            readings.append(reading)
                            predictions.append(prediction)
                            
                            # Generate alerts for high values
                            if pm25 > 50:
                                alert = {
                                    'reading_id': None,  # Will be set after reading insert
                                    'station_id': station_id,
                                    'alert_type': 'PM2.5 High',
                                    'severity': 'Critical' if pm25 > 100 else 'High' if pm25 > 75 else 'Moderate',
                                    'status': 'Open',
                                    'message': f'PM2.5 level {pm25:.1f} μg/m³ exceeds safe threshold'
                                }
                                alerts.append(alert)
                        
                        elif sensor_type == 'CO2':
                            base_co2 = 400 + 100 * np.sin(hour * np.pi / 12) + random.uniform(-20, 20)
                            co2 = max(0, round(base_co2, 2))
                            
                            reading = {
                                'station_id': station_id,
                                'sensor_id': sensor_id,
                                'timestamp': timestamp,
                                'pm25': None,
                                'co2_ppm': co2,
                                'temperature_c': round(20 + 10 * np.sin(hour * np.pi / 12) + random.uniform(-2, 2), 2),
                                'humidity_percent': round(50 + 20 * np.sin((hour + 6) * np.pi / 12) + random.uniform(-5, 5), 2),
                                'wind_speed_ms': round(random.uniform(0.5, 5.0), 2),
                                'data_quality_score': round(random.uniform(0.9, 1.0), 2)
                            }
                            
                            readings.append(reading)
            
            # Insert readings and get IDs
            print("💾 Inserting readings...")
            reading_ids = []
            
            for reading in readings:
                result = conn.execute(text("""
                    INSERT INTO scaqms.air_quality_readings 
                    (station_id, sensor_id, timestamp, pm25, co2_ppm, temperature_c, humidity_percent, wind_speed_ms, data_quality_score)
                    VALUES (:station_id, :sensor_id, :timestamp, :pm25, :co2_ppm, :temperature_c, :humidity_percent, :wind_speed_ms, :data_quality_score)
                    RETURNING reading_id
                """), reading)
                
                reading_id = result.fetchone()[0]
                reading_ids.append(reading_id)
            
            # Insert predictions
            print("🤖 Inserting predictions...")
            for i, prediction in enumerate(predictions):
                prediction['reading_id'] = reading_ids[i]
                conn.execute(text("""
                    INSERT INTO scaqms.predictions 
                    (reading_id, station_id, model_version, predicted_aqi_category, confidence_score)
                    VALUES (:reading_id, :station_id, :model_version, :predicted_aqi_category, :confidence_score)
                """), prediction)
            
            # Insert alerts
            print("🚨 Inserting alerts...")
            for i, alert in enumerate(alerts):
                if i < len(reading_ids):
                    alert['reading_id'] = reading_ids[i]
                    conn.execute(text("""
                        INSERT INTO scaqms.alerts 
                        (reading_id, station_id, alert_type, severity, status, message)
                        VALUES (:reading_id, :station_id, :alert_type, :severity, :status, :message)
                    """), alert)
        
        print("✅ Sample data populated successfully!")
        
        # Show summary
        with engine.begin() as conn:
            readings_count = conn.execute(text("SELECT COUNT(*) FROM scaqms.air_quality_readings")).fetchone()[0]
            predictions_count = conn.execute(text("SELECT COUNT(*) FROM scaqms.predictions")).fetchone()[0]
            alerts_count = conn.execute(text("SELECT COUNT(*) FROM scaqms.alerts")).fetchone()[0]
            
            print(f"\n📈 Data Summary:")
            print(f"   - {readings_count} air quality readings")
            print(f"   - {predictions_count} predictions")
            print(f"   - {alerts_count} alerts")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = populate_data()
    if success:
        print("\n🎉 Data population completed!")
        print("Now you can run: streamlit run app.py")
    else:
        print("\n💥 Data population failed!")
