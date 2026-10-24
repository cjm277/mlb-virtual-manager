"""Settings for MLB Virtual Manager.

API keys come from a .env file. We look in two places, in this order:
  1. the repo folder itself (Final Project/.env)
  2. the folder above the repo (where the teaching staff keep their shared .env)

Values from the repo's own .env win; the parent .env only fills in what is missing.
Keys are never printed or logged.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_SEARCH_PATHS = (REPO_ROOT / ".env", REPO_ROOT.parent / ".env")

# The course Portkey key may only be used with this model.
MODEL_NAME = "gpt-6-luna"
API_KEY_NAME = "PORTKEY_API_KEY"


def load_env(search_paths: tuple[Path, ...] = ENV_SEARCH_PATHS) -> list[Path]:
    """Load every .env found in search order and return the ones that were used."""
    found = [path for path in search_paths if path.is_file()]
    for path in found:
        # override=False: anything already set (repo .env first, or the shell) wins.
        load_dotenv(path, override=False)
    return found


def get_api_key(search_paths: tuple[Path, ...] = ENV_SEARCH_PATHS) -> str:
    """Return the Portkey key, or stop with a clear message saying where we looked."""
    load_env(search_paths)
    key = os.getenv(API_KEY_NAME, "").strip()
    if not key:
        places = "\n".join(f"  - {path}" for path in search_paths)
        raise SystemExit(
            f"{API_KEY_NAME} is missing. Add it to a .env file in one of:\n{places}\n"
            "See .env.example for the format."
        )
    return key


if __name__ == "__main__":
    used = load_env()
    if not used:
        print("No .env file found. Looked in:")
        for path in ENV_SEARCH_PATHS:
            print(f"  - {path}")
    else:
        print("Loaded .env from:")
        for path in used:
            print(f"  - {path}")
    status = "found (value hidden)" if os.getenv(API_KEY_NAME) else "MISSING"
    print(f"{API_KEY_NAME}: {status}")
    print(f"Model: {MODEL_NAME}")
