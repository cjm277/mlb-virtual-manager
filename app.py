"""Start MLB Virtual Manager: python app.py, then open http://localhost:8000 (opens automatically)."""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser

import uvicorn

from backend import config


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the MLB Virtual Manager web app.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="Don't open a browser tab")
    args = ap.parse_args()

    found = config.load_env()
    if not os.getenv(config.API_KEY_NAME):
        print(f"WARNING: {config.API_KEY_NAME} was not found in {', '.join(map(str, config.ENV_SEARCH_PATHS))}.\n"
              "The app will open, but building a plan needs the key.")
    else:
        print(f"API key found in {found[0]} (value hidden). Model: {config.MODEL_NAME}")
    url = f"http://localhost:{args.port}"
    print(f"MLB Virtual Manager is running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("backend.main:app", host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
