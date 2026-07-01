"""Shared configuration for the scheduler-org-memory demo."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Infrastructure ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")  # optional HMAC verification

# --- Live-update queue (Redis Streams) ---
STREAM = "scheduler-memory:index"
GROUP = "indexers"

# --- Models / collection ---
COLLECTION = "scheduler_memory"
DENSE_MODEL = "nomic-embed-text"   # served by Ollama
DENSE_DIM = 768
SPARSE_MODEL = "Qdrant/bm25"       # fastembed, no training needed

# --- Answer generation (Streamlit UI) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEN_MODEL = "claude-opus-4-8"      # Claude model that writes the answer; swap for speed if needed
TRANSLATE_MODEL = "claude-haiku-4-5"  # cheap/fast model: RU question -> EN search query (corpus is English)

# --- Corpus: kube-scheduler scoped to SIG Scheduling ---
K8S_REPO = "kubernetes/kubernetes"
ENH_REPO = "kubernetes/enhancements"
WEB_REPO = "kubernetes/website"
DESIGN_REPO = "kubernetes/design-proposals-archive"

# Canonical design proposals (the "why", incl. rejected approaches) — folded into the kep pile.
DESIGN_FILES = [
    "scheduling/pod-preemption.md",   # killer-demo target: cross-node preemption rejected
    "scheduling/pod-priority-api.md",
]

CODE_PATH = "pkg/scheduler"                     # recursive, *.go
KEP_PATH = "keps/sig-scheduling"                # recursive, README.md + kep.yaml
ISSUE_LABEL = "sig/scheduling"                  # issues + PRs
DOCS_PATHS = [                                  # kubernetes/website, recursive dirs / files
    "content/en/docs/concepts/scheduling-eviction",
    "content/en/docs/reference/scheduling",
    "content/en/docs/reference/command-line-tools-reference/kube-scheduler.md",
]

# Demo caps (keep ingestion bounded; raise as needed).
ISSUES_MAX = int(os.getenv("ISSUES_MAX", "200"))   # number of issues/PRs to pull
SKIP_GO_TESTS = os.getenv("SKIP_GO_TESTS", "1") == "1"

# --- Piles (knowledge map colors in Qdrant Visualize) ---
PILES = ["code", "kep", "issue", "docs"]

# --- Local data layout ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CODE_DIR = DATA_DIR / "code"
KEP_DIR = DATA_DIR / "kep"
ISSUE_DIR = DATA_DIR / "issue"
DOCS_DIR = DATA_DIR / "docs"
STATE_FILE = DATA_DIR / ".state.json"

PILE_DIRS = {"code": CODE_DIR, "kep": KEP_DIR, "issue": ISSUE_DIR, "docs": DOCS_DIR}

# Path separator encoding used in saved filenames ("/" -> "__"), reversed at index time.
PATH_SEP = "__"


def encode_path(path: str) -> str:
    return path.replace("/", PATH_SEP)


def decode_path(name: str) -> str:
    return name.replace(PATH_SEP, "/")
