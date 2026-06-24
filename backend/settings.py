import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RULES_DIR = DATA_DIR / "knowledge" / "rules"
BOOKS_DIR = DATA_DIR / "knowledge" / "books"
OPENAPI_DIR = DATA_DIR / "openapi"
VECTOR_DIR = DATA_DIR / "vector_store"
SQLITE_PATH = DATA_DIR / "chat.db"
OPENAPI_PATH = OPENAPI_DIR / "stock_api.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o").strip()
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "gpt-4o-mini").strip()
HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "8"))

SUPER_ADMIN_USERNAME = os.getenv("SUPER_ADMIN_USERNAME", "admin").strip()
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "Admin@123456").strip()
AUTH_SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "7"))
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "stocktraders_session").strip()
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() == "true"
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip()

RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_CHUNK_TOKENS = int(os.getenv("RAG_CHUNK_TOKENS", "650"))
RAG_OVERLAP_TOKENS = int(os.getenv("RAG_OVERLAP_TOKENS", "120"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-large").strip()

MAX_TOOL_LOOPS = int(os.getenv("MAX_TOOL_LOOPS", "5"))

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Model options (UI dropdown) - bạn có thể thêm/bớt
ALLOWED_MODELS = [
    "gpt-4o",
    "gpt-5.2",
    "gpt-5.1-instant",
    "gpt-5.1-thinking",
    "gpt-5.2-instant",
    "gpt-5.2-thinking",
]

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    OPENAPI_DIR.mkdir(parents=True, exist_ok=True)
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)

