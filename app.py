# app.py
import os
import re
import time
import uuid
import string
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
import requests
from supabase import Client, create_client
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from supabase_client import supabase
from dateutil import parser






# Load environment
load_dotenv()

# ---------- Flask setup ----------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # service key
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") # anon key
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)





#network logger middleware
from network_logger import log_request_info
app.after_request(log_request_info)

PERSPECTIVE_API_KEY = os.environ.get("PERSPECTIVE_API_KEY")
PERSPECTIVE_API_URL = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={PERSPECTIVE_API_KEY}"


# ---------- Flask-Mail setup ----------
app.config.update(
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "True").lower() == "true",
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",  # or "None" if cross-site
    SESSION_COOKIE_SECURE=False     # change to True if running HTTPS

)
mail = Mail(app)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", app.config.get("MAIL_USERNAME"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")



# CYBERSHIELD IN-MEMORY WAF (Web Application Firewall)
# =================================================================
# This acts as our ultra-fast RAM cache for blocked IPs
BANNED_IPS = set()
INTERNAL_API_KEY = "CyberShield_WAF_Secret_998877" # Security measure

@app.before_request
def active_firewall():
    whitelisted_routes = [
        '/admin_dashboard',
        '/api/admin_dashboard/network',
        '/api/admin_dashboard/bullying',
        '/api/internal/block_ip',
        '/static'
    ]
    
    for route in whitelisted_routes:
        if request.path.startswith(route):
            return

    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    if client_ip in BANNED_IPS:
        abort(403, description="Connection Dropped: IP blocked by CyberShield AI.")

@app.route('/api/internal/block_ip', methods=['POST'])
def internal_block_ip():
    """
    CONTROL PLANE API: The AI Detector calls this to update the RAM cache.
    """
    # 1. Verify this request is actually coming from our Detector script
    if request.headers.get("X-API-KEY") != INTERNAL_API_KEY:
        return {"error": "Unauthorized"}, 401
    
    # 2. Add the malicious IP to the RAM cache
    data = request.json
    ip_to_block = data.get("ip")
    
    if ip_to_block:
        BANNED_IPS.add(ip_to_block)
        print(f"\n[WAF] Mitigated Threat: {ip_to_block} added to RAM blocklist.\n")
        return {"success": True, "message": f"{ip_to_block} blocked."}
    
    return {"error": "No IP provided"}, 400


# ---------- Helpers ----------
def generate_random_password(length=10):
    chars = string.ascii_letters + string.digits + "!@#$%*"
    return ''.join(secrets.choice(chars) for _ in range(length))

def generate_username():
    """
    Generate next username in format EDU25XXX
    """
    try:
        # Try RPC first (if exists)
        rpc = supabase.rpc("next_edu25_val").execute()
        if getattr(rpc, "data", None) and isinstance(rpc.data, list):
            next_val = rpc.data[0].get("nextval")
            if next_val is not None:
                return f"EDU25{int(next_val):03d}"
    except Exception as e:
        print("RPC failed:", e)

    # Fallback: get last username and increment
    try:
        last_resp = supabase.table("users").select("username").order("created_at", desc=True).limit(1).execute()
        if getattr(last_resp, "data", None):
            last_username = last_resp.data[0].get("username", "")
            try:
                last_num = int(last_username.replace("EDU25", ""))
            except Exception:
                last_num = 0
        else:
            last_num = 0
        return f"EDU25{last_num + 1:03d}"
    except Exception as e:
        print("Username fallback error:", e)
        return "EDU25001"

