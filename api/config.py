# ════════════════════════════════════════════════════════════════════════
#  config.py — FastAPI app configuration
# ════════════════════════════════════════════════════════════════════════

import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# Districts
DISTRICTS = ["nalbari", "baksa", "dhemaji", "lakhimpur"]

DISTRICT_LABELS = {
    "nalbari":   "Nalbari",
    "baksa":     "Baksa",
    "dhemaji":   "Dhemaji",
    "lakhimpur": "Lakhimpur",
}
