#!/usr/bin/env python3
"""
Quick Schema Deployment - Faster deployment with progress tracking
"""

import psycopg2
import urllib.parse as urlparse

# Azure PostgreSQL connection
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

def quick_deploy():
    """Quick deployment with progress tracking"""
    
    print("🌆 Quick Schema Deployment")
    print("=" * 50)
    
    # Parse connection
    parsed = urlparse.urlparse(AZURE_CONNECTION_STRING)
    
    try:
        print("📡 Connecting to Azure PostgreSQL...")
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port,
            dbname=parsed.path[1:],
            user=parsed.username,
            password=parsed.password,
            connect_timeout=10
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        print("✅ Connected!")
        
        # Check if schema exists
        print("🔍 Checking existing schema...")
        cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'scaqms')")
        schema_exists = cur.fetchone()[0]
        
        if schema_exists:
            print("⚠️  Schema 'scaqms' exists. Dropping...")
            # Drop schema with CASCADE (this is what takes time)
            cur.execute('DROP SCHEMA IF EXISTS scaqms CASCADE')
            print("✅ Old schema dropped")
        else:
            print("✅ No existing schema found")
        
        # Create new schema
        print("📋 Creating new schema...")
        cur.execute('CREATE SCHEMA scaqms')
        
        # Create types
        print("🏷️  Creating custom types...")
        cur.execute("CREATE TYPE scaqms.severity AS ENUM ('Low','Moderate','High','Critical')")
        cur.execute("CREATE TYPE scaqms.sensor_status AS ENUM ('Active','Inactive','Maintenance','Offline')")
        cur.execute("CREATE TYPE scaqms.alert_status AS ENUM ('Open','Acknowledged','Resolved','Escalated')")
        
        # Create tables
        print("🏢 Creating stations table...")
        cur.execute("""
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
        """)
        
        print("🔧 Creating sensors table...")
        cur.execute("""
            CREATE TABLE scaqms.sensors (
                sensor_id SERIAL PRIMARY KEY,
                station_id INTEGER NOT NULL REFERENCES scaqms.stations(station_id) ON DELETE CASCADE,
                sensor_type VARCHAR(50) NOT NULL,
                sensor_model VARCHAR(100),
                serial_number VARCHAR(100) UNIQUE,
                status scaqms.sensor_status DEFAULT 'Active',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        print("📊 Creating readings table...")
        cur.execute("""
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
        """)
        
        print("🚨 Creating alerts table...")
        cur.execute("""
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
        """)
        
        print("🤖 Creating predictions table...")
        cur.execute("""
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
        """)
        
        # Create indexes
        print("🔍 Creating indexes...")
        cur.execute("CREATE INDEX idx_readings_station ON scaqms.air_quality_readings(station_id)")
        cur.execute("CREATE INDEX idx_readings_timestamp ON scaqms.air_quality_readings(timestamp DESC)")
        cur.execute("CREATE INDEX idx_alerts_station ON scaqms.alerts(station_id)")
        
        # Insert sample data
        print("📝 Inserting sample stations...")
        stations = [
            ('ST001', 'Downtown Central', 'Downtown', 40.7128, -74.0060),
            ('ST002', 'Uptown Residential', 'Uptown', 40.7870, -73.9754),
            ('ST003', 'Industrial Zone', 'Industrial', 40.6782, -73.9442),
            ('ST004', 'Harbor Waterfront', 'Harbor', 40.7003, -74.0122),
            ('ST005', 'Central Park', 'Park', 40.7712, -73.9742)
        ]
        
        for station in stations:
            cur.execute("""
                INSERT INTO scaqms.stations (station_code, station_name, city_zone, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s)
            """, station)
        
        print("📝 Inserting sample sensors...")
        sensors = [
            (1, 'PM2.5', 'Sensirion SPS30', 'PM25-ST001-001'),
            (1, 'CO2', 'SenseAir S8', 'CO2-ST001-001'),
            (2, 'PM2.5', 'Sensirion SPS30', 'PM25-ST002-001'),
            (2, 'CO2', 'SenseAir S8', 'CO2-ST002-001'),
            (3, 'PM2.5', 'Sensirion SPS30', 'PM25-ST003-001'),
            (4, 'PM2.5', 'Sensirion SPS30', 'PM25-ST004-001'),
            (5, 'PM2.5', 'Sensirion SPS30', 'PM25-ST005-001'),
        ]
        
        for sensor in sensors:
            cur.execute("""
                INSERT INTO scaqms.sensors (station_id, sensor_type, sensor_model, serial_number)
                VALUES (%s, %s, %s, %s)
            """, sensor)
        
        # Verify
        cur.execute("SELECT COUNT(*) FROM scaqms.stations")
        stations_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM scaqms.sensors")
        sensors_count = cur.fetchone()[0]
        
        print("\n" + "=" * 50)
        print("✅ Deployment Complete!")
        print("=" * 50)
        print(f"📊 Created 5 tables")
        print(f"📈 Inserted {stations_count} stations, {sensors_count} sensors")
        print("\nNext steps:")
        print("1. Run: python stream_generator.py --rate 200 --duration 2")
        print("2. Run: python -m streamlit run app.py")
        print("=" * 50)
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    quick_deploy()

