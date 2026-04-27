# -*- coding: utf-8 -*-
"""
modules/agents/providers.py
API clients for Groq, Together.ai, OpenRouter.
All three use OpenAI-compatible endpoints.
"""
import json
import time
import requests
import certifi

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "label": "Groq",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1/chat/completions",
        "label": "Together.ai",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "label": "OpenRouter",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/Yohn18/synthex",
            "X-Title": "Synthex AI Team",
        },
    },
}

# Best models per provider for each task type
AUTO_SELECT = {
    "coding": {
        "provider": "groq",
        "model":    "llama-3.3-70b-versatile",
        "label":    "Groq · LLaMA 3.3 70B",
    },
    "analysis": {
        "provider": "together",
        "model":    "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "label":    "Together · Qwen 2.5 72B",
    },
    "research": {
        "provider": "openrouter",
        "model":    "google/gemini-flash-1.5",
        "label":    "OpenRouter · Gemini Flash",
    },
    "writing": {
        "provider": "openrouter",
        "model":    "anthropic/claude-3-haiku",
        "label":    "OpenRouter · Claude Haiku",
    },
    "math": {
        "provider": "together",
        "model":    "deepseek-ai/DeepSeek-R1",
        "label":    "Together · DeepSeek R1",
    },
    "review": {
        "provider": "groq",
        "model":    "mixtral-8x7b-32768",
        "label":    "Groq · Mixtral 8x7B",
    },
    "general": {
        "provider": "groq",
        "model":    "llama-3.1-8b-instant",
        "label":    "Groq · LLaMA 3.1 8B",
    },
    "orchestrator": {
        "provider": "openrouter",
        "model":    "anthropic/claude-3-haiku",
        "label":    "OpenRouter · Claude Haiku",
    },
    "critic": {
        "provider": "groq",
        "model":    "llama-3.3-70b-versatile",
        "label":    "Groq · LLaMA 3.3 70B",
    },
}

# Fallback chain per provider
FALLBACKS = {
    "groq":       ["together", "openrouter"],
    "together":   ["groq",    "openrouter"],
    "openrouter": ["groq",    "together"],
}


def call(provider: str, model: str, messages: list, api_key: str,
         max_tokens: int = 2048, temperature: float = 0.7,
         stream_cb=None, timeout: int = 60) -> str:
    """
    Call any provider. Returns text response.
    stream_cb(chunk: str) called for each streamed token if provided.
    """
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError("Provider tidak dikenal: {}".format(provider))
    if not api_key:
        raise ValueError("API key {} kosong".format(provider))

    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "Content-Type":  "application/json",
    }
    headers.update(cfg.get("extra_headers", {}))

    body = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
        "stream":      stream_cb is not None,
    }

    try:
        resp = requests.post(
            cfg["base_url"],
            headers=headers,
            data=json.dumps(body),
            timeout=timeout,
            verify=certifi.where(),
            stream=stream_cb is not None,
        )
    except requests.Timeout:
        raise RuntimeError("{} timeout setelah {}s".format(provider, timeout))
    except requests.ConnectionError as e:
        raise RuntimeError("{} connection error: {}".format(provider, e))

    if not resp.ok:
        raise RuntimeError("{} HTTP {}: {}".format(provider, resp.status_code, resp.text[:300]))

    # Streaming
    if stream_cb is not None:
        full = []
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8", errors="replace")
            if line.startswith("data: "):
                line = line[6:]
            if line == "[DONE]":
                break
            try:
                chunk = json.loads(line)
                delta = (chunk.get("choices", [{}])[0]
                              .get("delta", {})
                              .get("content", "") or "")
                if delta:
                    full.append(delta)
                    stream_cb(delta)
            except Exception:
                continue
        return "".join(full)

    # Non-streaming
    data = resp.json()
    text = (data.get("choices", [{}])[0]
                .get("message", {})
                .get("content") or "")
    if not text:
        raise RuntimeError("{} response kosong: {}".format(provider, str(data)[:200]))
    return text.strip()


def call_with_fallback(task_type: str, messages: list, keys: dict,
                       max_tokens: int = 2048, stream_cb=None) -> tuple:
    """
    Auto-select best model for task_type, with fallback.
    keys = {"groq": "...", "together": "...", "openrouter": "..."}
    Returns (text, provider_label_used)
    """
    sel = AUTO_SELECT.get(task_type, AUTO_SELECT["general"])
    providers_to_try = [sel["provider"]] + FALLBACKS.get(sel["provider"], [])

    last_err = None
    for prov in providers_to_try:
        key = keys.get(prov, "")
        if not key:
            continue
        model = sel["model"] if prov == sel["provider"] else AUTO_SELECT.get(task_type, {}).get("model", "llama-3.1-8b-instant")
        # Use provider's own default model on fallback
        if prov != sel["provider"]:
            fb_sel = next((v for k, v in AUTO_SELECT.items()
                           if v["provider"] == prov and k == task_type), None)
            if fb_sel:
                model = fb_sel["model"]
            else:
                model = {
                    "groq":       "llama-3.3-70b-versatile",
                    "together":   "Qwen/Qwen2.5-72B-Instruct-Turbo",
                    "openrouter": "anthropic/claude-3-haiku",
                }.get(prov, "llama-3.1-8b-instant")
        try:
            text = call(prov, model, messages, key,
                        max_tokens=max_tokens, stream_cb=stream_cb)
            label = "{} · {}".format(PROVIDERS[prov]["label"], model.split("/")[-1])
            return text, label
        except Exception as e:
            last_err = e
            time.sleep(0.5)
            continue

    raise RuntimeError("Semua provider gagal. Error terakhir: {}".format(last_err))
