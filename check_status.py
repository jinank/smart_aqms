#!/usr/bin/env python3
"""
Check the status of the streaming analytics pipeline
"""

import requests
import time
from sqlalchemy import create_engine, text

# Azure PostgreSQL connection
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123%21%40%23@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

def check_database():
    """Check database connection and data"""
    try:
        engine = create_engine(AZURE_CONNECTION_STRING)
        with engine.begin() as conn:
            # Check tables exist
            tables = conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'scaqms'
                ORDER BY table_name;
            """)).fetchall()
            
            print("Database Tables:")
            for table in tables:
                print(f"  - {table[0]}")
            
            # Check recent data
            recent_data = conn.execute(text("""
                SELECT COUNT(*) as total_records,
                       MAX(ts) as latest_record,
                       COUNT(DISTINCT station_id) as active_stations
                FROM scaqms.air_quality
                WHERE ts >= now() - INTERVAL '1 hour';
            """)).fetchone()
            
            print(f"\nRecent Data (last hour):")
            print(f"  - Total records: {recent_data[0]}")
            print(f"  - Latest record: {recent_data[1]}")
            print(f"  - Active stations: {recent_data[2]}")
            
            # Check alerts
            alerts = conn.execute(text("""
                SELECT COUNT(*) as total_alerts,
                       COUNT(*) FILTER (WHERE is_resolved = false) as unresolved_alerts
                FROM scaqms.alerts
                WHERE created_at >= now() - INTERVAL '1 hour';
            """)).fetchone()
            
            print(f"\nRecent Alerts (last hour):")
            print(f"  - Total alerts: {alerts[0]}")
            print(f"  - Unresolved alerts: {alerts[1]}")
            
            # Check predictions
            predictions = conn.execute(text("""
                SELECT COUNT(*) as total_predictions,
                       COUNT(DISTINCT aqi_pred) as prediction_categories
                FROM scaqms.predictions
                WHERE predicted_at >= now() - INTERVAL '1 hour';
            """)).fetchone()
            
            print(f"\nRecent Predictions (last hour):")
            print(f"  - Total predictions: {predictions[0]}")
            print(f"  - Prediction categories: {predictions[1]}")
            
        return True
        
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False

def check_dashboard():
    """Check if Streamlit dashboard is running"""
    try:
        response = requests.get("http://localhost:8501", timeout=5)
        if response.status_code == 200:
            print("Dashboard Status: RUNNING")
            print("Access URL: http://localhost:8501")
            return True
        else:
            print(f"Dashboard Status: ERROR (HTTP {response.status_code})")
            return False
    except requests.exceptions.RequestException:
        print("Dashboard Status: NOT RUNNING")
        return False

def main():
    print("Streaming Analytics Pipeline Status Check")
    print("=" * 50)
    
    # Check database
    print("\n1. Database Connection:")
    db_ok = check_database()
    
    # Check dashboard
    print("\n2. Dashboard Status:")
    dashboard_ok = check_dashboard()
    
    print("\n" + "=" * 50)
    print("SUMMARY:")
    print(f"Database: {'OK' if db_ok else 'FAILED'}")
    print(f"Dashboard: {'OK' if dashboard_ok else 'FAILED'}")
    
    if db_ok and dashboard_ok:
        print("\nAll systems operational!")
        print("Visit http://localhost:8501 to see the dashboard")
    else:
        print("\nSome systems need attention:")
        if not db_ok:
            print("- Check database connection")
        if not dashboard_ok:
            print("- Start dashboard with: python -m streamlit run app.py")

if __name__ == "__main__":
    main()
