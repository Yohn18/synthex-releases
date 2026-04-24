"""
modules/ai_client.py
Thin HTTP wrapper for multiple AI providers.
No SDKs needed — only requests (already a dependency).
"""
import json
import requests
import certifi

_PROVIDERS = {
    "openai":    "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
    "groq":      "Groq (LLaMA / Mixtral)",
    "gemini":    "Google Gemini",
}

_DEFAULT_MODELS = {
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "groq":      "llama3-70b-8192",
    "gemini":    "gemini-1.5-flash",
}

PROVIDER_NAMES  = list(_PROVIDERS.keys())
PROVIDER_LABELS = list(_PROVIDERS.values())


def _post(url, headers, body, timeout=30):
    for verify in (certifi.where(), False):
        try:
            r = requests.post(url, headers=headers,
                              data=json.dumps(body), timeout=timeout,
                              verify=verify)
            return r
        except Exception as e:
            last = e
    raise last


def call_ai(prompt: str, provider: str, api_key: str,
            model: str = "",
            system: str = "",
            system_prompt: str = "",
            max_tokens: int = 800,
            history: list = None) -> str:
    """
    Send `prompt` to the selected provider and return the text response.
    `history` is a list of {"role": "user"/"assistant", "content": str} for
    multi-turn conversation. Raises ValueError on bad config, RuntimeError on error.
    """
    if not api_key:
        raise ValueError("API key kosong. Masukkan API key di Settings → AI.")
    provider = provider.lower().strip()
    model    = (model or "").strip() or _DEFAULT_MODELS.get(provider, "")
    sys_msg  = (system_prompt or system or "").strip()
    history  = history or []

    if provider == "openai":
        messages = []
        if sys_msg:
            messages.append({"role": "system", "content": sys_msg})
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "messages": messages, "max_tokens": max_tokens}
        r = _post("https://api.openai.com/v1/chat/completions",
                  headers={"Authorization": "Bearer {}".format(api_key),
                           "Content-Type": "application/json"},
                  body=body)
        if not r.ok:
            raise RuntimeError("OpenAI error {}: {}".format(r.status_code, r.text[:200]))
        return r.json()["choices"][0]["message"]["content"].strip()

    elif provider == "anthropic":
        messages = []
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if sys_msg:
            body["system"] = sys_msg
        r = _post("https://api.anthropic.com/v1/messages",
                  headers={"x-api-key": api_key,
                           "anthropic-version": "2023-06-01",
                           "Content-Type": "application/json"},
                  body=body)
        if not r.ok:
            raise RuntimeError("Anthropic error {}: {}".format(r.status_code, r.text[:200]))
        return r.json()["content"][0]["text"].strip()

    elif provider == "groq":
        messages = []
        if sys_msg:
            messages.append({"role": "system", "content": sys_msg})
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "messages": messages, "max_tokens": max_tokens}
        r = _post("https://api.groq.com/openai/v1/chat/completions",
                  headers={"Authorization": "Bearer {}".format(api_key),
                           "Content-Type": "application/json"},
                  body=body)
        if not r.ok:
            raise RuntimeError("Groq error {}: {}".format(r.status_code, r.text[:200]))
        return r.json()["choices"][0]["message"]["content"].strip()

    elif provider == "gemini":
        contents = []
        for h in history:
            role = "user" if h["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": h["content"]}]})
        user_text = (sys_msg + "\n\n" + prompt) if sys_msg and not contents else prompt
        contents.append({"role": "user", "parts": [{"text": user_text}]})
        body = {"contents": contents,
                "generationConfig": {"maxOutputTokens": max_tokens}}
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               "{}:generateContent?key={}".format(model, api_key))
        r = _post(url,
                  headers={"Content-Type": "application/json"},
                  body=body)
        if not r.ok:
            raise RuntimeError("Gemini error {}: {}".format(r.status_code, r.text[:200]))
        return (r.json()["candidates"][0]["content"]["parts"][0]["text"]).strip()

    else:
        raise ValueError("Provider tidak dikenal: {}".format(provider))
