import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-opus-5")
COUNSEL_MODEL = os.environ.get("COUNSEL_MODEL", "claude-sonnet-5")
RESEARCH_MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-5")
JURY_MODEL = os.environ.get("JURY_MODEL", COUNSEL_MODEL)

# Caps how many repetitions the /api/session/batch variance-check endpoint will run in one request,
# since each repetition re-runs the full multi-call trial pipeline synchronously.
MAX_BATCH_RUNS = int(os.environ.get("MAX_BATCH_RUNS", "5"))

PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)

RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
os.makedirs(RUNS_DIR, exist_ok=True)

if not ANTHROPIC_API_KEY:
    print(
        "WARNING: ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key "
        "before starting a session."
    )
