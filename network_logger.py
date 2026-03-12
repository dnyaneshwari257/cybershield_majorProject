import logging
from logging.handlers import RotatingFileHandler
from flask import request
import os

# ===== LOG FILE PATH =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILENAME = os.path.join(BASE_DIR, 'server_traffic.log')

print("--------------------------------------------------")
print(f"[LOGGER] Saving log file to: {LOG_FILENAME}")
print("--------------------------------------------------")

# ===== LOGGER SETUP =====
logger = logging.getLogger('TrafficLogger')
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    LOG_FILENAME,
    maxBytes=100_000_000,
    backupCount=5
)

formatter = logging.Formatter('%(created)f,%(message)s')
handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(handler)


# ===== GET REAL CLIENT IP =====
def get_client_ip():

    if request.headers.get("CF-Connecting-IP"):
        ip = request.headers.get("CF-Connecting-IP")

    elif request.headers.get("True-Client-IP"):
        ip = request.headers.get("True-Client-IP")

    elif request.headers.get("X-Forwarded-For"):
        ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()

    else:
        ip = request.remote_addr

    if ip and ip.startswith("::ffff:"):
        ip = ip.replace("::ffff:", "")

    return ip


# ===== LOG REQUEST =====
def log_request_info(response):

    try:

        ip = get_client_ip()
        endpoint = request.path
        method = request.method
        status_code = response.status_code
        content_length = response.content_length or 0

        log_message = f"{ip},{endpoint},{method},{status_code},{content_length}"

        logger.info(log_message)

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")

    return response