# -*- coding: utf-8 -*-
"""
modules/ps_agent.py
PowerShell agent — Haiku generates command, subprocess executes it.

Hierarchy:
  Claude Sonnet (Claude Code / orchestrator)
      └── Haiku  → generate safe PowerShell command
          └── subprocess → execute on Windows
"""
import json
import os
import subprocess
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SYSTEM_PROMPT = """You are a PowerShell command generator for Windows automation.

Rules:
- Output ONLY the PowerShell command, no explanation, no markdown fences.
- Use single-line commands or semicolons to chain. Avoid here-strings.
- Prefer safe, read-only operations unless explicitly asked to write/delete.
- Always add -ErrorAction SilentlyContinue where appropriate.
- Output must be directly pasteable into PowerShell.

Example:
Task: list all .log files larger than 1MB in C:/Users/Admin
Output: Get-ChildItem -Path "C:/Users/Admin" -Filter "*.log" -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 1MB } | Select-Object FullName, Length"""

_BLOCKED = [
    r"\bFormat-Disk\b", r"\bRemove-Item\b.*-Recurse.*-Force",
    r"\bStop-Computer\b", r"\bRestart-Computer\b",
    r"rm\s+-rf", r"del\s+/[sS]",
    r"\bInvoke-Expression\b.*\$env",
]


def _load_ai_cfg() -> dict:
    try:
        with open(os.path.join(_ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f).get("ai", {})
    except Exception:
        return {}


def _is_safe(cmd: str) -> tuple[bool, str]:
    """Basic safety check. Returns (ok, reason)."""
    for pattern in _BLOCKED:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False, "Command diblokir karena terlalu destruktif: {}".format(pattern)
    return True, ""


def generate_command(task: str, api_key: str = "", provider: str = "",
                     model: str = "") -> str:
    """
    Use Haiku (or configured model) to generate a PowerShell command
    from a natural-language task description.
    """
    from modules.ai_client import call_ai

    cfg      = _load_ai_cfg()
    api_key  = api_key  or cfg.get("api_key", "")
    provider = provider or cfg.get("provider", "anthropic")
    # Force cheapest model for generation — Haiku is the anak buah
    model    = model or (
        "claude-haiku-4-5-20251001" if provider == "anthropic"
        else cfg.get("model", "")
    )

    if not api_key:
        raise ValueError("API key kosong. Set di Settings → AI.")

    return call_ai(
        prompt=task,
        provider=provider,
        api_key=api_key,
        model=model,
        system=_SYSTEM_PROMPT,
        max_tokens=256,
    )


def execute(cmd: str, timeout: int = 30, cwd: str = None) -> dict:
    """
    Execute a PowerShell command. Returns:
        {"ok": bool, "output": str, "error": str, "returncode": int}
    """
    ok, reason = _is_safe(cmd)
    if not ok:
        return {"ok": False, "output": "", "error": reason, "returncode": -1}

    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile",
             "-ExecutionPolicy", "Bypass", "-Command", cmd],
            capture_output=True, text=True,
            timeout=timeout, cwd=cwd or _ROOT,
            encoding="utf-8", errors="replace",
        )
        return {
            "ok":         result.returncode == 0,
            "output":     result.stdout.strip(),
            "error":      result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "",
                "error": "Timeout setelah {}s".format(timeout), "returncode": -1}
    except FileNotFoundError:
        return {"ok": False, "output": "",
                "error": "PowerShell tidak ditemukan di sistem ini.", "returncode": -1}


def run_task(task: str, mode: str = "auto", timeout: int = 30,
             api_key: str = "", provider: str = "", model: str = "") -> dict:
    """
    High-level: given a task string, generate + execute PowerShell.

    mode="auto"   → Haiku generates command from natural-language task
    mode="manual" → task IS the command, skip generation

    Returns:
        {"ok": bool, "command": str, "output": str, "error": str}
    """
    if mode == "manual":
        cmd = task.strip()
    else:
        cmd = generate_command(task, api_key=api_key,
                               provider=provider, model=model).strip()
        # Strip accidental markdown fences
        if cmd.startswith("```"):
            cmd = re.sub(r"^```[a-z]*\n?", "", cmd)
            cmd = re.sub(r"\n?```$", "", cmd)
        cmd = cmd.strip()

    result = execute(cmd, timeout=timeout)
    result["command"] = cmd
    return result
