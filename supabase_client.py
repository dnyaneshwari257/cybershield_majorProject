
# supabase_client.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # service role key

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL or SUPABASE_KEY is not set in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
