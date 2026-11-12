"""Single generate() function; swap provider via LLM_PROVIDER env var."""
import os, httpx
from app.config import (
    LLM_PROVIDER, GROQ_MODEL,
    OPENAI_MODEL, ANTHROPIC_MODEL, GEMINI_MODEL,
)


def generate(system: str, user: str) -> str:
    """Call the configured LLM and return the raw text response."""
    if LLM_PROVIDER == "openai":
        return _openai(system, user)
    if LLM_PROVIDER == "anthropic":
        return _anthropic(system, user)
    if LLM_PROVIDER == "gemini":
        return _gemini(system, user)
    return _groq(system, user)  # default


# ── Groq ──────────────────────────────────────────────────────────────────────

def _groq(system: str, user: str) -> str:
    """Groq cloud inference — fast, free tier at console.groq.com.
    Retries up to 3 times with exponential backoff on 429 rate-limit errors.
    """
    import time as _time
    headers = {
        "Authorization": f"Bearer {os.environ['GROQ_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "temperature": 0,
    }
    for attempt in range(3):
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload, headers=headers, timeout=60,
        )
        if r.status_code == 429:
            wait = 20 * (attempt + 1)  # 20s, 40s, 60s
            print(f"  [Groq 429] rate limited, waiting {wait}s ...")
            _time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    r.raise_for_status()  # raise after all retries exhausted


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _openai(system: str, user: str) -> str:
    import openai
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _anthropic(system: str, user: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


# ── Gemini ────────────────────────────────────────────────────────────────────

def _gemini(system: str, user: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system,
    )
    return model.generate_content(user).text
