#!/usr/bin/env python3
"""
Test Azure PostgreSQL Connection
"""

import psycopg2
from sqlalchemy import create_engine, text

# Test different connection strings
connection_strings = [
    # Original connection string
    "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require",
    
    # URL encoded password
    "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require",
    
    # Using psycopg2 directly
    {
        "host": "bigdata-508-server.postgres.database.azure.com",
        "port": 5432,
        "database": "postgres",
        "user": "postgres",
        "password": "Azure123!@#",
        "sslmode": "require"
    }
]

def test_connection(conn_str, description):
    """Test a connection string"""
    print(f"\nTesting: {description}")
    try:
        if isinstance(conn_str, dict):
            # Direct psycopg2 connection
            conn = psycopg2.connect(**conn_str)
        else:
            # SQLAlchemy connection
            engine = create_engine(conn_str)
            conn = engine.connect()
        
        # Test query
        if isinstance(conn_str, dict):
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            result = cursor.fetchone()
            cursor.close()
        else:
            result = conn.execute(text("SELECT version();")).fetchone()
        
        print(f"SUCCESS: {description}")
        print(f"PostgreSQL version: {result[0][:50]}...")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"FAILED: {description}")
        print(f"Error: {e}")
        return False

def main():
    print("Azure PostgreSQL Connection Test")
    print("=" * 50)
    
    # Test all connection methods
    success = False
    for i, conn_str in enumerate(connection_strings):
        if i == 0:
            desc = "Original connection string"
        elif i == 1:
            desc = "URL encoded password"
        else:
            desc = "Direct psycopg2 connection"
        
        if test_connection(conn_str, desc):
            success = True
            break
    
    if not success:
        print("\n" + "=" * 50)
        print("ALL CONNECTION TESTS FAILED")
        print("=" * 50)
        print("Possible issues:")
        print("1. Password is incorrect")
        print("2. Your IP address is not whitelisted in Azure PostgreSQL firewall")
        print("3. SSL connection requirements")
        print("4. Server is not accessible")
        print("\nTo fix:")
        print("1. Verify the password in Azure portal")
        print("2. Add your IP (34.127.33.101) to Azure PostgreSQL firewall rules")
        print("3. Check SSL settings")
    else:
        print("\n" + "=" * 50)
        print("CONNECTION SUCCESSFUL!")
        print("=" * 50)

if __name__ == "__main__":
    main()
