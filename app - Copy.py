# app.py — Smart AQMS Dashboard (Upgraded with System Metrics Visualization)
# -----------------------------------------------------------------------------
# Now supports:
#   ✅ Real-time KPI refresh (auto + manual)
#   ✅ System performance trends (throughput, latency, avg PM2.5)
#   ✅ Interactive visualizations for predictions & alerts
# -----------------------------------------------------------------------------

import os
import datetime
import pandas as pd
import psycopg2
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import urllib.parse as urlparse

# -----------------------------------------------------------------------------
# 🌐 Database Config (Azure PostgreSQL)
# -----------------------------------------------------------------------------
AZURE_CONNECTION_STRING = "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"
parsed = urlparse.urlparse(AZURE_CONNECTION_STRING)
PG_HOST, PG_PORT, PG_DB = parsed.hostname, parsed.port, parsed.path[1:]
PG_USER, PG_PASS = parsed.username, parsed.password

# -----------------------------------------------------------------------------
# 🚀 Streamlit Page Config
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart AQMS Dashboard",
    layout="wide",
    page_icon="🌆",
    initial_sidebar_state="expanded"
)
st_autorefresh(interval=10000, key="auto_refresh")

st.title("🌆 Smart City Air Quality Monitoring System")
st.markdown("### Real-time Analytics, Alerts & Performance Insights")
st.caption(f"⏱️ Last updated: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")

# -----------------------------------------------------------------------------
# 🔗 Database Connection Helpers
# -----------------------------------------------------------------------------
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASS
    )

@st.cache_data(ttl=10)
def load_data(minutes=180, limit=5000):
    q = f"""
        SELECT a.*, s.city_zone, s.latitude, s.longitude, s.sensor_type,
               p.aqi_pred, p.proba_good, p.proba_moderate, p.proba_unhealthy,
               p.proba_hazardous, p.confidence_score, p.model_version
        FROM scaqms.air_quality a
        JOIN scaqms.stations s ON a.station_id = s.station_id
        LEFT JOIN scaqms.predictions p ON a.record_id = p.record_id
        WHERE a.ts >= now() - INTERVAL '{minutes} minutes'
        ORDER BY a.ts DESC
        LIMIT {limit};
    """
    try:
        return pd.read_sql(q, get_conn())
    except Exception as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=15)
