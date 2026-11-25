"""Shared environment configuration; no provider calls or agent decisions."""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def model_name():
    return os.getenv("AGENT_MODEL", "openai/" + os.getenv("OPENAI_MODEL", "gpt-6-luna"))


def require_model():
    key = "GOOGLE_API_KEY" if model_name().startswith("gemini/") else "OPENAI_API_KEY"
    if not os.getenv(key):
        raise RuntimeError(
            f"Set {key} in .env. Ask the facilitator for the workshop proxy configuration."
        )
