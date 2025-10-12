# Smart AQMS Dashboard - Feature Reference 🎨

## 🚀 Quick Start

```bash
# Ensure all packages are installed
pip install -r requirements.txt

# Run the enhanced dashboard
streamlit run app.py
```

**Dashboard URL:** http://localhost:8501

---

## 📊 Dashboard Layout

### Header Section
- **Title:** Smart City Air Quality Monitoring System
- **Subtitle:** Real-time Analytics & Predictive Insights
- **Last Updated:** Live timestamp
- **Auto-refresh notice:** "🔁 Dashboard auto-refreshes every 30 seconds"

### Top Metrics (KPI Cards)
1. **Active Stations** - Number of currently active monitoring stations
2. **Latest PM2.5** - Most recent particulate matter reading (µg/m³)
3. **Active Alerts** - Count of unresolved warnings
4. **Avg Temperature** - Average temperature across all stations (°C)

### Sidebar Controls
- **Time Window:** 30/60/90/180 minutes (default: 180)
- **Record Limit:** 100-3000 records (default: 1000)
- **Latest System Metrics:** Real-time throughput, latency, accuracy

---

## 🎯 Tab Navigation

### Tab 1: 📊 Overview
**Purpose:** High-level air quality trends and predictions

**Visualizations:**
1. **PM2.5 Levels per Zone**
   - Line chart showing trends by city zone
   - Color-coded by zone
   - X-axis: Timestamp, Y-axis: PM2.5 (µg/m³)
   - Legend: Horizontal at top

2. **Predicted AQI over Time**
   - Scatter plot with color-coded AQI predictions
   - Colors: Green (Good), Yellow (Moderate), Orange (Unhealthy), Red (Hazardous)
   - Hover details: zone, CO2, temperature, humidity, wind speed
   - Size indicates PM2.5 concentration

**Use Cases:**
- Identify pollution hotspots
- Track temporal patterns
- Compare zones
- Validate ML predictions

---

### Tab 2: 🚨 Alerts
**Purpose:** Monitor and manage air quality warnings

**Features:**
1. **Alert Banner**
   - Shows count of unresolved alerts
   - Warning color if alerts exist
   - Success message if none

2. **Severity Breakdown**
   - 4 metric cards: Critical 🚨, High 🔴, Moderate 🟡, Low 🟢
   - Live counts per severity level
   - Quick visual assessment

