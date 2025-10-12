
# smart_aqms_stream_final.py
# -----------------------------------------------------------------------------
# Unified streaming pipeline for Smart AQMS (Azure PostgreSQL)
# - Async COPY ingestion (high throughput)
# - Online ML (SGDClassifier partial_fit) to predict AQI class
# - Statistical/IForest outlier detection and rule-based alerts
# - Predictions + metrics + alerts persisted for the Streamlit dashboard
# -----------------------------------------------------------------------------
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
from psycopg import AsyncConnection
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

DEFAULT_URL = os.getenv('AZURE_PG_URL') or         'postgresql://postgres:Azure123@bigdata-508-server.postgres.database.azure.com:5432/postgres?sslmode=require'

def aqi_label_from_pm25(x: float) -> str:
    if x <= 12: return "Good"
    elif x <= 35: return "Moderate"
    elif x <= 55: return "Unhealthy"
    else: return "Hazardous"

async def ensure_stations(conn, target_n=12):
    async with conn.cursor() as cur:
        await cur.execute("SELECT station_id FROM scaqms.stations ORDER BY station_id;")
        rows = await cur.fetchall()
        if len(rows) >= target_n:
            return [r[0] for r in rows]
        zones = ['Central','North','South','East','West','Uptown','Midtown','Harbor','Campus','Airport','Industrial','Market']
        base_lat, base_lon = 43.0481, -76.1474
        payload = []
        for i in range(target_n - len(rows)):
            payload.append((
                f"Station {len(rows)+i+1}",
                zones[(len(rows)+i) % len(zones)],
                base_lat + np.random.normal(0, 0.03),
                base_lon + np.random.normal(0, 0.03),
                'Combined', 'Active'
            ))
        await cur.executemany(
            """INSERT INTO scaqms.stations (station_name, city_zone, latitude, longitude, sensor_type, status)
               VALUES (%s,%s,%s,%s,%s,%s);""",
            payload
        )
        await conn.commit()
        await cur.execute("SELECT station_id FROM scaqms.stations ORDER BY station_id;")
        return [r[0] for r in await cur.fetchall()]

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
        if random.random() < 0.02:
            s["pm25"] += np.random.uniform(20, 60)
        s["co2"] += np.random.normal(0, 5)
        temp = 18 + 7*math.sin(2*math.pi*(minute/1440.0)) + np.random.normal(0, 0.5)
        hum = np.clip(60 - (temp-18)*1.2 + np.random.normal(0, 2), 15, 95)
        wind = np.clip(s["wind"] + np.random.normal(0, 0.2), 0, 12)
        s.update({"temp": temp, "hum": hum, "wind": wind})
        return s["pm25"] + diurnal, s["co2"], temp, hum, wind

class OutlierDetector:
    def __init__(self, contamination=0.03):
        self.model_pm25 = IsolationForest(contamination=contamination, random_state=42)
        self.model_co2  = IsolationForest(contamination=contamination, random_state=42)
        self.trained = False
    def fit_baseline(self, df: pd.DataFrame):
        if df.empty: return
        self.model_pm25.fit(df[["pm25"]].values)
        self.model_co2.fit(df[["co2_ppm"]].values)
        self.trained = True
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            df["is_anomaly"], df["anomaly_score"] = False, 0.0
            return df
        if not self.trained or len(df) < 20:
            df["z_pm25"] = (df["pm25"] - df["pm25"].mean()) / (df["pm25"].std() + 1e-6)
            df["z_co2"]  = (df["co2_ppm"] - df["co2_ppm"].mean()) / (df["co2_ppm"].std() + 1e-6)
            df["anomaly_score"] = np.abs(df["z_pm25"]) + np.abs(df["z_co2"])
            df["is_anomaly"] = df["anomaly_score"] > 5
        else:
            s1 = -self.model_pm25.decision_function(df[["pm25"]])
            s2 = -self.model_co2.decision_function(df[["co2_ppm"]])
            df["anomaly_score"] = (s1 + s2) / 2
            thr = np.percentile(df["anomaly_score"], 98)
            df["is_anomaly"] = df["anomaly_score"] > thr
        return df

class OnlineAQIModel:
    def __init__(self):
        self.pipe = make_pipeline(
            StandardScaler(),
            SGDClassifier(loss="log_loss", max_iter=10, learning_rate="optimal", random_state=42)
        )
        self.is_fitted = False
    def fit_partial(self, df: pd.DataFrame) -> float:
        df = df.copy()
        df["aqi_label"] = df["pm25"].apply(aqi_label_from_pm25)
        X = df[["pm25","co2_ppm","temperature_c","humidity","wind_speed"]].values
        y = df["aqi_label"].values
        if not self.is_fitted:
            self.pipe.fit(X, y)
            self.is_fitted = True
        else:
            self.pipe.partial_fit(X, y)
        preds = self.pipe.predict(X)
        return float(np.mean(preds == y))
    def predict_proba(self, df: pd.DataFrame):
        if not self.is_fitted:
            return np.tile(np.array([0.25,0.25,0.25,0.25]), (len(df),1)), np.array(["Good","Moderate","Unhealthy","Hazardous"])
        X = df[["pm25","co2_ppm","temperature_c","humidity","wind_speed"]].values
        proba = self.pipe.predict_proba(X)
        classes = self.pipe.named_steps['sgdclassifier'].classes_
        return proba, classes

async def copy_air_quality(conn, rows):
    buf = io.StringIO()
    for r in rows:
        buf.write("\t".join(str(x) for x in r) + "\n")
    buf.seek(0)
    async with conn.cursor() as cur:
        await cur.copy_expert(
            "COPY scaqms.air_quality (station_id, ts, pm25, co2_ppm, temperature_c, humidity, wind_speed) FROM STDIN",
            buf
        )
    await conn.commit()

