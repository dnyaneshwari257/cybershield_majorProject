
# supabase_client.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

print("SUPABASE_URL:", SUPABASE_URL)
print("SUPABASE_KEY:", SUPABASE_KEY)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Supabase environment variables missing")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Test connection
def test_supabase_connection():
    try:
        resp = supabase.table("users").select("*").limit(1).execute()
        if resp.data is None:
            print("Supabase test query returned no data.")
            return False
        return True
    except Exception as e:
        print("Supabase connection failed:", e)
        return False

if not test_supabase_connection():
    print("Warning: Supabase client may not be properly connected.")
