# -*- coding: utf-8 -*-
"""
modules/vision/ocr.py
Extract text from images using AI vision (Claude/GPT/Gemini).
No Tesseract needed — uses existing AI provider config.
"""
import base64
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SYSTEM = ("You are an OCR engine. Extract ALL visible text from the image exactly as it appears. "
           "Return only the extracted text, no explanation, no formatting. "
           "Preserve line breaks. If no text found, return empty string.")


def _load_ai_cfg() -> dict:
    try:
        with open(os.path.join(_ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f).get("ai", {})
    except Exception:
        return {}


def _img_to_b64(path: str) -> tuple:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mt  = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
           "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode(), mt


def extract_text(image_path: str, api_key: str = "", provider: str = "",
                 model: str = "", language: str = "") -> str:
    """
    Extract text from image_path using AI vision.
    Returns extracted text string.
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError("File tidak ditemukan: {}".format(image_path))

    cfg      = _load_ai_cfg()
    api_key  = api_key  or cfg.get("api_key", "")
    provider = (provider or cfg.get("provider", "anthropic")).lower()
    if not api_key:
        raise ValueError("API key kosong. Set di Settings -> AI.")

    b64, mt = _img_to_b64(image_path)
    prompt  = "Extract all text from this image."
    if language:
        prompt += " Language hint: {}.".format(language)

    import requests, certifi

    if provider == "anthropic":
        model = model or "claude-haiku-4-5-20251001"
        body  = {
            "model": model, "max_tokens": 1024,
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                 "media_type": mt, "data": b64}},
                {"type": "text", "text": prompt},
            ]}],
        }
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": api_key,
                                   "anthropic-version": "2023-06-01",
                                   "Content-Type": "application/json"},
                          json=body, timeout=30, verify=certifi.where())
        if not r.ok:
            raise RuntimeError("Anthropic OCR error {}: {}".format(
                r.status_code, r.text[:200]))
        return (r.json().get("content", [{}])[0].get("text") or "").strip()

    elif provider == "openai":
        model = model or "gpt-4o-mini"
        body  = {
            "model": model, "max_tokens": 1024,
            "messages": [{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:{};base64,{}".format(mt, b64)}},
                {"type": "text", "text": _SYSTEM + "\n\n" + prompt},
            ]}],
        }
        r = requests.post("https://api.openai.com/v1/chat/completions",
                          headers={"Authorization": "Bearer {}".format(api_key),
                                   "Content-Type": "application/json"},
                          json=body, timeout=30, verify=certifi.where())
        if not r.ok:
            raise RuntimeError("OpenAI OCR error {}: {}".format(
                r.status_code, r.text[:200]))
        return (r.json().get("choices", [{}])[0]
                .get("message", {}).get("content") or "").strip()

    elif provider == "gemini":
        model = model or "gemini-2.0-flash"
        url   = ("https://generativelanguage.googleapis.com/v1beta/models/"
                 "{}:generateContent?key={}".format(model, api_key))
        body  = {"contents": [{"parts": [
            {"inline_data": {"mime_type": mt, "data": b64}},
            {"text": _SYSTEM + "\n\n" + prompt},
        ]}]}
        r = requests.post(url, json=body, timeout=30, verify=certifi.where())
        if not r.ok:
            raise RuntimeError("Gemini OCR error {}: {}".format(
                r.status_code, r.text[:200]))
        return (r.json().get("candidates", [{}])[0]
                .get("content", {}).get("parts", [{}])[0]
                .get("text") or "").strip()

    else:
        raise ValueError("Provider {} belum support vision OCR.".format(provider))


def screenshot_and_ocr(save_dir: str = None, api_key: str = "",
                       provider: str = "", model: str = "") -> tuple:
    """Screenshot layar, OCR, return (text, path)."""
    import datetime, tempfile
    from PIL import ImageGrab

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(save_dir, "ocr_{}.png".format(ts))
    else:
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)

    ImageGrab.grab().save(path)
    text = extract_text(path, api_key=api_key, provider=provider, model=model)
    return text, path
