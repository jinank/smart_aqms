#!/usr/bin/env python3
"""
Quick Schema Deployment for Smart AQMS
"""

import psycopg2
from sqlalchemy import create_engine, text
import urllib.parse as urlparse

# Azure PostgreSQL connection
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

def deploy_schema():
    """Deploy schema and populate with data"""
    
    print("🌆 Deploying Smart AQMS Schema to Azure PostgreSQL")
    print("=" * 50)
    
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
            # Drop and recreate schema
            print("🗑️  Dropping existing schema...")
            conn.execute(text('DROP SCHEMA IF EXISTS scaqms CASCADE'))
            conn.execute(text('CREATE SCHEMA scaqms'))
            
            # Create types
            print("🏷️  Creating custom types...")
            conn.execute(text("CREATE TYPE scaqms.severity AS ENUM ('Low','Moderate','High','Critical')"))
            conn.execute(text("CREATE TYPE scaqms.sensor_status AS ENUM ('Active','Inactive','Maintenance','Offline')"))
            conn.execute(text("CREATE TYPE scaqms.alert_status AS ENUM ('Open','Acknowledged','Resolved','Escalated')"))
            
            # Create tables
            print("🏢 Creating tables...")
            
            # Stations table
            conn.execute(text("""
                CREATE TABLE scaqms.stations (
                    station_id SERIAL PRIMARY KEY,
                    station_code VARCHAR(20) UNIQUE NOT NULL,
                    station_name VARCHAR(100) NOT NULL,
                    city_zone VARCHAR(100) NOT NULL,
                    latitude NUMERIC(9,6) NOT NULL,
                    longitude NUMERIC(9,6) NOT NULL,
                    status scaqms.sensor_status DEFAULT 'Active',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            
            # Sensors table
            conn.execute(text("""
                CREATE TABLE scaqms.sensors (
                    sensor_id SERIAL PRIMARY KEY,
                    station_id INTEGER NOT NULL REFERENCES scaqms.stations(station_id) ON DELETE CASCADE,
                    sensor_type VARCHAR(50) NOT NULL,
                    sensor_model VARCHAR(100),
                    serial_number VARCHAR(100) UNIQUE,
                    status scaqms.sensor_status DEFAULT 'Active',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            
            # Air quality readings table
            conn.execute(text("""
                CREATE TABLE scaqms.air_quality_readings (
                    reading_id BIGSERIAL PRIMARY KEY,
                    station_id INTEGER NOT NULL REFERENCES scaqms.stations(station_id) ON DELETE CASCADE,
                    sensor_id INTEGER NOT NULL REFERENCES scaqms.sensors(sensor_id) ON DELETE CASCADE,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    pm25 NUMERIC(10,2),
                    co2_ppm NUMERIC(10,2),
                    temperature_c NUMERIC(5,2),
                    humidity_percent NUMERIC(5,2),
                    wind_speed_ms NUMERIC(5,2),
                    data_quality_score NUMERIC(3,2) DEFAULT 0.95,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            
            # Alerts table
            conn.execute(text("""
                CREATE TABLE scaqms.alerts (
                    alert_id SERIAL PRIMARY KEY,
                    reading_id BIGINT REFERENCES scaqms.air_quality_readings(reading_id) ON DELETE CASCADE,
                    station_id INTEGER NOT NULL REFERENCES scaqms.stations(station_id) ON DELETE CASCADE,
                    alert_type VARCHAR(50) NOT NULL,
                    severity scaqms.severity NOT NULL,
                    status scaqms.alert_status DEFAULT 'Open',
                    message TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            
            # Predictions table
            conn.execute(text("""
                CREATE TABLE scaqms.predictions (
                    prediction_id SERIAL PRIMARY KEY,
                    reading_id BIGINT NOT NULL REFERENCES scaqms.air_quality_readings(reading_id) ON DELETE CASCADE,
                    station_id INTEGER NOT NULL REFERENCES scaqms.stations(station_id) ON DELETE CASCADE,
                    model_version VARCHAR(20) NOT NULL,
                    predicted_aqi_category TEXT NOT NULL,
                    confidence_score NUMERIC(6,5),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT uq_reading_prediction UNIQUE (reading_id)
                )
            """))
            
            # Create indexes
            print("🔍 Creating indexes...")
            conn.execute(text("CREATE INDEX idx_readings_station ON scaqms.air_quality_readings(station_id)"))
            conn.execute(text("CREATE INDEX idx_readings_timestamp ON scaqms.air_quality_readings(timestamp DESC)"))
            conn.execute(text("CREATE INDEX idx_alerts_station ON scaqms.alerts(station_id)"))
            conn.execute(text("CREATE INDEX idx_alerts_severity ON scaqms.alerts(severity)"))
            
            # Insert sample data
            print("📝 Adding sample data...")
            
            # Insert stations
            stations = [
                ('ST001', 'Downtown Central', 'Downtown', 40.7128, -74.0060),
                ('ST002', 'Uptown Residential', 'Uptown', 40.7870, -73.9754),
                ('ST003', 'Industrial Zone', 'Industrial', 40.6782, -73.9442),
                ('ST004', 'Harbor Waterfront', 'Harbor', 40.7003, -74.0122),
                ('ST005', 'Central Park', 'Park', 40.7712, -73.9742)
            ]
            
            for station in stations:
                conn.execute(text("""
                    INSERT INTO scaqms.stations (station_code, station_name, city_zone, latitude, longitude)
                    VALUES (:code, :name, :zone, :lat, :lon)
                """), {'code': station[0], 'name': station[1], 'zone': station[2], 'lat': station[3], 'lon': station[4]})
            
            # Insert sensors
            sensors = [
                (1, 'PM2.5', 'Sensirion SPS30', 'PM25-ST001-001'),
                (1, 'CO2', 'SenseAir S8', 'CO2-ST001-001'),
                (2, 'PM2.5', 'Sensirion SPS30', 'PM25-ST002-001'),
                (2, 'CO2', 'SenseAir S8', 'CO2-ST002-001'),
                (3, 'PM2.5', 'Sensirion SPS30', 'PM25-ST003-001'),
                (3, 'NO2', 'Alphasense NO2', 'NO2-ST003-001'),
                (4, 'PM2.5', 'Sensirion SPS30', 'PM25-ST004-001'),
                (4, 'Wind', 'Davis 6410', 'WIND-ST004-001'),
                (5, 'PM2.5', 'Sensirion SPS30', 'PM25-ST005-001'),
                (5, 'O3', 'Alphasense OX', 'O3-ST005-001')
            ]
            
            for sensor in sensors:
                conn.execute(text("""
                    INSERT INTO scaqms.sensors (station_id, sensor_type, sensor_model, serial_number)
                    VALUES (:station_id, :type, :model, :serial)
                """), {'station_id': sensor[0], 'type': sensor[1], 'model': sensor[2], 'serial': sensor[3]})
        
        print("✅ Schema deployed successfully!")
        
        # Verify deployment
        with engine.begin() as conn:
            tables = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'scaqms'")).fetchall()
            stations_count = conn.execute(text("SELECT COUNT(*) FROM scaqms.stations")).fetchone()[0]
            sensors_count = conn.execute(text("SELECT COUNT(*) FROM scaqms.sensors")).fetchone()[0]
            
            print(f"\n📊 Created {len(tables)} tables:")
            for table in tables:
                print(f"   - {table[0]}")
            print(f"\n📈 Sample data: {stations_count} stations, {sensors_count} sensors")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = deploy_schema()
    if success:
        print("\n🎉 Deployment completed!")
        print("Now you can run: streamlit run app.py")
    else:
        print("\n💥 Deployment failed!")
