"""Settings for MLB Virtual Manager.

API keys come from a .env file. We look in two places, in this order:
  1. the repo folder itself (Final Project/.env)
  2. the folder above the repo (where the teaching staff keep their shared .env)

Values from the repo's own .env win; the parent .env only fills in what is missing.
Keys are never printed or logged.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_SEARCH_PATHS = (REPO_ROOT / ".env", REPO_ROOT.parent / ".env")
PROMPTS_DIR = REPO_ROOT / "backend" / "prompts"
RUNS_DIR = REPO_ROOT / "runs"

# The course Portkey key may only be used with this model. It is the only model string in the project.
MODEL_NAME = "gpt-6-luna"
API_KEY_NAME = "PORTKEY_API_KEY"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# --- Budget: hard caps for one game plan (all agents combined) -----------------
MAX_REQUESTS_PER_RUN = 80          # model calls
MAX_TOOL_CALLS_PER_RUN = 120
MAX_TOKENS_PER_RUN = 600_000       # input + output; at list prices this caps a run near $0.15
MAX_STEPS_PER_AGENT = 12           # model calls inside one agent's loop
MAX_OUTPUT_TOKENS_PER_RESPONSE = 6_000
MAX_FIX_ROUNDS = 2                 # consistency-checker fix loop

# --- Budget across runs (backend/budget.py) ---------------------------------------
DAILY_BUDGET_USD = 2.00            # all plans + chat in one day; then new builds and chat are refused
REUSE_HOURS = 24                   # the same request within this window reopens the saved plan (no new cost)
AGENT_TIMEOUT_SECONDS = 240        # one agent's whole loop
# One model call normally takes 1-14 s. A call that stalls (it happened once: 89 s for a 700-token answer)
# is abandoned after 60 s and retried, without cutting off genuinely long but productive work.
MODEL_REQUEST_TIMEOUT_SECONDS = 60
MODEL_MAX_RETRIES = 2

# --- Pricing (USD per 1M tokens), for cost in the audit trail -------------------
# Source: genai-prices (Pydantic's public price database, shipped with PydanticAI), entry "GPT-6 Luna",
# verified by its maintainers against https://developers.openai.com/api/docs/pricing on 2026-10-12.
PRICE_INPUT_PER_M = 0.20
PRICE_CACHED_INPUT_PER_M = 0.02
PRICE_OUTPUT_PER_M = 0.50
PRICE_SOURCE = "genai-prices 'GPT-6 Luna' (OpenAI list price, verified 2026-10-12)"


def cost_usd(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """List-price cost. input_tokens includes the cached ones, which are billed at the cached rate."""
    uncached = max(input_tokens - cached_tokens, 0)
    return (uncached * PRICE_INPUT_PER_M + cached_tokens * PRICE_CACHED_INPUT_PER_M
            + output_tokens * PRICE_OUTPUT_PER_M) / 1_000_000


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


def check_model_env() -> None:
    """Refuse to run if .env asks for a different model (the course key allows gpt-6-luna only)."""
    configured = os.getenv("OPENAI_MODEL", "").strip()
    if configured and configured != MODEL_NAME:
        raise SystemExit(f"OPENAI_MODEL in .env is '{configured}', but this app must use '{MODEL_NAME}'.")


# Portkey reports per response whether it answered from its cache (x-portkey-cache-status: HIT/MISS).
# Each agent loop sets its own list here; the hook appends one entry per model response.
GATEWAY_LOG: ContextVar[list | None] = ContextVar("gateway_log", default=None)


async def _record_gateway_headers(response) -> None:
    log = GATEWAY_LOG.get()
    if log is not None:
        log.append({"cache": response.headers.get("x-portkey-cache-status"),
                    "provider": response.headers.get("x-portkey-provider")})


@lru_cache(maxsize=1)
def build_model():
    """The single gpt-6-luna model, routed through Portkey, shared by every agent."""
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from openai import DefaultAsyncHttpxClient

    key = get_api_key()
    check_model_env()
    http = DefaultAsyncHttpxClient(event_hooks={"response": [_record_gateway_headers]})
    client = AsyncOpenAI(api_key=key, base_url=PORTKEY_BASE_URL, default_headers={"x-portkey-api-key": key},
                         timeout=MODEL_REQUEST_TIMEOUT_SECONDS, max_retries=MODEL_MAX_RETRIES, http_client=http)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def model_settings():
    from pydantic_ai.models.openai import OpenAIResponsesModelSettings

    return OpenAIResponsesModelSettings(max_tokens=MAX_OUTPUT_TOKENS_PER_RESPONSE, openai_reasoning_effort="low")


def run_limits():
    from pydantic_ai.usage import UsageLimits

    return UsageLimits(request_limit=MAX_REQUESTS_PER_RUN, tool_calls_limit=MAX_TOOL_CALLS_PER_RUN,
                       total_tokens_limit=MAX_TOKENS_PER_RUN)


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
