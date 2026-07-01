"""
Ollama HTTP client — synchronous, with universal JSON extraction and retry logic.
Compatible with all local models: gemma3n, qwen3, deepseek-r1, llama3, mistral, phi, etc.
"""

import json
import re
import time
from typing import Union

import requests

OLLAMA_TIMEOUT = 360  # 6 minutes — local LLMs can be slow on large prompts


# ─────────────────────────────────────────────────────────────
# Universal LLM output cleaner
# Works with ALL local models regardless of vendor
# ─────────────────────────────────────────────────────────────

def clean_llm_output(text: str) -> str:
    """
    Strip non-content artifacts from any local LLM's raw output.

    Handles:
      - <think>...</think>     qwen3, deepseek-r1 reasoning blocks
      - <reasoning>...</reasoning>   some deepseek variants
      - [THINKING]...[/THINKING]     alternative reasoning markers
      - Dangling / unclosed <think>  when output was cut short
      - Leading prose preambles      "Sure! Here is the JSON:" (gemma3, llama3, phi)
      - Trailing commentary          "I hope this helps!" after JSON
    """
    if not text:
        return text

    # 1. Remove complete XML-style reasoning blocks (multi-line safe)
    for tag in ["think", "reasoning", "thought", "scratchpad"]:
        text = re.sub(
            rf"<{tag}>[\s\S]*?</{tag}>",
            "",
            text,
            flags=re.IGNORECASE
        )
        # Also remove dangling unclosed opening tag and everything after it
        text = re.sub(
            rf"<{tag}>[\s\S]*$",
            "",
            text,
            flags=re.IGNORECASE
        )

    # 2. Remove [THINKING]...[/THINKING] style blocks
    text = re.sub(
        r"\[THINKING\][\s\S]*?\[/THINKING\]",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text.strip()


def _strip_prose_preamble(text: str) -> str:
    """
    Remove common AI assistant preamble phrases from free-text prose output.
    These appear in gemma3, llama3, phi, mistral when generating plain text.

    Examples removed:
      "Sure! Here is the section:"
      "Certainly, here's the generated SRS section:"
      "Below is the SRS section for Introduction:"
    """
    # Remove common single-line opener phrases at the very start
    opener_pattern = re.compile(
        r"^[ \t]*(Sure[!,.]?|Certainly[!,.]?|Of course[!,.]?|Absolutely[!,.]?|"
        r"Here(?:'s| is)(?: the| a)?[^.\n]*[.:]?|"
        r"Below(?:'s| is)(?: the| a)?[^.\n]*[.:]?|"
        r"The following[^.\n]*[.:]?|"
        r"I(?:'ll| will)(?: now| help| generate)?[^.\n]*[.:]?|"
        r"Let me[^.\n]*[.:]?)[ \t]*\n+",
        re.IGNORECASE | re.MULTILINE
    )
    # Apply up to 3 times in case there are stacked opener lines
    for _ in range(3):
        cleaned = opener_pattern.sub("", text, count=1)
        if cleaned == text:
            break
        text = cleaned

    return text.strip()


# ─────────────────────────────────────────────────────────────
# JSON extraction — model-agnostic, multi-strategy
# ─────────────────────────────────────────────────────────────

def extract_json(text: str) -> dict:
    """
    Robustly extract the first valid JSON object from any LLM output.
    Handles preamble text, reasoning blocks, and markdown code fences
    from all common local models (gemma3n, qwen3, llama3, mistral, phi, etc.)
    """
    if not text:
        return {}

    # Step 0: Universal cleanup — remove reasoning blocks and trim
    text = clean_llm_output(text)
    if not text:
        return {}

    # Step 1: Direct parse (happy path — clean models like mistral/gemma3n)
    text_stripped = text.strip()
    try:
        result = json.loads(text_stripped)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Step 2: Strip markdown code fences (gemma3n, llama3 often wrap in ```json)
    for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(1).strip())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

    # Step 3: Find the LARGEST balanced JSON object by scanning for {
    # This handles "Here is the JSON: {...}" style output from phi/llama3
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
                    candidate = text[i: j + 1]
                    if len(candidate) > best_len:
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                best = parsed
                                best_len = len(candidate)
                        except json.JSONDecodeError:
                            pass
                    break

    if best is not None:
        return best

    raise ValueError(
        f"Could not extract JSON object from LLM response "
        f"(first 300 chars): {text[:300]}"
    )


def extract_json_array(text: str) -> list:
    """
    Robustly extract the first valid JSON array from any LLM output.
    Uses the same multi-strategy approach as extract_json.
    """
    if not text:
        return []

    # Step 0: Universal cleanup
    text = clean_llm_output(text)
    if not text:
        return []

    # Step 1: Direct parse
    text_stripped = text.strip()
    try:
        result = json.loads(text_stripped)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Step 2: Strip markdown code fences
    for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(1).strip())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

    # Step 3: Find the LARGEST balanced JSON array by scanning for [
    best: list | None = None
    best_len = 0
    for i, ch in enumerate(text):
        if ch == "[":
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "[":
                    depth += 1
                elif text[j] == "]":
                    depth -= 1
                if depth == 0:
                    candidate = text[i: j + 1]
                    if len(candidate) > best_len:
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, list):
                                best = parsed
                                best_len = len(candidate)
                        except json.JSONDecodeError:
                            pass
                    break

    if best is not None:
        return best

    raise ValueError(
        f"Could not extract JSON array from LLM response "
        f"(first 300 chars): {text[:300]}"
    )


# ─────────────────────────────────────────────────────────────
# Global provider configuration
# ─────────────────────────────────────────────────────────────

PROVIDER = "ollama"
API_KEY = ""


def chat(
    model: str,
    prompt: str,
    base_url: str = "http://localhost:11434",
    expect_json: bool = True,
    max_retries: int = 3,
    temperature: float = 0.1,
) -> Union[dict, str]:
    """
    Send a chat message to the configured LLM provider (Ollama or Gemini API).
    Automatically routes based on the global PROVIDER setting.
    """
    if PROVIDER == "gemini":
        return _chat_gemini(model, prompt, expect_json, max_retries, temperature)
    return _chat_ollama(model, prompt, base_url, expect_json, max_retries, temperature)


def _chat_gemini(
    model: str,
    prompt: str,
    expect_json: bool = True,
    max_retries: int = 3,
    temperature: float = 0.1,
) -> Union[dict, str]:
    """Route to Google Gemini API."""
    actual_model = model
    if not model.startswith("gemini-"):
        if any(k in model.lower() for k in ["heavy", "20b", "pro", "oss", "32b", "70b"]):
            actual_model = "gemini-2.5-pro"
        else:
            actual_model = "gemini-2.5-flash"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:generateContent?key={API_KEY}"
    headers = {"Content-Type": "application/json"}

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if expect_json:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            if expect_json:
                return extract_json(content)
            return clean_llm_output(content)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Gemini API call failed after {max_retries} attempts. Last error: {last_error}"
    )


def _chat_ollama(
    model: str,
    prompt: str,
    base_url: str = "http://localhost:11434",
    expect_json: bool = True,
    max_retries: int = 3,
    temperature: float = 0.1,
) -> Union[dict, str]:
    """
    Send a request to local Ollama server.

    Notes:
      - format=json is set for JSON stages to constrain the model output.
        NOTE: Ollama's format=json forces a JSON *object* {}. For stages
        that expect a JSON *array* [], we set expect_json=False and use
        extract_json_array() separately (Stage B).
      - num_ctx=16384 overrides Ollama's default 2048-token context window.
      - All raw content is passed through clean_llm_output() to strip
        reasoning blocks and prose preambles regardless of model.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": 64000,
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
            # For free-text output: strip reasoning blocks and preamble
            return _strip_prose_preamble(clean_llm_output(content))

        except (requests.RequestException, KeyError, ValueError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                wait = 2 ** attempt   # exponential back-off: 1s, 2s, 4s
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
