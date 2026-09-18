"""
config.py — environment, constants, and shared Gemini client.
"""
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = "gemini-3.5-flash-lite"

# 45-second timeout in milliseconds.
# The SDK has NO default timeout — without this, calls hang forever.
_HTTP_OPTIONS = types.HttpOptions(timeout=45000)

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=_HTTP_OPTIONS,
) if GEMINI_API_KEY else None

DB_PATH = os.path.join(os.path.dirname(__file__), "defect_data.db")
