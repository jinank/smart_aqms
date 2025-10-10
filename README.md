# Azure PostgreSQL Streaming Analytics Pipeline
## Smart City Air Quality Monitoring System (AQMS)

### 🎯 Project Overview

This project implements a comprehensive streaming analytics pipeline on Azure PostgreSQL for real-time air quality monitoring in smart cities. The system demonstrates end-to-end data processing from raw sensor ingestion to actionable insights through machine learning and anomaly detection.

### 🏗️ System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Sources  │───▶│  Azure PostgreSQL │───▶│   Analytics     │
│  (IoT Sensors)  │    │   (Streaming DB)  │    │   Dashboard     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  ML Pipeline    │
                       │  & Anomaly      │
                       │  Detection      │
                       └─────────────────┘
```

### 📊 Database Schema

The system uses a multi-table relational schema with the following components:

#### Core Tables:
1. **`stations`** - Monitoring station locations and metadata
2. **`air_quality`** - Main streaming table with time-series sensor data (partitioned by month)
3. **`alerts`** - Anomaly detection results and alerts
4. **`predictions`** - ML model outputs for AQI classification
5. **`system_metrics`** - Performance monitoring and system health metrics

#### Key Features:
- **Time-partitioned tables** for optimal query performance
- **Generated columns** for automatic AQI bucket classification
- **Comprehensive indexing** for fast real-time queries
- **Referential integrity** with foreign key constraints

### 🚀 Quick Start

#### Prerequisites
- Python 3.8+
- Azure PostgreSQL database access
- Required Python packages (see requirements.txt)

#### Installation
```bash
# Clone or download the project files
# Install dependencies
pip install -r requirements.txt

# Run the complete demo
python run_demo.py
```

#### Manual Setup
```bash
# 1. Deploy schema and seed data
python azure_deploy.py

# 2. Start data streaming (in separate terminal)
python azure_stream.py --continuous --rate 300

# 3. Start monitoring system (in separate terminal)
python azure_monitor.py --interval 30