def send_credentials_email(to_email, name, username, password):
    try:
        subject = "EduLearn - Your account credentials"
        body = (
            f"Hello {name},\n\n"
            "Your EduLearn account has been created.\n\n"
            f"Username: {username}\n"
            f"Password: {password}\n\n"
            f"Login here: {BASE_URL}/login\n\n"
            "Please change your password after your first login.\n\n"
            "Regards,\nEduLearn Team"
        )
        msg = Message(subject=subject, sender=SENDER_EMAIL, recipients=[to_email], body=body)
        mail.send(msg)
        return True
    except Exception as e:
        print("Email send failed:", e)
        return False

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.get_json() or request.form
        name = data.get("full_name")
        email = data.get("email")
        phone = data.get("phone")
        course = data.get("course")

        if not all([name, email, phone, course]):
            return jsonify({"success": False, "message": "All fields are required"}), 400

        # Check for existing user
        try:
            existing = supabase.table("users").select("*").eq("email", email).execute()
            if getattr(existing, "data", None) and existing.data:
                return jsonify({"success": False, "message": "Email already registered"}), 400
        except Exception as e:
            print("Exception checking existing user:", e)
            return jsonify({"success": False, "message": "Database error. Try again later."}), 500

        # Generate username
        username = generate_username()
        # Generate password and hash
        plain_password = generate_random_password(10)
        hashed_password = generate_password_hash(plain_password)

        # Insert new user
        try:
            insert_resp = supabase.table("users").insert({
                "id": str(uuid.uuid4()),
                "name": name,
                "email": email,
                "username": username,
                "password": hashed_password,
                "phone": phone,
                "course": course,
                "must_change_password": True,
                "created_at": datetime.utcnow().isoformat()
            }, returning='representation').execute()

            if not getattr(insert_resp, "data", None):
                return jsonify({"success": False, "message": "Registration failed. Try again later."}), 500

            # Send email (ignore failure)
            send_credentials_email(email, name, username, plain_password)

            return jsonify({"success": True, "message": "Registration successful! Check your email.", "username": username}), 201
        except Exception as e:
            print("Insert exception:", e)
            return jsonify({"success": False, "message": "Registration failed. Try again later."}), 500

    # GET request
    return render_template("register.html")




# new login/lockout functionality
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    # Handle POST
    data = request.get_json() or request.form
    username = data.get("moodle_id") # Assuming 'moodle_id' is the 'username'
    password = data.get("password")

    if not username or not password:
        return {"success": False, "message": "Username and password required"}, 400

    try:
        # This is your existing code to find the user
        resp = supabase.table("users").select("*").eq("username", username).execute()
    except Exception as e:
        print("Supabase select error:", e)
        return {"success": False, "message": "Database error"}, 500

    if not resp.data:
        return {"success": False, "message": "Invalid credentials"}, 400

    user = resp.data[0]
    
    # =================================================================
    # --- NEW LOCKOUT CHECK GOES HERE ---
    # =================================================================
    if user.get('lockout_until'):
        # Parse the timestamp from the database
        #lockout_time = datetime.fromisoformat(user['lockout_until'].replace('Z', '+00:00'))
        lockout_time = parser.isoparse(user['lockout_until'])
        # If the current time is before the lockout time, block the login
        if datetime.now(timezone.utc) < lockout_time:
            remaining_seconds = (lockout_time - datetime.now(timezone.utc)).total_seconds()
            remaining_minutes = max(1, round(remaining_seconds / 60)) # Show at least 1 minute
            
            return {
                "success": False, 
                "message": f"Account locked. Please try again in {remaining_minutes} minute(s)."
            }, 403 # 403 Forbidden is a good status code for this
    # --- END OF NEW LOCKOUT CHECK ---
    

    # Your existing password check and session logic continues here
    if not check_password_hash(user["password"], password):
        return {"success": False, "message": "Invalid credentials"}, 400

    # Store session
    session.permanent = True
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["name"] = user.get("name", "")

    # If user must change password → redirect them there
    if user.get("must_change_password", True):
        return {
            "success": True,
            "must_change_password": True,
            "message": "Please change your password",
            "redirect": "/change-password"
        }, 200

    # Otherwise → go to dashboard 
    return {
        "success": True,
        "message": "Login successful",
        "redirect": "/dashboard"
    }, 200




@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        flash("Please login first", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        current = request.form.get("current_password")
        new = request.form.get("new_password")

        if not current or not new:
            flash("Both fields are required", "danger")
            return redirect(url_for("change_password"))

        user_id = session["user_id"]

        try:
            resp = supabase.table("users").select("*").eq("id", user_id).execute()
        except Exception as e:
            print("Supabase select error:", e)
            flash("Database error. Try again later.", "danger")
            return redirect(url_for("change_password"))

        if not resp.data:
            flash("User not found", "danger")
            return redirect(url_for("login"))

        user = resp.data[0]

        if not check_password_hash(user["password"], current):
            flash("Current password is incorrect", "danger")
            return redirect(url_for("change_password"))

        try:
            update_resp = supabase.table("users").update({
                "password": generate_password_hash(new),
                "must_change_password": False
            }).eq("id", user_id).execute()
        except Exception as e:
            print("Supabase update error:", e)
            flash("Failed to update password. Try again later.", "danger")
            return redirect(url_for("change_password"))

        if not update_resp.data:
            flash("Failed to update password. Try again later.", "danger")
            return redirect(url_for("change_password"))

        flash("Password updated successfully", "success")
        return redirect(url_for("dashboard"))

    return render_template("change_password.html")




@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    try:
        resp = supabase.table("users").select("*").eq("id", session["user_id"]).execute()
        user = resp.data[0] if getattr(resp, "data", None) else {}
        must_change = user.get("must_change_password", True)
        return render_template("dashboard.html", user_name=user.get("name", session.get("name")), must_change=must_change)
    except Exception as e:
        print("Dashboard exception:", e)
        flash("Failed to load dashboard", "danger")
        return redirect(url_for("login"))





@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))

