# app.py  — Smart City Air Quality Monitoring System
import os
import datetime
import pandas as pd
import psycopg2
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ----------------------------------------------------
# 🚀 PAGE CONFIG — must be FIRST Streamlit command
# ----------------------------------------------------
st.set_page_config(
    page_title="Smart AQMS Dashboard",
    layout="wide",
    page_icon="🌆",
    initial_sidebar_state="expanded"
)

# ----------------------------------------------------
# 🔁 AUTO REFRESH (every 10 seconds for real-time feel)
# ----------------------------------------------------
st_autorefresh(interval=10000, key="realtime_refresh")

# ----------------------------------------------------
# 🌐 DATABASE CONFIG - Azure PostgreSQL
# ----------------------------------------------------
# Azure PostgreSQL connection string
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123!@#@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

# Parse connection string for individual components
import urllib.parse as urlparse
parsed = urlparse.urlparse(AZURE_CONNECTION_STRING)
PG_HOST = parsed.hostname
PG_PORT = parsed.port
PG_DB = parsed.path[1:]  # remove leading slash
PG_USER = parsed.username
PG_PASS = parsed.password

# ----------------------------------------------------
# 🧱 UI HEADER
# ----------------------------------------------------
st.title("🌆 Smart City Air Quality Monitoring System")
st.markdown("### Real-time Analytics & Predictive Insights")
st.caption(f"⏱️ Last updated: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")

# ----------------------------------------------------
# 🔗 DATABASE HELPERS
# ----------------------------------------------------
@st.cache_resource
def get_conn():
    """Create a persistent PostgreSQL connection."""
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS
    )

@st.cache_data(ttl=5)  # Reduced cache time for more real-time updates
def load_data(minutes=180, limit=5000):
    """Load recent air quality data with enhanced features."""
    q = f"""
        SELECT a.*, s.city_zone, s.latitude, s.longitude, s.sensor_type,
               p.aqi_pred, p.proba_good, p.proba_moderate, p.proba_unhealthy, p.proba_hazardous,
               p.confidence_score, p.model_version
        FROM scaqms.air_quality a
        JOIN scaqms.stations s ON a.station_id = s.station_id
        LEFT JOIN scaqms.predictions p ON a.record_id = p.record_id
        WHERE a.ts >= now() - INTERVAL '{minutes} minutes'
        ORDER BY a.ts DESC
        LIMIT {limit};
    """
    try:
        conn = get_conn()
        df = pd.read_sql(q, conn)
        return df
    except Exception as e:
        st.error(f"Database connection error: {e}")
        st.cache_resource.clear()
        try:
            conn = get_conn()
            df = pd.read_sql(q, conn)
            return df
        except Exception as e2:
            st.error(f"Failed to reconnect: {e2}")
            return pd.DataFrame()

