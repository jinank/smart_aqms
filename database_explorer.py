#!/usr/bin/env python3
"""
Database Explorer - Connect to Azure PostgreSQL and explore the database
"""

import psycopg2
from sqlalchemy import create_engine, text
import pandas as pd

# Azure PostgreSQL connection - URL encoded password
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123%21%40%23@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

def explore_database():
    """Explore the database structure and data"""
    print("Azure PostgreSQL Database Explorer")
    print("=" * 50)
    
    try:
        # Connect using SQLAlchemy
        engine = create_engine(AZURE_CONNECTION_STRING)
        
        with engine.begin() as conn:
            print("✅ Connected to Azure PostgreSQL successfully!")
            print(f"Database: postgres")
            print(f"Server: bigdata-508-server.postgres.database.azure.com")
            print()
            
            # Show database information
            print("📊 DATABASE INFORMATION:")
            print("-" * 30)
            
            # Show schemas
            schemas = conn.execute(text("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ORDER BY schema_name;
            """)).fetchall()
            
            print("Schemas:")
            for schema in schemas:
                print(f"  - {schema[0]}")
            print()
            
            # Show tables in scaqms schema
            print("📋 TABLES IN scaqms SCHEMA:")
            print("-" * 30)
            
            tables = conn.execute(text("""
                SELECT table_name, table_type
                FROM information_schema.tables 
                WHERE table_schema = 'scaqms'
                ORDER BY table_name;
            """)).fetchall()
            
            for table in tables:
                print(f"  - {table[0]} ({table[1]})")
            print()
            
            # Show table details
            for table_name in ['stations', 'air_quality', 'alerts', 'predictions']:
                print(f"🔍 TABLE: {table_name.upper()}")
                print("-" * 30)
                
                # Get row count
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM scaqms.{table_name}")).fetchone()
                row_count = count_result[0]
                print(f"Total rows: {row_count:,}")
                
                if row_count > 0:
                    # Show sample data
                    sample = conn.execute(text(f"""
                        SELECT * FROM scaqms.{table_name} 
                        ORDER BY 
                        CASE 
                            WHEN '{table_name}' = 'stations' THEN station_id
                            WHEN '{table_name}' = 'air_quality' THEN record_id
                            WHEN '{table_name}' = 'alerts' THEN alert_id
                            WHEN '{table_name}' = 'predictions' THEN prediction_id
                        END DESC
                        LIMIT 3;
                    """)).fetchall()
                    
                    if sample:
                        print("Sample data (last 3 records):")
                        for row in sample:
                            print(f"  {dict(row._mapping)}")
                
                print()
            
            # Show recent activity
            print("📈 RECENT ACTIVITY (Last Hour):")
            print("-" * 30)
            
            # Recent air quality data
            recent_aq = conn.execute(text("""
                SELECT COUNT(*) as total_records,
                       MAX(ts) as latest_record,
                       COUNT(DISTINCT station_id) as active_stations
                FROM scaqms.air_quality
                WHERE ts >= now() - INTERVAL '1 hour';
            """)).fetchone()
            
            print(f"Air Quality Records: {recent_aq[0]:,}")
            print(f"Latest Record: {recent_aq[1]}")
            print(f"Active Stations: {recent_aq[2]}")
            
            # Recent alerts
            recent_alerts = conn.execute(text("""
                SELECT COUNT(*) as total_alerts,
                       COUNT(*) FILTER (WHERE is_resolved = false) as unresolved
                FROM scaqms.alerts
                WHERE created_at >= now() - INTERVAL '1 hour';
            """)).fetchone()
            
            print(f"Recent Alerts: {recent_alerts[0]:,} (unresolved: {recent_alerts[1]:,})")
            
            # Recent predictions
            recent_preds = conn.execute(text("""
                SELECT COUNT(*) as total_predictions
                FROM scaqms.predictions
                WHERE predicted_at >= now() - INTERVAL '1 hour';
            """)).fetchone()
            
            print(f"Recent Predictions: {recent_preds[0]:,}")
            print()
            
            # Show partition information
            print("🗂️ PARTITION INFORMATION:")
            print("-" * 30)
            
            partitions = conn.execute(text("""
                SELECT schemaname, tablename, 
                       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables 
                WHERE schemaname = 'scaqms' 
                AND tablename LIKE 'air_quality_%'
                ORDER BY tablename;
            """)).fetchall()
            
            for partition in partitions:
                print(f"  - {partition[1]} ({partition[2]})")
            
            print()
            
            # Show current connections
            print("🔗 CONNECTION INFORMATION:")
            print("-" * 30)
            
            connections = conn.execute(text("""
                SELECT COUNT(*) as active_connections,
                       COUNT(*) FILTER (WHERE state = 'active') as active_queries
                FROM pg_stat_activity 
                WHERE datname = 'postgres';
            """)).fetchone()
            
            print(f"Active Connections: {connections[0]}")
            print(f"Active Queries: {connections[1]}")
            
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return False
    
    return True

def run_custom_query(query):
    """Run a custom SQL query"""
    try:
        engine = create_engine(AZURE_CONNECTION_STRING)
        with engine.begin() as conn:
            result = conn.execute(text(query))
            
            if result.returns_rows:
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                print(f"Query Result ({len(df)} rows):")
                print(df.to_string(index=False))
            else:
                print("Query executed successfully (no rows returned)")
                
    except Exception as e:
        print(f"❌ Query error: {e}")

if __name__ == "__main__":
    if explore_database():
        print("\n" + "=" * 50)
        print("Database exploration completed successfully!")
        
        # Example queries you can run
        print("\n💡 Example queries you can run:")
        print("- SELECT * FROM scaqms.stations LIMIT 5;")
        print("- SELECT COUNT(*) FROM scaqms.air_quality WHERE ts >= now() - INTERVAL '1 hour';")
        print("- SELECT * FROM scaqms.alerts ORDER BY created_at DESC LIMIT 10;")
    else:
        print("Failed to connect to database")