# ---------- API endpoint ----------
@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    name = data.get("full_name") or data.get("name")
    email = data.get("email")
    phone = data.get("phone", "")
    course = data.get("course", "")
    if not all([name, email]):
        return jsonify({"success": False, "message": "name and email required"}), 400

    # Check existing user
    try:
        existing = supabase.table("users").select("*").eq("email", email).execute()
        if getattr(existing, "data", None) and existing.data:
            return jsonify({"success": False, "message": "Email already registered"}), 400
    except Exception as e:
        print("API register exception:", e)
        return jsonify({"success": False, "message": "Database error"}), 500

    username = generate_username()
    plain_password = generate_random_password(10)
    hashed_password = generate_password_hash(plain_password)

    try:
        result = supabase.table("users").insert({
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "username": username,
            "password": hashed_password,
            "phone": phone,
            "course": course,
            "must_change_password": True,
            "created_at": datetime.utcnow().isoformat()
        }, returning='representation').execute()

        if not getattr(result, "data", None):
            return jsonify({"success": False, "message": "Registration failed"}), 500

        send_credentials_email(email, name, username, plain_password)

        return jsonify({"success": True, "username": username}), 201
    except Exception as e:
        print("API register insert exception:", e)
        return jsonify({"success": False, "message": "Registration failed"}), 500



# --- Chat Users ---
@app.route('/chat')
def chat_users():
    # A guard to ensure user is logged in
    if 'user_id' not in session:
        return "Please log in to chat.", 401
    try:
        users_resp = supabase.table("users").select("id, name").neq("id", session.get("user_id")).execute()
        return render_template(
            "chat_users.html",
            users=users_resp.data,
            supabase_url=SUPABASE_URL,
            supabase_anon=SUPABASE_ANON_KEY # Pass the public anon key to the frontend
        )
    except Exception as e:
        return f"Error loading users: {str(e)}", 500




# In app.py