@st.cache_data(ttl=10)  # More frequent alert updates
def load_alerts(limit=200):
    """Fetch recent alerts with station information."""
    q = f"""
        SELECT a.*, s.city_zone, s.latitude, s.longitude
        FROM scaqms.alerts a
        JOIN scaqms.stations s ON a.station_id = s.station_id
        ORDER BY a.created_at DESC 
        LIMIT {limit};
    """
    try:
        conn = get_conn()
        df = pd.read_sql(q, conn)
        return df
    except Exception as e:
        st.error(f"Alert loading error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def load_system_metrics(limit=100):
    """Load system performance metrics."""
    q = f"""
        SELECT metric_name, metric_value, metric_unit, recorded_at
        FROM scaqms.system_metrics
        ORDER BY recorded_at DESC
        LIMIT {limit};
    """
    try:
        conn = get_conn()
        df = pd.read_sql(q, conn)
        return df
    except Exception as e:
        st.warning(f"Could not load system metrics: {e}")
        return pd.DataFrame()

# ----------------------------------------------------
# 🕹️ SIDEBAR CONTROLS
# ----------------------------------------------------
st.sidebar.header("Dashboard Controls")
window = st.sidebar.slider("Time window (minutes)", 15, 720, 180, step=15)
limit  = st.sidebar.number_input("Record limit", 500, 10000, 3000, step=500)
refresh_button = st.sidebar.button("🔄 Refresh Now")

# ----------------------------------------------------
# 📊 LOAD DATA
# ----------------------------------------------------
status_placeholder = st.empty()
status_placeholder.text("Loading data from database...")

df = load_data(window, limit)
alerts = load_alerts()
metrics = load_system_metrics()
status_placeholder.text("✅ Data loaded successfully.")

if df.empty:
    st.warning("⚠️ No recent data. Please run the generator notebook.")
    st.stop()

# ----------------------------------------------------
# 📈 KPI METRICS
# ----------------------------------------------------
col1, col2, col3, col4, col5 = st.columns(5)

# Calculate metrics
avg_pm25 = df['pm25'].mean() if not df.empty else 0
avg_co2 = df['co2_ppm'].mean() if not df.empty else 0
max_pm25 = df['pm25'].max() if not df.empty else 0
total_records = len(df)
active_alerts = len(alerts[alerts['is_resolved'] == False]) if not alerts.empty else 0

col1.metric("Avg PM2.5", f"{avg_pm25:.1f} μg/m³", 
           delta=f"{'🔴' if avg_pm25 > 35 else '🟡' if avg_pm25 > 12 else '🟢'}")
col2.metric("Avg CO₂", f"{avg_co2:.0f} ppm", 
           delta=f"{'🔴' if avg_co2 > 600 else '🟡' if avg_co2 > 500 else '🟢'}")
col3.metric("Max PM2.5", f"{max_pm25:.1f} μg/m³",
           delta=f"{'🚨' if max_pm25 > 100 else '⚠️' if max_pm25 > 55 else '✅'}")
col4.metric("Total Records", f"{total_records:,}")
col5.metric("Active Alerts", f"{active_alerts}", 
           delta=f"{'🚨' if active_alerts > 10 else '⚠️' if active_alerts > 0 else '✅'}")

# System metrics
if not metrics.empty:
    recent_metrics = metrics.head(10)
    st.sidebar.subheader("📊 System Metrics")
    for _, metric in recent_metrics.iterrows():
        st.sidebar.metric(
            metric['metric_name'].replace('_', ' ').title(),
            f"{metric['metric_value']:.2f} {metric['metric_unit']}"
        )

# ----------------------------------------------------
# 🌆 VISUALIZATIONS
# ----------------------------------------------------
aqi_colors = {
    "Good": "#00E400",
    "Moderate": "#FFFF00",
    "Unhealthy": "#FF7E00",
    "Hazardous": "#99004C",
    None: "#808080"
}

# PM2.5 trends
fig1 = px.line(
    df.sort_values("ts"), x="ts", y="pm25", color="city_zone",
    title=f"PM2.5 Levels per Zone (Last {window} minutes)",
    labels={"ts": "Timestamp", "pm25": "PM2.5 (µg/m³)", "city_zone": "Zone"}
)
fig1.update_layout(legend=dict(orientation="h", y=1.05, x=1, xanchor="right"))
st.plotly_chart(fig1, use_container_width=True)

# AQI predictions
fig2 = px.scatter(
    df, x="ts", y="pm25", color="aqi_pred",
    color_discrete_map=aqi_colors,
    hover_data=["city_zone", "co2_ppm", "temperature_c", "humidity", "wind_speed"],
    title="Predicted AQI over Time"
)
fig2.update_traces(marker=dict(size=9, line=dict(width=1, color='DarkSlateGrey')))
fig2.update_layout(plot_bgcolor='white', paper_bgcolor='white')
st.plotly_chart(fig2, use_container_width=True)

# ----------------------------------------------------
# 🚨 ALERTS TABLE
# ----------------------------------------------------
st.subheader("🚨 Recent Alerts")
if alerts.empty:
    st.info("✅ No alerts detected recently.")
else:
    # Filter unresolved alerts
    unresolved = alerts[alerts['is_resolved'] == False]
    
    if not unresolved.empty:
        st.warning(f"⚠️ {len(unresolved)} unresolved alerts detected!")
        
        # Show severity breakdown
        severity_counts = unresolved['severity'].value_counts()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Critical", severity_counts.get('Critical', 0), delta="🚨")
        col2.metric("High", severity_counts.get('High', 0), delta="🔴")
        col3.metric("Moderate", severity_counts.get('Moderate', 0), delta="🟡")
        col4.metric("Low", severity_counts.get('Low', 0), delta="🟢")
    
    # Display alerts with better formatting
    display_alerts = alerts[['created_at', 'city_zone', 'alert_type', 'severity', 'message', 'anomaly_score']].copy()
    display_alerts['created_at'] = pd.to_datetime(display_alerts['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Color code severity
    def color_severity(val):
        colors = {'Critical': 'background-color: #ffebee', 'High': 'background-color: #fff3e0',
                 'Moderate': 'background-color: #fffde7', 'Low': 'background-color: #f3e5f5'}
        return colors.get(val, '')
    
    styled_alerts = display_alerts.style.applymap(color_severity, subset=['severity'])
    st.dataframe(styled_alerts, use_container_width=True, height=300)

# ----------------------------------------------------
# 🗺️ MAP VIEW
# ----------------------------------------------------
st.subheader("🗺️ Latest Station Readings")
latest = (
    df.sort_values("ts")
      .drop_duplicates(subset=["station_id"], keep="last")
      .dropna(subset=["latitude", "longitude"])
)

fig3 = px.scatter_mapbox(
    latest, lat="latitude", lon="longitude", color="aqi_pred", size="pm25",
    hover_name="city_zone", color_discrete_map=aqi_colors,
    zoom=10, height=500, title="Geospatial AQI (Latest Readings)"
)
fig3.update_layout(mapbox_style="open-street-map")
st.plotly_chart(fig3, use_container_width=True)

# ----------------------------------------------------
# ℹ️ FOOTER
# ----------------------------------------------------
st.markdown("""
---
**Smart AQMS** © 2025 — Real-time Environmental Intelligence  
Built with ❤️ using Streamlit, PostgreSQL, and Scikit-learn.
""")
