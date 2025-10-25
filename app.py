# app.py
import os
import time
import uuid
import string
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import requests
from supabase import Client, create_client
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from supabase_client import supabase

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
        lockout_time = datetime.fromisoformat(user['lockout_until'].replace('Z', '+00:00'))
        
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



# --- Send Message ---
@app.route('/api/messages', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        data = request.json
        sender_id = session.get("user_id")
        receiver_id = data.get("recipient_id") # JS sends 'recipient_id'
        message_text = data.get("content")      # JS sends 'content'

        if not sender_id or not receiver_id or not message_text:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        insert_data = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "message": message_text,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "sent"
        }

        result = supabase.table("messages").insert(insert_data).execute()

        # Check for errors from the Supabase API call
        if hasattr(result, 'error') and result.error:
            return jsonify({"success": False, "error": result.error.message}), 500

        return jsonify({"success": True, "message_row": result.data[0]})
    except Exception as e:
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




# TEXT MODERATION END POINT

# --- New endpoint for real-time text moderation ---
# @app.route('/api/moderate-text', methods=['POST'])
# def moderate_text():
#     if 'user_id' not in session:
#         return jsonify({"success": False, "error": "Unauthorized"}), 401

#     # Check if user is locked out
#     if 'lockout_until' in session and time.time() < session['lockout_until']:
#         return jsonify({
#             "success": False,
#             "error": "You are temporarily locked out."
#         }), 429 # 429 Too Many Requests

#     text_to_check = request.json.get("text")
#     if not text_to_check:
#         return jsonify({"is_harmful": False}) # Nothing to check

#     # Prepare the request for the Perspective API
#     api_request_data = {
#         'comment': {'text': text_to_check},
#         'languages': ['en'],
#         'requestedAttributes': {'TOXICITY': {}}
#     }

#     try:
#         response = requests.post(PERSPECTIVE_API_URL, json=api_request_data)
#         response.raise_for_status() # Raise an exception for bad status codes
#         api_response = response.json()

#         # Get the toxicity score (it's a probability from 0.0 to 1.0)
#         toxicity_score = api_response['attributeScores']['TOXICITY']['summaryScore']['value']

#         # We define "harmful" as any text with a toxicity score > 0.7
#         # You can adjust this threshold.
#         is_harmful = toxicity_score > 0.7

#         return jsonify({"success": True, "is_harmful": is_harmful, "score": toxicity_score})

#     except requests.exceptions.RequestException as e:
#         print(f"Error calling Perspective API: {e}")
#         # Don't block the user if the moderation service fails
#         return jsonify({"success": False, "is_harmful": False})




# new add text moderation endpoint
# --- New endpoint for real-time text moderation ---
@app.route('/api/moderate-text', methods=['POST'])
def moderate_text():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    user_id = session['user_id']
    
    # =================================================================
    # --- BUG FIX (see section 2 below) ---
    # We should check the database for lockout, not the session
    try:
        user_resp = supabase.table("users").select("lockout_until").eq("id", user_id).execute()
        if not user_resp.data:
            return jsonify({"success": False, "error": "User not found"}), 404
        
        user = user_resp.data[0]
        if user.get('lockout_until'):
            lockout_time = datetime.fromisoformat(user['lockout_until'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) < lockout_time:
                remaining_seconds = (lockout_time - datetime.now(timezone.utc)).total_seconds()
                remaining_minutes = max(1, round(remaining_seconds / 60))
                return jsonify({
                    "success": False, 
                    "error": f"Account locked. Please try again in {remaining_minutes} minute(s).",
                    "is_harmful": True # Treat as harmful to prevent sending
                }), 429 # 429 Too Many Requests
    except Exception as e:
        print(f"Error checking user lockout: {e}")
        # Fail safe: allow message but log error
    # --- END OF BUG FIX ---
    # =================================================================

    text_to_check = request.json.get("text")
    if not text_to_check:
        return jsonify({"is_harmful": False}) # Nothing to check

    # Prepare the request for the Perspective API
    api_request_data = {
        'comment': {'text': text_to_check},
        # =================================================================
        # --- ACCURACY IMPROVEMENT ---
        # Provide all languages you want to monitor.
        # The API will auto-detect from this list.
        'languages': ['en', 'hi', 'hi-Latn'],
        # --- END OF IMPROVEMENT ---
        # =================================================================
        'requestedAttributes': {'TOXICITY': {}}
    }

    try:
        response = requests.post(PERSPECTIVE_API_URL, json=api_request_data)
        response.raise_for_status() # Raise an exception for bad status codes
        api_response = response.json()
        
        # Check if the API was able to score the text
        if 'attributeScores' not in api_response:
            # This can happen if language detection fails or text is empty
            print(f"Perspective API did not return scores: {api_response}")
            return jsonify({"success": True, "is_harmful": False, "score": 0.0})

        # Get the toxicity score (it's a probability from 0.0 to 1.0)
        toxicity_score = api_response['attributeScores']['TOXICITY']['summaryScore']['value']

        # We define "harmful" as any text with a toxicity score > 0.7
        # You can adjust this threshold.
        is_harmful = toxicity_score > 0.7

        return jsonify({"success": True, "is_harmful": is_harmful, "score": toxicity_score})

    except requests.exceptions.RequestException as e:
        print(f"Error calling Perspective API: {e}")
        # Don't block the user if the moderation service fails
        # Fail-open (allow the message) to not disrupt user experience
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





# ---------- Run ----------
if __name__ == "__main__":
    app.run(debug=True)
