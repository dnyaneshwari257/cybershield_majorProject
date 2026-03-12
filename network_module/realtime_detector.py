import time
import pandas as pd
import joblib
import os
import io
import requests
from collections import deque
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv


# ================= CONFIGURATION =================

LOG_FILE = r"C:\Users\Nilesh\Desktop\cybercopy_dnyaneshwari\cybershield_majorProject\server_traffic.log"
MODEL_FILE = "network_model.pkl"

# WAF API Configuration
WAF_ENDPOINT = "https://cybershield-majorproject.onrender.com/api/internal/block_ip"
INTERNAL_API_KEY = "CyberShield_WAF_Secret_998877"


# ================= SUPABASE SETUP =================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")

load_dotenv(ENV_PATH)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ================= HELPER FUNCTIONS =================

def get_last_n_lines(file_path, n=500):
    """Reads the last N lines of the active log file."""
    if not os.path.exists(file_path):
        return ""

    with open(file_path, 'r') as f:
        last_lines = deque(f, maxlen=n)
        return "".join(last_lines)


def get_ip_details(ip):
    
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}")
        data = res.json()
        location = f'{data.get("city","Unknown")}, {data.get("country","Unknown")}'
        ipv4 = data.get("query")   # API automatically returns IPv4 if available
        return ipv4, location

    except:
        return ip, "Unknown"

def calculate_severity(req_rate):
    """Determine attack severity based on request rate"""

    if req_rate > 200:
        return "CRITICAL"

    elif req_rate > 120:
        return "HIGH"

    elif req_rate > 60:
        return "MEDIUM"

    return "LOW"


# ================= MAIN MONITOR =================

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

            # last 10 seconds traffic
            recent_traffic = df[df['timestamp'] > (current_time - 10)]

            print(f"Active Lines (10s): {len(recent_traffic)}")

            if recent_traffic.empty:
                time.sleep(2)
                continue

            # ================= FEATURE EXTRACTION =================

            features = recent_traffic.groupby('ip').agg({

                'endpoint': ['count', pd.Series.nunique],
                'status_code': lambda x: (x >= 400).mean(),
                'content_length': 'sum'

            })

            features.columns = ['request_rate', 'unique_endpoints', 'error_rate', 'byte_count']

            preds = model.predict(features[['request_rate','error_rate','byte_count']])

            # ================= DETECTION LOOP =================

            for ip, pred, req_rate, uniq_ep, err_rate in zip(

                    features.index,
                    preds,
                    features['request_rate'],
                    features['unique_endpoints'],
                    features['error_rate']):

                attack_type = None

                # ================= DDOS =================
                if req_rate > 80:

                    attack_type = "DDoS"

                # ================= PORT SCAN =================
                elif err_rate > 0.7 and req_rate > 20:

                    attack_type = "Port Scan"

                # ================= ENDPOINT FLOOD =================
                elif uniq_ep > 15 and req_rate > 30:

                    attack_type = "Endpoint Flood"

                # ================= RECONNAISSANCE =================
                elif uniq_ep > 10 and err_rate > 0.5:

                    attack_type = "Reconnaissance"

                # ================= ML ANOMALY =================
                elif pred == -1 and req_rate > 50:

                    attack_type = "Network Anomaly"

                if not attack_type:
                    continue

                print(f"[ALERT] {attack_type} detected from {ip}")

                # ================= GET GEO LOCATION =================

                ipv4, location = get_ip_details(ip)

                severity = calculate_severity(req_rate)

                # ================= STORE ATTACK LOG =================

                try:

                    existing = supabase.table("attack_logs") \
                        .select("ip_address") \
                        .eq("ip_address", ipv4) \
                        .order("timestamp", desc=True) \
                        .limit(1) \
                        .execute()

                    if not existing.data:

                        supabase.table('attack_logs').insert({

                            "ip_address": ipv4,
                            "location": location,
                            "attack_type": attack_type,
                            "severity": severity,
                            "blocked": True,
                            "timestamp": datetime.utcnow().isoformat()

                        }).execute()

                        print("[DB] Attack stored")

                except Exception as e:

                    print("DB Error:", e)

                # ================= BLOCK IP =================

                try:

                    headers = {"X-API-KEY": INTERNAL_API_KEY}

                    payload = {"ip": ip}

                    res = requests.post(

                        WAF_ENDPOINT,
                        json=payload,
                        headers=headers,
                        timeout=2

                    )

                    if res.status_code == 200:

                        print(f"[WAF] IP blocked: {ip}")

                    else:

                        print(f"[WAF Warning] Status {res.status_code}")

                except Exception as e:

                    print("WAF Error:", e)

                # ================= CLOUD ALERT =================

                try:

                    if ip not in alerted_ips:

                        supabase.table('network_alerts').insert({

                            "ip_address": ip,
                            "attack_type": attack_type,
                            "intensity": f"{req_rate} req/sec"

                        }).execute()

                        alerted_ips.add(ip)

                        print("[Cloud] Alert pushed")

                except Exception as e:

                    print("Cloud Error:", e)

            time.sleep(2)

        except Exception as e:

            print("Monitor Error:", e)
            time.sleep(2)

# ================= ENTRY POINT =================

if __name__ == "__main__":
    monitor()