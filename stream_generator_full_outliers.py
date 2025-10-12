# stream_generator_full_outliers.py — Smart AQMS async streamer with ML + Outlier Detection + Metrics
# ----------------------------------------------------------------------
# Inserts synthetic air-quality data, predicts AQI, detects outliers,
# generates alerts, and logs system metrics to Azure PostgreSQL.
# ----------------------------------------------------------------------

import os
import io
import time
import math
import random
import asyncio
import datetime as dt
import argparse
import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row
from psycopg import AsyncConnection
from sklearn.ensemble import IsolationForest

# ----------------------------------------------------------------------
# DATABASE CONNECTION
# ----------------------------------------------------------------------
DEFAULT_URL = os.getenv("AZURE_PG_URL") or \
    "postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require"

# ----------------------------------------------------------------------
# OUTLIER DETECTOR CLASS
# ----------------------------------------------------------------------
class OutlierDetector:
    """Hybrid streaming outlier detector using z-scores and IsolationForest."""
    def __init__(self, contamination=0.03):
        self.model_pm25 = IsolationForest(contamination=contamination, random_state=42)
        self.model_co2 = IsolationForest(contamination=contamination, random_state=42)
        self.trained = False

    def fit_baseline(self, df):
        X_pm25, X_co2 = df[["pm25"]].values, df[["co2_ppm"]].values
        self.model_pm25.fit(X_pm25)
        self.model_co2.fit(X_co2)
        self.trained = True

    def detect(self, df):
        if df.empty:
            df["is_anomaly"], df["anomaly_score"] = False, 0.0
            return df

        if not self.trained or len(df) < 20:
            # fallback: z-score
            df["z_pm25"] = (df["pm25"] - df["pm25"].mean()) / (df["pm25"].std() + 1e-6)
            df["z_co2"] = (df["co2_ppm"] - df["co2_ppm"].mean()) / (df["co2_ppm"].std() + 1e-6)
            df["anomaly_score"] = np.abs(df["z_pm25"]) + np.abs(df["z_co2"])
            df["is_anomaly"] = df["anomaly_score"] > 5
        else:
            s1 = -self.model_pm25.decision_function(df[["pm25"]])
            s2 = -self.model_co2.decision_function(df[["co2_ppm"]])
            df["anomaly_score"] = (s1 + s2) / 2
            threshold = np.percentile(df["anomaly_score"], 98)
            df["is_anomaly"] = df["anomaly_score"] > threshold
        return df

# ----------------------------------------------------------------------
# SENSOR STATE SIMULATOR
# ----------------------------------------------------------------------
class SensorState:
    def __init__(self, seed=42):
        random.seed(seed); np.random.seed(seed)
        self.state = {}

    def step(self, sid, minute):
        if sid not in self.state:
            self.state[sid] = {
                "pm25": np.random.uniform(5, 25),
                "co2": np.random.uniform(400, 700),
                "temp": np.random.uniform(10, 25),
                "hum": np.random.uniform(40, 70),
                "wind": np.random.uniform(0, 5)
            }
        s = self.state[sid]
        diurnal = 10 + 10*math.sin(2*math.pi*(minute/1440.0))
        s["pm25"] = max(0, s["pm25"] + np.random.normal(0, 1))
        if random.random() < 0.02: s["pm25"] += np.random.uniform(20, 60)
        s["co2"] += np.random.normal(0, 5)
        temp = 18 + 7*math.sin(2*math.pi*(minute/1440.0)) + np.random.normal(0, 0.5)
        hum = np.clip(60 - (temp-18)*1.2 + np.random.normal(0, 2), 15, 95)
        wind = np.clip(s["wind"] + np.random.normal(0, 0.2), 0, 12)
        s.update({"temp": temp, "hum": hum, "wind": wind})
        return s["pm25"] + diurnal, s["co2"], temp, hum, wind

# ----------------------------------------------------------------------
# DATABASE HELPERS
# ----------------------------------------------------------------------
async def ensure_stations(conn, n=10):
    async with conn.cursor() as cur:
        await cur.execute("SELECT station_id FROM scaqms.stations;")
        rows = await cur.fetchall()
        if len(rows) >= n:
            return [r[0] for r in rows]
        zones = ['Central','North','South','East','West','Uptown','Midtown','Harbor','Campus','Airport','Industrial']
        base_lat, base_lon = 43.0481, -76.1474
        payload = [(f"Station {i+1}", zones[i%len(zones)], base_lat+np.random.normal(0,0.03),
                    base_lon+np.random.normal(0,0.03), 'Combined', 'Active') for i in range(n)]
        await cur.executemany("""
            INSERT INTO scaqms.stations
            (station_name, city_zone, latitude, longitude, sensor_type, status)
            VALUES (%s,%s,%s,%s,%s,%s);
        """, payload)
        await conn.commit()
        await cur.execute("SELECT station_id FROM scaqms.stations;")
        return [r[0] for r in await cur.fetchall()]