# 4. Launch dashboard
streamlit run app.py
```

### 📈 System Components

#### 1. Data Generation Pipeline (`azure_stream.py`)
- **High-volume streaming**: 200-500 records per minute
- **Realistic patterns**: Diurnal, seasonal, and rush-hour variations
- **Zone-specific pollution**: Different pollution levels by area type
- **Sensor reliability simulation**: Quality scores and occasional failures
- **Batch processing**: Optimized for high-throughput insertion

#### 2. Outlier Detection System (`azure_monitor.py`)
- **Isolation Forest**: Unsupervised anomaly detection
- **Statistical methods**: Z-score based outlier identification
- **Multi-feature analysis**: CO2, PM2.5, PM10, NO2, O3, weather data
- **Severity classification**: Critical, High, Moderate, Low alerts
- **Real-time processing**: Continuous monitoring with configurable intervals

#### 3. Machine Learning Pipeline
- **Online learning**: SGD classifier with incremental updates
- **Multi-class classification**: AQI prediction (Good, Moderate, Unhealthy, Hazardous)
- **Feature engineering**: Derived features and data preprocessing
- **Model persistence**: Automatic model saving and loading
- **Confidence scoring**: Prediction reliability metrics

#### 4. Real-time Dashboard (`app.py`)
- **Live updates**: 10-second refresh intervals
- **Comprehensive KPIs**: Air quality metrics with visual indicators
- **Interactive visualizations**: Time-series plots, geospatial maps
- **Alert management**: Color-coded severity levels and detailed messages
- **System monitoring**: Performance metrics and health indicators

### 🔧 Configuration

#### Azure PostgreSQL Connection
The system connects to Azure PostgreSQL using the provided connection string:
```
postgresql://postgres:Azure123!@#@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require
```

#### Performance Tuning
- **Batch sizes**: Adjustable for optimal throughput
- **Monitoring intervals**: Configurable outlier detection and ML update frequencies
- **Data retention**: Automatic cleanup of old metrics and alerts
- **Connection pooling**: Optimized database connections

### 📊 Key Metrics and KPIs

#### Air Quality Indicators:
- **PM2.5**: Fine particulate matter (μg/m³)
- **PM10**: Coarse particulate matter (μg/m³)
- **CO2**: Carbon dioxide concentration (ppm)
- **NO2**: Nitrogen dioxide (ppm)
- **O3**: Ozone levels (ppm)

#### System Performance:
- **Data throughput**: Records per minute processed
- **Detection accuracy**: Anomaly detection performance
- **ML model accuracy**: AQI prediction reliability
- **System latency**: End-to-end processing times

### 🎯 Project Deliverables

✅ **Relational Schema**: Multi-table database with 5+ interrelated tables
✅ **Data Generation**: High-volume streaming pipeline (300+ records/minute)
✅ **Real-time Dashboard**: Live monitoring with 10-second updates
✅ **Outlier Detection**: Multi-method anomaly detection system
✅ **Machine Learning**: Online learning AQI prediction model
✅ **Deployment Scripts**: Automated setup and monitoring tools

### 🔍 Technical Highlights

#### Streaming Analytics:
- **Time-partitioned tables** for efficient querying
- **Batch processing** for high-throughput data ingestion
- **Real-time monitoring** with configurable intervals
- **Automatic scaling** through connection pooling

#### Machine Learning:
- **Online learning** for continuous model updates
- **Feature engineering** with derived metrics
- **Multi-class classification** for AQI prediction
- **Model persistence** and versioning

#### Data Quality:
- **Sensor reliability simulation** with quality scores
- **Missing data handling** with intelligent imputation
- **Outlier detection** with multiple algorithms
- **Data validation** with constraint checking

### 🚀 Performance Characteristics

- **Data Volume**: 300+ records per minute sustained
- **Latency**: Sub-second processing for real-time updates
- **Scalability**: Partitioned tables support millions of records
- **Reliability**: Automatic error handling and reconnection
- **Monitoring**: Comprehensive system health metrics

### 📝 Usage Examples

#### Start High-Volume Streaming:
```bash
python azure_stream.py --continuous --rate 500 --batch-size 100
```

#### Monitor with Custom Intervals:
```bash
python azure_monitor.py --interval 60 --outlier-window 120 --ml-window 240
```

#### Deploy Fresh System:
```bash
python azure_deploy.py
```

### 🎥 Demonstration

The system demonstrates:
1. **Real-time data ingestion** from simulated IoT sensors
2. **Continuous anomaly detection** with multiple algorithms
3. **Online machine learning** with incremental model updates
4. **Live dashboard updates** with comprehensive visualizations
5. **End-to-end streaming analytics** from raw data to insights

### 📚 Technical Stack

- **Database**: Azure PostgreSQL with advanced partitioning
- **Backend**: Python with SQLAlchemy and psycopg2
- **Frontend**: Streamlit with Plotly visualizations
- **ML**: Scikit-learn with online learning algorithms
- **Monitoring**: Custom metrics and alerting system

### 🔧 Troubleshooting

#### Common Issues:
1. **Connection errors**: Check Azure PostgreSQL credentials and network access
2. **Performance issues**: Adjust batch sizes and monitoring intervals
3. **Memory usage**: Monitor system metrics and adjust data retention policies
4. **ML model issues**: Check training data quality and feature engineering

#### Performance Optimization:
- Use appropriate batch sizes for your Azure PostgreSQL tier
- Monitor connection pool usage and adjust accordingly
- Implement data archiving for long-term storage
- Consider read replicas for dashboard queries

### 📞 Support

For technical issues or questions about the streaming analytics pipeline, please refer to the code documentation and inline comments for detailed implementation guidance.

---

**Built with ❤️ for Azure PostgreSQL Streaming Analytics**
