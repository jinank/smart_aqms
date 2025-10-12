#!/usr/bin/env python3
"""Check what exists in the Azure PostgreSQL database"""

import psycopg2
import urllib.parse as urlparse

AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

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
    cur = conn.cursor()
    print("✅ Connected!\n")
    
    # Check if schema exists
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'scaqms')")
    schema_exists = cur.fetchone()[0]
    
    if schema_exists:
        print("✅ Schema 'scaqms' EXISTS\n")
        
        # List tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'scaqms' 
            ORDER BY table_name
        """)
        tables = cur.fetchall()
        
        print(f"📊 Found {len(tables)} tables:")
        for table in tables:
            print(f"   - {table[0]}")
            
            # Count rows in each table
            try:
                cur.execute(f"SELECT COUNT(*) FROM scaqms.{table[0]}")
                count = cur.fetchone()[0]
                print(f"     ({count:,} rows)")
            except:
                print(f"     (unable to count)")
        
        print("\n" + "=" * 50)
        print("💡 The schema already exists!")
        print("You can either:")
        print("1. Use existing schema - run: python stream_generator.py")
        print("2. Drop manually in Azure Portal if needed")
        print("=" * 50)
    else:
        print("❌ Schema 'scaqms' DOES NOT exist")
        print("\n💡 Run: python quick_deploy.py")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")