def load_alerts(limit=200):
    q = f"""
        SELECT a.*, s.city_zone, s.latitude, s.longitude
        FROM scaqms.alerts a
        JOIN scaqms.stations s ON a.station_id = s.station_id
        ORDER BY a.created_at DESC LIMIT {limit};
    """
    try:
        return pd.read_sql(q, get_conn())
    except Exception as e:
        st.warning(f"Failed to load alerts: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=15)
def load_metrics(limit=300):
    q = f"""
        SELECT metric_name, metric_value, metric_unit, recorded_at
        FROM scaqms.system_metrics
        ORDER BY recorded_at DESC
        LIMIT {limit};
    """
    try:
        return pd.read_sql(q, get_conn())
    except Exception as e:
        st.warning(f"Could not load system metrics: {e}")
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# 🕹️ Sidebar Controls
# -----------------------------------------------------------------------------
st.sidebar.header("Dashboard Controls")
window = st.sidebar.slider("Time Window (minutes)", 15, 720, 180, step=15)
limit = st.sidebar.number_input("Record Limit", 500, 10000, 3000, step=500)
refresh = st.sidebar.button("🔄 Manual Refresh")

# -----------------------------------------------------------------------------
# 📊 Load Data
# -----------------------------------------------------------------------------
df = load_data(window, limit)
alerts = load_alerts()
metrics = load_metrics()

if df.empty:
    st.warning("⚠️ No live data detected. Please start your data generator.")
    st.stop()

# -----------------------------------------------------------------------------
# 📈 KPI Cards
# -----------------------------------------------------------------------------
col1, col2, col3, col4, col5 = st.columns(5)
avg_pm25 = df["pm25"].mean()
avg_co2 = df["co2_ppm"].mean()
max_pm25 = df["pm25"].max()
total_records = len(df)
active_alerts = len(alerts[alerts["is_resolved"] == False]) if not alerts.empty else 0

col1.metric("Avg PM2.5", f"{avg_pm25:.1f} µg/m³", "🔴" if avg_pm25 > 35 else "🟡" if avg_pm25 > 12 else "🟢")
col2.metric("Avg CO₂", f"{avg_co2:.0f} ppm", "🔴" if avg_co2 > 600 else "🟡" if avg_co2 > 500 else "🟢")
col3.metric("Max PM2.5", f"{max_pm25:.1f}", "🚨" if max_pm25 > 100 else "⚠️" if max_pm25 > 55 else "✅")
col4.metric("Total Records", f"{total_records:,}")
col5.metric("Active Alerts", active_alerts, "🚨" if active_alerts > 10 else "⚠️" if active_alerts > 0 else "✅")

# -----------------------------------------------------------------------------
# ⚙️ System Performance Charts
# -----------------------------------------------------------------------------
st.subheader("⚙️ System Performance Metrics (Live Updates)")

if not metrics.empty:
    metrics["recorded_at"] = pd.to_datetime(metrics["recorded_at"])
    throughput = metrics[metrics["metric_name"] == "ingest_throughput"]
    latency = metrics[metrics["metric_name"] == "ingest_latency"]
    pm25_batch = metrics[metrics["metric_name"] == "avg_pm25_batch"]

    colm1, colm2, colm3 = st.columns(3)

    if not throughput.empty:
        fig_throughput = px.line(
            throughput.sort_values("recorded_at"),
            x="recorded_at", y="metric_value",
            title="Ingestion Throughput (rows/min)",
            labels={"metric_value": "Rows per Minute", "recorded_at": "Time"},
        )
        colm1.plotly_chart(fig_throughput, use_container_width=True)

    if not latency.empty:
        fig_latency = px.line(
            latency.sort_values("recorded_at"),
            x="recorded_at", y="metric_value",
            title="Ingestion Latency (ms)",
            labels={"metric_value": "Latency (ms)", "recorded_at": "Time"},
        )
        colm2.plotly_chart(fig_latency, use_container_width=True)

    if not pm25_batch.empty:
        fig_pm = px.line(
            pm25_batch.sort_values("recorded_at"),
            x="recorded_at", y="metric_value",
            title="Avg PM2.5 per Batch (µg/m³)",
            labels={"metric_value": "µg/m³", "recorded_at": "Time"},
        )
        colm3.plotly_chart(fig_pm, use_container_width=True)

# -----------------------------------------------------------------------------
# 🌆 Air Quality Visualization
# -----------------------------------------------------------------------------
st.subheader("🌫️ Air Quality Trends")

fig1 = px.line(
    df.sort_values("ts"), x="ts", y="pm25", color="city_zone",
    title=f"PM2.5 Levels per Zone (Last {window} min)",
    labels={"ts": "Timestamp", "pm25": "PM2.5 (µg/m³)", "city_zone": "Zone"},
)
st.plotly_chart(fig1, use_container_width=True)

# -----------------------------------------------------------------------------
# 🚨 Alerts
# -----------------------------------------------------------------------------
st.subheader("🚨 Active Alerts")
if alerts.empty:
    st.info("✅ No recent alerts.")
else:
    unresolved = alerts[alerts["is_resolved"] == False]
    if not unresolved.empty:
        st.warning(f"{len(unresolved)} unresolved alerts detected!")
    st.dataframe(
        alerts[["created_at", "city_zone", "alert_type", "severity", "message", "anomaly_score"]],
        use_container_width=True, height=300
    )

# -----------------------------------------------------------------------------
# 🗺️ Map Visualization
# -----------------------------------------------------------------------------
st.subheader("🗺️ Latest Station Readings")

latest = (
    df.sort_values("ts")
      .drop_duplicates(subset=["station_id"], keep="last")
      .dropna(subset=["latitude", "longitude"])
)

fig3 = px.scatter_mapbox(
    latest, lat="latitude", lon="longitude", color="aqi_pred", size="pm25",
    hover_name="city_zone", zoom=9, height=500, title="Geospatial AQI (Latest Readings)",
    color_discrete_map={
        "Good": "#00E400", "Moderate": "#FFFF00", "Unhealthy": "#FF7E00", "Hazardous": "#99004C"
    },
)
fig3.update_layout(mapbox_style="open-street-map")
st.plotly_chart(fig3, use_container_width=True)

# -----------------------------------------------------------------------------
# 🧭 Footer
# -----------------------------------------------------------------------------
st.markdown("---")
st.caption("Smart AQMS Dashboard • Built by Justin, Sravani, and Jinank — Real-time Environmental Intelligence")
