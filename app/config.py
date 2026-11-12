"""Central config — all constants and env vars in one place."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR    = Path(__file__).parent.parent
DOCS_DIR    = BASE_DIR / "docs"
DATA_DIR    = BASE_DIR / "data"
INDEX_FILE  = DATA_DIR / "index.npz"
CHUNKS_FILE = DATA_DIR / "chunks.json"

# Embedding model
EMBED_MODEL      = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Retrieval
TOP_K                = 6
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.30"))

# LLM — Groq is default; others available via LLM_PROVIDER env var
LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "groq")
GROQ_MODEL      = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
