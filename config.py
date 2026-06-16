import os

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
EMBEDDING_MODEL = "gemini-embedding-001"
LLM_MODEL = "gemini-2.5-flash"

# ChromaDB
CHROMA_PATH = "./chroma_store"
COLLECTION_NAME = "docsentinel"

# Thresholds
SIMILARITY_THRESHOLD = 0.75   # min cosine sim to link code <-> doc
CONFIDENCE_HIGH = 0.80         # auto-fix above this
CONFIDENCE_LOW = 0.50          # flag for human review below this

# Paths (relative to repo root)
CODE_EXTENSIONS = [".py"]
DOC_EXTENSIONS = [".md"]
MAP_OUTPUT = "./code_doc_map.json"