# --- Get Messages Between Two Users ---
@app.route('/api/messages/<user1_id>/<user2_id>', methods=['GET'])
def get_messages(user1_id, user2_id):
    """
    Fetches messages by calling the 'get_conversation_messages'
    database function via RPC.
    """
    try:
        # Key Change: Call the RPC function instead of building a complex query.
        params = {"user_a_id": user1_id, "user_b_id": user2_id}
        resp = supabase.rpc("get_conversation_messages", params).execute()

        # The rest of the function remains the same.
        return jsonify({"success": True, "messages": resp.data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



# --- Send Message (SECURITY ENHANCED) ---
@app.route('/api/messages', methods=['POST'])
def send_message():
    # 1. Auth Check
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    try:
        data = request.json
        sender_id = session.get("user_id")
        username = session.get("username") # We need this for the dashboard log
        receiver_id = data.get("recipient_id") 
        message_text = data.get("content")

        if not sender_id or not receiver_id or not message_text:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        # ---------------------------------------------------------
        # SECURITY LAYER: CHECK LOCKOUT & TOXICITY
        # ---------------------------------------------------------
        
        # A. Check if user is currently banned
        user_res = supabase.table('users').select('lockout_until, offense_count').eq('id', sender_id).execute()
        user_data = user_res.data[0] if user_res.data else {}
        
        if user_data.get('lockout_until'):
            # Use dateutil parser to handle the timestamp format safely
            lockout_time = parser.isoparse(user_data['lockout_until'])
            # Ensure comparison is timezone-aware (UTC)
            if lockout_time > datetime.now(timezone.utc):
                 return jsonify({"success": False, "error": "⛔ You are temporarily banned from chatting due to toxic behavior."}), 403

        # B. Check for Toxicity
        # We use your existing 'check_for_blocked_words' function + a hardcoded list for the demo
        demo_bad_words = ["stupid", "idiot", "hate", "kill", "abuse", "useless", "trash"]
        is_toxic = any(word in message_text.lower() for word in demo_bad_words) or check_for_blocked_words(message_text)

        if is_toxic:
            print(f"[SECURITY] Blocking toxic message from {username}")

            # 1. Log to 'incidents' table (Populates Dashboard Log)
            supabase.table('incidents').insert({
                "user_id": sender_id,
                "username": username,
                "message": message_text,
                "category": "Toxic Language"
            }).execute()

            # 2. Update Offense Count (Populates User Violations Table)
            current_offenses = user_data.get('offense_count') or 0
            new_count = current_offenses + 1
            update_data = {"offense_count": new_count}

            # 3. Auto-Lockout Logic (3 Strikes Rule)
            if new_count >= 3:
                # Lockout for 30 minutes
                ban_until = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
                update_data["lockout_until"] = ban_until
                print(f"[SECURITY] User {username} LOCKED OUT until {ban_until}")

            # Commit updates to User
            supabase.table('users').update(update_data).eq('id', sender_id).execute()

            # 4. BLOCK THE MESSAGE (Do not save to 'messages' table)
            return jsonify({"success": False, "error": "⚠️ Message blocked: Toxic content detected. This incident has been logged."}), 400

        # ---------------------------------------------------------
        # IF SAFE: PROCEED NORMALLY
        # ---------------------------------------------------------

        insert_data = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "message": message_text,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "sent"
        }

        result = supabase.table("messages").insert(insert_data).execute()

        if hasattr(result, 'error') and result.error:
            return jsonify({"success": False, "error": result.error.message}), 500

        return jsonify({"success": True, "message_row": result.data[0]})

    except Exception as e:
        print(f"Chat Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# --- Mark Message as Delivered ---
@app.route('/api/messages/delivered', methods=['POST'])
def mark_delivered():
    try:
        message_id = request.json.get("message_id")
        if not message_id:
            return jsonify({"success": False, "error": "Message ID is required"}), 400

        result = supabase.table("messages") \
            .update({"status": "delivered"}) \
            .eq("id", message_id) \
            .execute()
        return jsonify({"success": True, "updated": len(result.data)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Mark Messages as Read ---
@app.route('/api/messages/read', methods=['POST'])
def mark_read():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        data = request.json
        sender_id = data.get("sender_id")
        receiver_id = session.get("user_id") # The current user is the receiver

        if not sender_id:
            return jsonify({"success": False, "error": "sender_id is required"}), 400

        # Update all messages from the sender to the current user that are not 'read'
        result = supabase.table("messages") \
            .update({"status": "read"}) \
            .eq("sender_id", sender_id) \
            .eq("receiver_id", receiver_id) \
            .neq("status", "read") \
            .execute()
        return jsonify({"success": True, "updated": len(result.data)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500




# block words code for files.txt
# --- Load blocked words from MULTIPLE files ---
BLOCKED_WORDS = set()

def load_list_from_file(filepath, word_set):
    """Helper function to load a single file into the main set."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            words = [line.strip().lower() for line in f if line.strip()]
            word_set.update(words) # Use update() to add all words from the list
            return len(words)
    except FileNotFoundError:
        print(f"--- INFO: Blocklist file not found, skipping: {filepath}")
        return 0
    except Exception as e:
        print(f"--- ERROR loading {filepath}: {e}")
        return 0

def load_blocked_words():
    """Loads words from all blocklist files into one master set."""
    global BLOCKED_WORDS
    BLOCKED_WORDS.clear() # Start with an empty set
    
    # 2. (NEW) Your Hinglish-specific list
    hinglish_count = load_list_from_file('custom_blocklist_hinglish.txt', BLOCKED_WORDS)
        
    # Updated print statement to show what was loaded
    print(f"--- Successfully loaded {len(BLOCKED_WORDS)} total unique blocked words.")
    print(f"    (Loaded:{hinglish_count} Hinglish)")


def check_for_blocked_words(text):
    """
    Checks if any part of the text contains a blocked word.
    This is a simple 'string in string' check, which is more
    effective for slang and variations than a 'whole word' check.
    """
    if not BLOCKED_WORDS:
        return False
        
    text_lower = text.lower()
    for word in BLOCKED_WORDS:
        if word in text_lower:
            return True # Found a match
            
    return False


load_blocked_words()


# === REPLACE YOUR EXISTING moderate_text FUNCTION WITH THIS ===

@app.route('/api/moderate-text', methods=['POST'])
def moderate_text():
    # 1. Auth Check
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    text_to_check = request.json.get("text")
    if not text_to_check or len(text_to_check) < 3:
        return jsonify({"success": True, "is_harmful": False})

    sender_id = session.get("user_id")
    username = session.get("username")

    # Helper function to Log Incident & Punish User
    def handle_toxic_detection(reason, source_layer):
        print(f"[SECURITY] Toxic content detected by {source_layer}: {reason}")
        
        # A. Log to 'incidents' table (Dashboard Live Log)
        try:
            supabase.table('incidents').insert({
                "user_id": sender_id,
                "username": username,
                "message": text_to_check, 
                "category": f"Blocked by {source_layer}"
            }).execute()
        except Exception as e:
            print(f"Error logging incident: {e}")

        # B. Increment Offense Count (Dashboard Violations Table)
        try:
            # Fetch current count
            user_res = supabase.table('users').select('offense_count').eq('id', sender_id).execute()
            current_count = user_res.data[0].get('offense_count', 0) if user_res.data else 0
            new_count = current_count + 1
            
            update_data = {"offense_count": new_count}

            # C. Auto-Lockout (3 Strikes)
            if new_count >= 3:
                # Lockout for 5 minutes
                ban_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
                update_data["lockout_until"] = ban_until
                print(f"[SECURITY] User {username} LOCKED OUT until {ban_until}")

            supabase.table('users').update(update_data).eq('id', sender_id).execute()
        except Exception as e:
            print(f"Error updating user stats: {e}")

        # Return the 'True' flag so Frontend disables the button
        return jsonify({
            "success": True, 
            "is_harmful": True, 
            "reason": reason
        })

    # === LAYER 1: Custom Keyword List ===
    # This catches "stupid", "idiot" from your local file
    if check_for_blocked_words(text_to_check):
        return handle_toxic_detection("Prohibited Language", "Keyword Filter")

    # === LAYER 2: Perspective API (AI) ===
    # This catches "You are useless" (Contextual toxicity)
    api_request_data = {
        'comment': {'text': text_to_check},
        'languages': ['en'],
        'requestedAttributes': {
            'TOXICITY': {}, 'SEVERE_TOXICITY': {}, 'THREAT': {}, 
            'IDENTITY_ATTACK': {}, 'INSULT': {}, 'SEXUALLY_EXPLICIT': {}
        }
    }

    try:
        response = requests.post(PERSPECTIVE_API_URL, json=api_request_data, timeout=5)
        response.raise_for_status()
        
        if 'attributeScores' not in response.json():
            return jsonify({"success": True, "is_harmful": False})

        scores = response.json()['attributeScores']
        
        # Check thresholds
        if scores['THREAT']['summaryScore']['value'] > 0.4:
            return handle_toxic_detection("Threat Detected", "AI Model")
            
        if scores['SEVERE_TOXICITY']['summaryScore']['value'] > 0.5:
             return handle_toxic_detection("Severe Toxicity", "AI Model")
             
        if scores['IDENTITY_ATTACK']['summaryScore']['value'] > 0.4:
             return handle_toxic_detection("Hate Speech", "AI Model")

        if scores['INSULT']['summaryScore']['value'] > 0.5:
             return handle_toxic_detection("Personal Insult", "AI Model")
             
        if scores['TOXICITY']['summaryScore']['value'] > 0.65:
             return handle_toxic_detection("Toxic Language", "AI Model")

        # If clean
        return jsonify({"success": True, "is_harmful": False})

    except Exception as e:
        print(f"Error calling Perspective API: {e}")
        return jsonify({"success": True, "is_harmful": False})

# moderation lockout function
# In app.py
# In app.py

@app.route('/api/set-lockout', methods=['GET'])
def set_lockout():
    if 'user_id' in session:
        user_id = session.get('user_id')
        # Lockout for 5 minutes (300 seconds) from the current time
        lockout_end_time = datetime.utcnow() + timedelta(seconds=300)
        
        # Update the user's record in the database
        supabase.table("users").update({
            "lockout_until": lockout_end_time.isoformat()
        }).eq("id", user_id).execute()

    return jsonify({"success": True})


########ADMIN MODULE

# === ROUTE: DASHBOARD PAGE ===
@app.route('/admin_dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')


# ADMIN DASHBOARD APIs (for charts and tables)
# === API 1: CYBERBULLYING DATA ===
@app.route('/api/admin_dashboard/bullying')
def api_bullying():
    try:
        # 1. Get Repeat Offenders (From your existing 'users' table)
        # We filter for users who have offense_count > 0
        offenders = supabase.table('users')\
            .select('username, offense_count, lockout_until')\
            .gt('offense_count', 0)\
            .order('offense_count', desc=True)\
            .limit(5)\
            .execute()
        
        # 2. Get Recent Incidents (From the new 'incidents' table)
        incidents = supabase.table('incidents')\
            .select('*')\
            .order('timestamp', desc=True)\
            .limit(10)\
            .execute()
        
        return jsonify({
            "offenders": offenders.data,
            "incidents": incidents.data
        })
    except Exception as e:
        print(f"Supabase Error: {e}")
        return jsonify({"offenders": [], "incidents": []})

# === API 2: NETWORK DATA (Real-time Graph & Alerts) ===
@app.route('/api/admin_dashboard/network')
def api_network():
    # Set default "None" so the frontend doesn't crash if empty
    data = {"rps": 0, "status": "Normal", "recent_logs": [], "latest_alert": "None"}
    
    # Force Absolute Path to ensure we find the log file
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOG_FILE = os.path.join(BASE_DIR, 'server_traffic.log')

    # --- A. Get Live Traffic Speed (For the Graph) ---
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()[-5000:] # Read a large chunk
                current_time = time.time()
                recent_count = 0
                
                for line in lines:
                    try:
                        parts = line.split(',')
                        # Check if request happened in the last 1 second
                        if float(parts[0]) > (current_time - 1):
                            recent_count += 1
                    except:
                        continue

                data["rps"] = recent_count
                
                if data["rps"] > 50: 
                    data["status"] = "Critical"
    except Exception as e:
        print(f"Dashboard Graph Error: {e}")

    # --- B. Get Cloud Alerts (For the "Last Alert" Text) ---
    try:
        # Fetch the most recent alert from your Supabase table
        alerts = supabase.table('network_alerts')\
            .select('*')\
            .order('timestamp', desc=True)\
            .limit(1)\
            .execute()
        
        # If we got data, format it for the dashboard
        if getattr(alerts, 'data', None) and len(alerts.data) > 0:
            last_alert = alerts.data[0]
            data["latest_alert"] = f"{last_alert['attack_type']} from {last_alert['ip_address']}"
            
    except Exception as e:
        print(f"Supabase Fetch Error: {e}")

    return jsonify(data)


#########Mobile Attack Route (For fun testing of the WAF - Not linked anywhere, so it's a "secret" route)

@app.route('/mobile_attack')
def mobile_attack():
    """Precision Mobile Attack: Spikes the Error Rate to trigger the AI."""
    return """
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="text-align:center; padding:50px; font-family:sans-serif; background-color:#1e1e2f; color:white;">
        <h2>📱 CyberShield Precision Attack</h2>
        <p>Target: <b>Your PC</b></p>
        <button onclick="startAttack()" style="padding:20px 40px; background:red; color:white; font-size:24px; border:none; border-radius:10px; font-weight:bold; cursor:pointer;">🔥 LAUNCH ATTACK</button>
        <h3 id="status" style="margin-top:30px;">Ready</h3>
        <script>
            let count = 0;
            let isBlocked = false;

            function fire() {
                if (isBlocked) return;
                
                // Hit a fake endpoint to generate 404 errors. 
                // A 100% error rate will trip the AI's anomaly detection.
                fetch('/this_page_does_not_exist_' + Math.random())
                .then(res => {
                    // ONLY show blocked if the WAF actually returns 403 Forbidden
                    if (res.status === 403) {
                        isBlocked = true;
                        document.getElementById('status').innerHTML = "❌ <span style='color:red;'>TRUE WAF BLOCK (403)</span> ❌";
                    }
                })
                .catch(e => { /* Ignore normal server lag */ });
                
                count++;
            }

            function startAttack() {
                document.getElementById('status').innerText = "Attacking...";
                // Fire requests at a steady, manageable pace so Flask can log them
                setInterval(() => {
                    if (!isBlocked) {
                        for(let i=0; i<10; i++) fire();
                        document.getElementById('status').innerText = "Requests Fired: " + count;
                    }
                }, 100); 
            }
        </script>
    </body>
    </html>
    """
# ---------- Run ----------
if __name__ == '__main__':
    # host='0.0.0.0' opens the server to your local Wi-Fi
    app.run(host='0.0.0.0', port=5000, debug=True)