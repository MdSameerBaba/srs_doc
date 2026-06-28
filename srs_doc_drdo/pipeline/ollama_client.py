"""
Ollama HTTP client — synchronous, with JSON extraction and retry logic.
Target models: gpt-oss-20b (heavy) and gemma3n:e4b (fast), both running locally.
"""

import json
import re
import time
from typing import Union

import requests

OLLAMA_TIMEOUT = 360  # 6 minutes — local LLMs can be slow on large prompts


# ─────────────────────────────────────────────────────────────
# JSON extraction
# ─────────────────────────────────────────────────────────────

def extract_json(text: str) -> dict:
    """
    Robustly extract the first valid JSON object from LLM output.
    Local models sometimes wrap JSON in markdown fences or add preamble text.
    """
    if not text:
        return {}

    # 1. Try direct parse first (happy path)
    text_stripped = text.strip()
    try:
        return json.loads(text_stripped)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences
    for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

    # 3. Find the largest balanced JSON object
    best: dict | None = None
    best_len = 0
    for i, ch in enumerate(text):
        if ch == "{":
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                if depth == 0:
                    candidate = text[i : j + 1]
                    if len(candidate) > best_len:
                        try:
                            parsed = json.loads(candidate)
                            best = parsed
                            best_len = len(candidate)
                        except json.JSONDecodeError:
                            pass
                    break

    if best is not None:
        return best

    raise ValueError(f"Could not extract JSON from response (first 300 chars): {text[:300]}")


# ─────────────────────────────────────────────────────────────
# Core chat function
# ─────────────────────────────────────────────────────────────

def chat(
    model: str,
    prompt: str,
    base_url: str = "http://localhost:11434",
    expect_json: bool = True,
    max_retries: int = 3,
    temperature: float = 0.1,
) -> Union[dict, str]:
    """
    Send a chat message to a local Ollama model.

    Args:
        model:        Ollama model name (e.g. 'gpt-oss-20b', 'gemma3n:e4b')
        prompt:       User prompt string
        base_url:     Ollama server URL
        expect_json:  If True, parse response as JSON; otherwise return raw string
        max_retries:  Number of retry attempts on failure
        temperature:  Sampling temperature (lower = more deterministic)

    Returns:
        dict if expect_json=True, str otherwise
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": 16384
        },
    }
    if expect_json:
        payload["format"] = "json"

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{base_url}/api/chat",
                json=payload,
                timeout=OLLAMA_TIMEOUT,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]

            if expect_json:
                return extract_json(content)
            return content

        except (requests.RequestException, KeyError, ValueError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # exponential back-off: 1s, 2s, 4s
                time.sleep(wait)

    raise RuntimeError(
        f"Ollama call failed after {max_retries} attempts. Last error: {last_error}"
    )


# ─────────────────────────────────────────────────────────────
# Connection helpers
# ─────────────────────────────────────────────────────────────

def check_connection(base_url: str = "http://localhost:11434") -> tuple[bool, str]:
    """Ping Ollama and return (is_up, human_readable_message)."""
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        model_str = ", ".join(models) if models else "none pulled yet"
        return True, f"✅ Connected — models available: {model_str}"
    except requests.ConnectionError:
        return False, f"❌ Cannot reach Ollama at {base_url}. Is `ollama serve` running?"
    except Exception as exc:
        return False, f"❌ Unexpected error: {exc}"


def list_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Return list of locally available model names."""
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