3. **Alert Table**
   - Columns: Created At, Zone, Type, Severity, Message, Status
   - Color-coded rows by severity:
     - Critical: Red background (#ffebee)
     - High: Orange background (#fff3e0)
     - Moderate: Yellow background (#fffde7)
     - Low: Purple background (#f3e5f5)
   - Sortable columns
   - 400px height with scrolling

**Use Cases:**
- Emergency response prioritization
- Compliance monitoring
- Historical alert analysis
- Incident tracking

---

### Tab 3: 🗺️ Map
**Purpose:** Geospatial visualization of station data

**Features:**
1. **Interactive Map**
   - OpenStreetMap base layer
   - Station markers at lat/long coordinates
   - Zoom level 10 (city-wide view)
   - 600px height for better visibility

2. **Marker Details**
   - Color: AQI prediction category
   - Size: PM2.5 concentration (larger = higher)
   - Hover: Shows city zone name
   - Click: Displays full station details

3. **Map Controls**
   - Zoom in/out buttons
   - Pan by dragging
   - Reset to default view
   - Fullscreen mode

**Use Cases:**
- Identify pollution clusters
- Plan sensor deployment
- Emergency routing
- Public communication

**Data:** Shows latest reading per station (deduplicated)

---

### Tab 4: 📈 System Metrics
**Purpose:** Monitor platform performance and health

**Section 1: Metric Trends**
- **Layout:** Two-column grid
- **Metrics Displayed:** Up to 6 time-series charts
- **Common Metrics:**
  - `ingest_throughput` - Records ingested per minute
  - `ingest_latency` - Data processing delay (ms)
  - `stream_model_accuracy` - ML prediction accuracy (%)
  - `system_uptime` - Platform availability (%)
  - `memory_usage` - RAM consumption (MB)
  - `cpu_usage` - Processor utilization (%)

**Chart Details:**
- Type: Line chart
- Height: 200px per chart
- X-axis: Timestamp (auto-formatted)
- Y-axis: Metric value
- Minimum data points: 2 (to show trend)

**Section 2: Recent Metrics Data**
- **Table Display:** Last 20 metric records
- **Columns:** 
  - Metric Name (formatted with title case)
  - Metric Value (numeric, 2 decimal places)
  - Metric Unit
  - Recorded At (formatted: YYYY-MM-DD HH:MM:SS)
- **Use:** Drill-down for exact values

**Use Cases:**
- System health monitoring
- Performance troubleshooting
- Capacity planning
- SLA compliance

---

## 🔧 Performance Optimizations

### Data Loading
```python
@st.cache_data(ttl=30)  # Cache for 30 seconds
def load_data(minutes=180, limit=1000):
    # Optimized query with subquery
    # Limits records BEFORE joining (much faster)
```

### Benefits:
- ✅ Reduced database load
- ✅ Faster page loads (2-5 seconds vs 30+ seconds)
- ✅ Lower memory usage
- ✅ Better user experience

### Auto-refresh Settings:
- **Interval:** 30 seconds (30000ms)
- **Cache TTL:** 30 seconds
- **Default Records:** 1000
- **Default Time Window:** 180 minutes

---

## 🎨 Design Specifications

### Color Palette

**AQI Colors (Standard EPA):**
- Good: `#00E400` (Bright Green)
- Moderate: `#FFFF00` (Yellow)
- Unhealthy: `#FF7E00` (Orange)
- Hazardous: `#99004C` (Dark Red)
- Unknown: `#808080` (Gray)

**Alert Severity Colors:**
- Critical: `#ffebee` (Light Red)
- High: `#fff3e0` (Light Orange)
- Moderate: `#fffde7` (Light Yellow)
- Low: `#f3e5f5` (Light Purple)

**Chart Background:**
- Plot: White
- Paper: White
- Clean, professional appearance

### Typography
- Headers: Streamlit default (Source Sans Pro)
- Monospace code: Consolas/Monaco
- Emojis for visual hierarchy (📊 🚨 🗺️ 📈)

### Spacing
- Tab height: Auto-adjusts to content
- Chart height: 500-600px
- Table height: 300-400px
- Metric cards: Auto-grid layout

---

## 🔐 Security Features

### Secrets Management
- **File:** `.streamlit/secrets.toml`
- **Status:** Git-ignored (never committed)
- **Format:** TOML key-value pairs
- **Access:** `st.secrets["postgres"]["url"]`

### Best Practices Implemented:
✅ Credentials separated from code  
✅ `.gitignore` configured  
✅ SSL mode required for connections  
✅ No plaintext passwords in code  
✅ Ready for Azure Key Vault integration  

---

## 📱 Responsive Design

### Desktop (1920x1080+)
- Full-width charts
- Two-column metric layouts
- All content visible without scrolling per tab

### Laptop (1366x768)
- Charts scale to container width
- Sidebar collapsible
- Vertical scrolling per tab

### Tablet/Mobile
- Streamlit automatically adapts
- Sidebar becomes hamburger menu
- Charts stack vertically
- Touch-friendly controls

---

## 🎬 Presentation Mode Tips

### 1. Pre-Demo Checklist
- [ ] Start Streamlit: `streamlit run app.py`
- [ ] Verify database connection (check KPI cards)
- [ ] Refresh browser to clear cache
- [ ] Set time window to 180 minutes
- [ ] Expand to fullscreen (F11)

### 2. Demo Flow (5 minutes)
1. **Overview Tab (1 min)**
   - Show PM2.5 trends
   - Highlight zone differences
   - Mention ML predictions

2. **Alerts Tab (1 min)**
   - Count active alerts
   - Show severity breakdown
   - Explain color coding

3. **Map Tab (1 min)**
   - Show station locations
   - Interact with map (zoom/pan)
   - Explain marker colors/sizes

4. **System Metrics Tab (1.5 min)**
   - Show performance trends
   - Explain self-monitoring
   - Highlight system health

5. **Q&A (0.5 min)**
   - Mention auto-refresh
   - Explain database schema
   - Discuss scalability

### 3. Key Talking Points
- "Real-time data streaming from Azure PostgreSQL"
- "6,500+ readings with perfect referential integrity"
- "ML-powered AQI predictions"
- "Auto-refreshing dashboard every 30 seconds"
- "Production-ready with secure credential management"

---

## 🐛 Troubleshooting

### Dashboard shows "No recent data"
**Solution:** Run data generator:
```bash
python stream_generator.py
```

### Slow loading (30+ seconds)
**Solution:** Already optimized! If still slow:
1. Reduce record limit in sidebar (e.g., 500)
2. Decrease time window (e.g., 60 minutes)
3. Check database connection latency

### "Connection refused" error
**Solution:** 
1. Verify Azure PostgreSQL is running
2. Check connection string in `secrets.toml`
3. Ensure SSL mode is correct
4. Verify firewall rules allow your IP

### Charts not updating
**Solution:**
1. Clear Streamlit cache: Press 'C' in browser
2. Refresh browser (Ctrl+F5)
3. Check auto-refresh is enabled
4. Verify new data is being inserted

### Import errors
**Solution:**
```bash
pip install -r requirements.txt
```

---

## 📊 Data Schema Reference

### Tables Used by Dashboard

**`scaqms.air_quality`**
- `record_id` (PK)
- `station_id` (FK → stations)
- `ts` (timestamp)
- `pm25`, `co2_ppm`, `temperature_c`, `humidity`, `wind_speed`

**`scaqms.stations`**
- `station_id` (PK)
- `station_name`, `city_zone`
- `latitude`, `longitude`
- `sensor_type`, `status`

**`scaqms.predictions`**
- `prediction_id` (PK)
- `record_id` (FK → air_quality)
- `aqi_pred` (Good/Moderate/Unhealthy/Hazardous)
- `confidence_score`, `model_version`

**`scaqms.alerts`**
- `alert_id` (PK)
- `station_id` (FK → stations)
- `alert_type`, `severity`, `message`
- `status` (Open/Resolved)
- `created_at`, `resolved_at`

**`scaqms.system_metrics`**
- `metric_id` (PK)
- `metric_name`, `metric_value`, `metric_unit`
- `recorded_at`

---

## 🎓 Educational Value

### Course Deliverables Met
✅ **Relational Schema** - 5 interrelated tables  
✅ **Primary Keys** - Unique identifiers for all tables  
✅ **Foreign Keys** - Referential integrity enforced  
✅ **Constraints** - Data validation (CHECK, NOT NULL)  
✅ **Indexes** - Query optimization  
✅ **Real Data** - 6,500+ readings  
✅ **Visualization** - Interactive dashboard  
✅ **Deployment** - Azure PostgreSQL  

### Technical Skills Demonstrated
- Database design and normalization
- SQL query optimization
- Python data processing (pandas)
- Data visualization (Plotly)
- Web application development (Streamlit)
- Cloud deployment (Azure)
- Secret management
- Real-time data streaming
- Machine learning integration
- System monitoring

---

## 🚀 Future Enhancements

### Potential Additions (Not Required)
- [ ] User authentication (login/logout)
- [ ] Alert email notifications
- [ ] Downloadable reports (PDF/CSV)
- [ ] Historical data comparison
- [ ] Air quality forecasting (24h ahead)
- [ ] API endpoints for mobile app
- [ ] Multi-language support
- [ ] Dark mode toggle
- [ ] Custom alert thresholds
- [ ] Integration with weather APIs

---

**Your dashboard is presentation-perfect! 🎉**

For questions or issues, refer to:
- `PRESENTATION_SCRIPT.md` - 5-minute demo script
- `SLIDE_OUTLINE.md` - PowerPoint structure
- `ENHANCEMENTS_APPLIED.md` - Technical details
- `requirements.txt` - Dependencies
