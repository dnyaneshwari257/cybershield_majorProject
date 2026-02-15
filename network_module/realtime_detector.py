import time
import pandas as pd
import joblib
import os
import io
import requests # <-- NEEDED FOR WEBHOOK
from collections import deque
from datetime import datetime
from supabase import create_client, Client # <-- NEEDED FOR DASHBOARD
from dotenv import load_dotenv  # <-- ADD THIS IMPORT

# === CONFIGURATION ===
LOG_FILE = r"C:\Users\ashwini\source\repos\cybershield_majorProject\server_traffic.log"
MODEL_FILE = "network_model.pkl"

# WAF API Configuration
WAF_ENDPOINT = "http://127.0.0.1:5000/api/internal/block_ip"
INTERNAL_API_KEY = "CyberShield_WAF_Secret_998877" # Matches the key in app.py

# === SUPABASE SETUP (Load from .env in the parent folder) ===
# 1. Get the path to the main folder (one level up)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")

# 2. Load the .env file
load_dotenv(ENV_PATH)

# 3. Fetch the keys
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_last_n_lines(file_path, n=500):
    """Reads the last N lines of the active log file."""
    if not os.path.exists(file_path):
        return ""
    
    with open(file_path, 'r') as f:
        last_lines = deque(f, maxlen=n)
        return "".join(last_lines)

def monitor():
    if not os.path.exists(MODEL_FILE):
        print("Error: Model not found! Run train_model.py first.")
        return

    model = joblib.load(MODEL_FILE)
    print(f"[{datetime.now().time()}] CyberShield Network Monitor: ACTIVE")
    print(f"Monitoring Log File: {os.path.abspath(LOG_FILE)}")
    print(f"WAF API Endpoint: {WAF_ENDPOINT}")
    print("----------------------------------------------------")

    COLUMNS = ['timestamp', 'ip', 'endpoint', 'method', 'status_code', 'content_length']
    
    # Keep track to avoid spamming the DB and API every 2 seconds
    alerted_ips = set()

    while True:
        try:
            if not os.path.exists(LOG_FILE):
                print("Waiting for log file...")
                time.sleep(1)
                continue

            raw_data = get_last_n_lines(LOG_FILE, n=500)
            
            if not raw_data.strip():
                time.sleep(1)
                continue

            df = pd.read_csv(io.StringIO(raw_data), names=COLUMNS)
            current_time = time.time()
            recent_traffic = df[df['timestamp'] > (current_time - 10)]

            print(f"Active Lines (10s): {len(recent_traffic)}")

            if not recent_traffic.empty:
                features = recent_traffic.groupby('ip').agg({
                    'endpoint': 'count',           
                    'status_code': lambda x: (x >= 400).mean(), 
                    'content_length': 'sum'        
                })
                features.columns = ['request_rate', 'error_rate', 'byte_count']

                preds = model.predict(features)

                for ip, pred, req_rate in zip(features.index, preds, features['request_rate']):
                    # MINIMUM THREAT THRESHOLD: 
    # Only trust the AI's anomaly detection if traffic exceeds 50 req/sec
                    if pred == -1 and req_rate > 50:
                        print(f"\n[!!!] ALERT: DDoS Attack Detected from {ip}!")

                        # === 1. PUSH ALERT TO ADMIN DASHBOARD ===
                        if ip not in alerted_ips:
                            try:
                                supabase.table('network_alerts').insert({
                                    "ip_address": ip,
                                    "attack_type": "Volumetric DDoS",
                                    "intensity": f"{req_rate} req/sec"
                                }).execute()
                                print("      [Cloud] Alert pushed to Supabase.")
                                alerted_ips.add(ip)
                            except Exception as e:
                                print(f"      [Cloud Error] {e}")

                        # === 2. ACTIVE MITIGATION: TRIGGER WAF ===
                        try:
                            headers = {"X-API-KEY": INTERNAL_API_KEY}
                            payload = {"ip": ip}
                            
                            res = requests.post(WAF_ENDPOINT, json=payload, headers=headers, timeout=2)
                            
                            if res.status_code == 200:
                                print(f"      [Defense] API Webhook sent. WAF is now blocking {ip}.")
                            else:
                                print(f"      [Defense Warning] WAF responded with: {res.status_code}")
                        except Exception as e:
                            print(f"      [Defense Error] Could not reach WAF: {e}")
            
            time.sleep(2)

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    monitor()