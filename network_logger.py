import logging
from logging.handlers import RotatingFileHandler
from flask import request
import os  

# === 1. FORCE ABSOLUTE PATH ===
# Get the folder where THIS script (network_logger.py) is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Save the log file in that same folder
LOG_FILENAME = os.path.join(BASE_DIR, 'server_traffic.log')

print(f"--------------------------------------------------")
print(f"[LOGGER] Saving log file to: {LOG_FILENAME}")
print(f"--------------------------------------------------")

# === 2. Configure Logger ===
logger = logging.getLogger('TrafficLogger')
logger.setLevel(logging.INFO)

# Create a handler that rotates files
# FIX: Increased maxBytes to 100MB (100,000,000) to prevent WinError 32 file locking crashes
handler = RotatingFileHandler(LOG_FILENAME, maxBytes=100_000_000, backupCount=5)

# Define format: Timestamp,Message
formatter = logging.Formatter('%(created)f,%(message)s')
handler.setFormatter(formatter)

# Prevent adding multiple handlers if script is reloaded
if not logger.handlers:
    logger.addHandler(handler)

def log_request_info(response):
    """
    Logs request details using a thread-safe rotating file handler.
    """
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        endpoint = request.path
        method = request.method
        status_code = response.status_code
        content_length = response.content_length if response.content_length else 0
        
        log_message = f"{ip},{endpoint},{method},{status_code},{content_length}"
        
        logger.info(log_message)
            
    except Exception as e:
        print(f"Logging Error: {e}")
    
    return response