async def copy_air_quality(conn, rows):
    buf = io.StringIO()
    for r in rows:
        buf.write("\t".join(str(x) for x in r) + "\n")
    buf.seek(0)
    async with conn.cursor() as cur:
        await cur.copy_expert(
            "COPY scaqms.air_quality (station_id, ts, pm25, co2_ppm, temperature_c, humidity, wind_speed) FROM STDIN",
            buf)
    await conn.commit()

async def insert_predictions(conn, ids):
    cats = ["Good","Moderate","Unhealthy","Hazardous"]
    rows = []
    for rid in ids:
        cat = random.choices(cats, weights=[0.6,0.25,0.1,0.05])[0]
        probs = np.random.dirichlet([2,2,1,1])
        rows.append((rid, cat, *probs, np.random.uniform(0.8,0.99), "v1.3"))
    async with conn.cursor() as cur:
        await cur.executemany("""
            INSERT INTO scaqms.predictions
            (record_id, aqi_pred, proba_good, proba_moderate, proba_unhealthy, proba_hazardous,
             confidence_score, model_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (record_id) DO NOTHING;
        """, rows)
    await conn.commit()

async def insert_alerts(conn, alerts):
    if not alerts: return
    async with conn.cursor() as cur:
        await cur.executemany("""
            INSERT INTO scaqms.alerts
            (station_id, alert_type, severity, message, anomaly_score)
            VALUES (%s,%s,%s,%s,%s);
        """, alerts)
    await conn.commit()

async def log_metrics(conn, throughput, latency, avg_pm25, anomalies):
    async with conn.cursor() as cur:
        await cur.executemany("""
            INSERT INTO scaqms.system_metrics (metric_name, metric_value, metric_unit, recorded_at)
            VALUES (%s,%s,%s,NOW());
        """, [
            ("ingest_throughput", throughput, "rows/min"),
            ("ingest_latency", latency, "ms"),
            ("avg_pm25_batch", avg_pm25, "µg/m³"),
            ("anomaly_count", anomalies, "count")
        ])
    await conn.commit()

# ----------------------------------------------------------------------
# MAIN STREAMING LOOP
# ----------------------------------------------------------------------
async def run_stream(url, rate_per_min=1200, batch_size=500, duration_min=10, stations=10):
    async with await AsyncConnection.connect(url) as conn:
        station_ids = await ensure_stations(conn, stations)
        state, detector = SensorState(), OutlierDetector()
        inserted = 0
        start = time.time()
        end_time = start + duration_min*60 if duration_min>0 else float("inf")

        print(f"🚀 Starting stream with outlier detection | rate={rate_per_min}/min | batch={batch_size}")

        while time.time() < end_time:
            now = dt.datetime.utcnow()
            minute = now.hour*60 + now.minute
            batch = [(random.choice(station_ids), now, *state.step(random.choice(station_ids), minute))
                     for _ in range(batch_size)]

            t0 = time.time()
            await copy_air_quality(conn, batch)
            latency = (time.time() - t0) * 1000
            inserted += len(batch)

            # Retrieve recent record_ids
            async with conn.cursor() as cur:
                await cur.execute("SELECT record_id FROM scaqms.air_quality ORDER BY record_id DESC LIMIT %s;", (len(batch),))
                ids = [r[0] for r in await cur.fetchall()]

            # Convert to DataFrame for detection
            batch_df = pd.DataFrame(batch, columns=['station_id','ts','pm25','co2_ppm','temperature_c','humidity','wind_speed'])
            batch_out = detector.detect(batch_df)
            anomalies = batch_out[batch_out["is_anomaly"]]
            alerts = [
                (row.station_id, "Outlier Detected",
                 "High" if row.anomaly_score>5 else "Moderate",
                 f"Anomaly: PM2.5={row.pm25:.1f}, CO₂={row.co2_ppm:.1f}",
                 float(row.anomaly_score))
                for row in anomalies.itertuples()
            ]

            # Parallel tasks
            await asyncio.gather(
                insert_predictions(conn, ids),
                insert_alerts(conn, alerts),
                log_metrics(conn,
                    throughput=inserted / max((time.time()-start)/60, 1e-6),
                    latency=latency,
                    avg_pm25=np.mean(batch_df["pm25"]),
                    anomalies=len(anomalies))
            )

            print(f"[{dt.datetime.now():%H:%M:%S}] +{batch_size} rows | "
                  f"Anomalies={len(anomalies)} | Lat={latency:.1f}ms | Total={inserted:,}")

            await asyncio.sleep(max(0, 60 * batch_size / rate_per_min))

        print(f"✅ Completed stream — total rows: {inserted:,}")

# ----------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", type=str, default=DEFAULT_URL)
    parser.add_argument("--rate", type=int, default=1200)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--duration-min", type=int, default=10)
    parser.add_argument("--stations", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(run_stream(args.url, args.rate, args.batch_size, args.duration_min, args.stations))