async def insert_predictions(conn, record_ids, proba, classes):
    label_index = {c:i for i,c in enumerate(classes)}
    def p(lbl, row): return float(row[label_index.get(lbl, 0)])
    rows = []
    for rid, row in zip(record_ids, proba):
        pred_idx = int(np.argmax(row))
        pred_lbl = classes[pred_idx] if isinstance(classes, np.ndarray) else classes[pred_idx]
        rows.append((
            rid, pred_lbl,
            p("Good", row), p("Moderate", row), p("Unhealthy", row), p("Hazardous", row),
            float(np.max(row)), "online-sgd-v1"
        ))
    async with conn.cursor() as cur:
        await cur.executemany(
            """
            INSERT INTO scaqms.predictions
            (record_id, aqi_pred, proba_good, proba_moderate, proba_unhealthy, proba_hazardous, confidence_score, model_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (record_id) DO NOTHING;
            """,
            rows
        )
    await conn.commit()

async def insert_alerts(conn, alerts):
    if not alerts: return
    async with conn.cursor() as cur:
        await cur.executemany(
            """
            INSERT INTO scaqms.alerts (station_id, alert_type, severity, message, anomaly_score)
            VALUES (%s,%s,%s,%s,%s);
            """, alerts
        )
    await conn.commit()

async def log_metrics(conn, metrics):
    if not metrics: return
    async with conn.cursor() as cur:
        await cur.executemany(
            """
            INSERT INTO scaqms.system_metrics (metric_name, metric_value, metric_unit, recorded_at)
            VALUES (%s,%s,%s,NOW());
            """, metrics
        )
    await conn.commit()

async def run_stream(url: str, rate_per_min: int, batch_size: int, duration_min: int, stations: int):
    async with await AsyncConnection.connect(url) as conn:
        station_ids = await ensure_stations(conn, stations)
        state = SensorState()
        detector = OutlierDetector(contamination=0.03)
        model = OnlineAQIModel()

        inserted = 0
        start = time.time()
        end_time = start + duration_min*60 if duration_min > 0 else float('inf')

        print(f"\n🚀 Smart AQMS stream started | rate={rate_per_min}/min | batch={batch_size} | stations={stations}\n")

        while time.time() < end_time:
            now = dt.datetime.utcnow()
            minute = now.hour*60 + now.minute
            batch = [(random.choice(station_ids), now, *state.step(random.choice(station_ids), minute))
                     for _ in range(batch_size)]

            t0 = time.time()
            await copy_air_quality(conn, batch)
            latency_ms = (time.time() - t0) * 1000.0
            inserted += len(batch)

            async with conn.cursor() as cur:
                await cur.execute("SELECT record_id FROM scaqms.air_quality ORDER BY record_id DESC LIMIT %s;", (len(batch),))
                record_ids = [r[0] for r in await cur.fetchall()]

            batch_df = pd.DataFrame(batch, columns=['station_id','ts','pm25','co2_ppm','temperature_c','humidity','wind_speed'])

            batch_out = detector.detect(batch_df.copy())
            anomalies = batch_out[batch_out["is_anomaly"]]
            alerts = [
                (row.station_id, "Outlier Detected",
                 "High" if row.anomaly_score > 5 else "Moderate",
                 f"Anomaly: PM2.5={row.pm25:.1f}, CO₂={row.co2_ppm:.0f} ppm",
                 float(row.anomaly_score))
                for row in anomalies.itertuples()
            ]
            for row in batch_df.itertuples():
                if row.pm25 > 100:
                    alerts.append((row.station_id, "High PM2.5", "Critical", f"PM2.5 {row.pm25:.1f} µg/m³", row.pm25/100))
                elif row.pm25 > 55:
                    alerts.append((row.station_id, "PM2.5 Alert", "High", f"PM2.5 {row.pm25:.1f} µg/m³", row.pm25/100))
                if row.co2_ppm > 800:
                    alerts.append((row.station_id, "CO₂ Alert", "Moderate", f"CO₂ {row.co2_ppm:.0f} ppm", row.co2_ppm/1000))

            acc = model.fit_partial(batch_df.copy())
            proba, classes = model.predict_proba(batch_df.copy())

            await asyncio.gather(
                insert_predictions(conn, record_ids, proba, classes),
                insert_alerts(conn, alerts),
                log_metrics(conn, [
                    ("ingest_throughput", inserted / max((time.time()-start)/60, 1e-6), "rows/min"),
                    ("ingest_latency", latency_ms, "ms"),
                    ("avg_pm25_batch", float(np.mean(batch_df["pm25"])), "µg/m³"),
                    ("anomaly_count", int(len(anomalies)), "count"),
                    ("stream_model_accuracy", float(acc), "score")
                ])
            )

            print(f"[{dt.datetime.now():%H:%M:%S}] +{batch_size} rows | acc={acc:.3f} | anomalies={len(anomalies)} | lat={latency_ms:.1f} ms | total={inserted:,}")

            await asyncio.sleep(max(0, 60 * batch_size / rate_per_min))

        print(f"\n✅ Completed stream. Total rows inserted: {inserted:,}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart AQMS unified streaming pipeline")
    parser.add_argument("--url", type=str, default=DEFAULT_URL)
    parser.add_argument("--rate", type=int, default=1800, help="Target rows per minute")
    parser.add_argument("--batch-size", type=int, default=600, help="Rows per micro-batch")
    parser.add_argument("--duration-min", type=int, default=10, help="Duration to run (0 = forever)")
    parser.add_argument("--stations", type=int, default=12, help="Number of stations to simulate")
    args = parser.parse_args()
    asyncio.run(run_stream(args.url, args.rate, args.batch_size, args.duration_min, args.stations))
