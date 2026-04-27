# -*- coding: utf-8 -*-
"""
agent_cli.py — Synthex AI Team CLI
Jalankan: python agent_cli.py
         python agent_cli.py "tugas kamu"
         python agent_cli.py --quick "tugas cepat"
"""
import sys
import os
import json
import time
import argparse
import threading

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

# ── ANSI colors ────────────────────────────────────────────────────────────────
R  = "\033[0m"
B  = "\033[1m"
DIM= "\033[2m"
PRP= "\033[38;5;135m"
CYN= "\033[38;5;51m"
GRN= "\033[38;5;82m"
YEL= "\033[38;5;220m"
RED= "\033[38;5;196m"
GRY= "\033[38;5;244m"
WHT= "\033[97m"

BANNER = """{PRP}{B}
  ███████╗██╗   ██╗███╗   ██╗████████╗██╗  ██╗███████╗██╗  ██╗
  ██╔════╝╚██╗ ██╔╝████╗  ██║╚══██╔══╝██║  ██║██╔════╝╚██╗██╔╝
  ███████╗ ╚████╔╝ ██╔██╗ ██║   ██║   ███████║█████╗   ╚███╔╝
  ╚════██║  ╚██╔╝  ██║╚██╗██║   ██║   ██╔══██║██╔══╝   ██╔██╗
  ███████║   ██║   ██║ ╚████║   ██║   ██║  ██║███████╗██╔╝ ██╗
  ╚══════╝   ╚═╝   ╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
{R}""".format(PRP=PRP, B=B, R=R)

SUBHEADER = "{CYN}{B}  AI Team{R} {GRY}—{R} {WHT}Groq · Together.ai · OpenRouter{R}  {GRY}by Yohn18{R}".format(
    CYN=CYN, B=B, R=R, GRY=GRY, WHT=WHT)

LINE = "{GRY}  {}{R}".format("─" * 60, GRY=GRY, R=R)


def _print_banner():
    os.system("cls" if os.name == "nt" else "clear")
    print(BANNER)
    print(SUBHEADER)
    print(LINE)
    print()


def _load_keys() -> dict:
    cfg_path = os.path.join(_ROOT, "config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        agents_cfg = cfg.get("agents", {})
        return {
            "groq":       agents_cfg.get("groq_key", ""),
            "together":   agents_cfg.get("together_key", ""),
            "openrouter": agents_cfg.get("openrouter_key", ""),
        }
    except Exception:
        return {"groq": "", "together": "", "openrouter": ""}


def _save_keys(keys: dict):
    cfg_path = os.path.join(_ROOT, "config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        if "agents" not in cfg:
            cfg["agents"] = {}
        cfg["agents"]["groq_key"]       = keys.get("groq", "")
        cfg["agents"]["together_key"]   = keys.get("together", "")
        cfg["agents"]["openrouter_key"] = keys.get("openrouter", "")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print("{}Gagal simpan: {}{}".format(RED, e, R))
        return False


def _check_keys(keys: dict) -> bool:
    active = [k for k, v in keys.items() if v]
    if not active:
        return False
    return True


def _setup_keys():
    print("\n{}{}🔑  Setup API Keys{}".format(B, YEL, R))
    print("{} Tekan Enter untuk skip provider yang tidak dipakai.{}".format(GRY, R))
    print()
    keys = _load_keys()
    providers = [
        ("groq",       "Groq",        "https://console.groq.com/keys"),
        ("together",   "Together.ai", "https://api.together.ai/settings/api-keys"),
        ("openrouter", "OpenRouter",  "https://openrouter.ai/keys"),
    ]
    for key_name, label, url in providers:
        current = keys.get(key_name, "")
        masked = ("*" * 8 + current[-4:]) if len(current) > 4 else ("(belum diset)" if not current else current)
        print("  {}{}{} {}[{}]{}".format(B, label, R, GRY, masked, R))
        print("  {}Dapatkan key: {}{}".format(DIM, url, R))
        val = input("  Key baru (Enter skip): ").strip()
        if val:
            keys[key_name] = val
        print()
    if _save_keys(keys):
        print("{}✅  Keys tersimpan!{}".format(GRN, R))
    return keys


def _spinner(stop_event, label=""):
    frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    i = 0
    while not stop_event.is_set():
        print("\r  {}{} {}{}{}".format(CYN, frames[i % len(frames)], GRY, label, R),
              end="", flush=True)
        time.sleep(0.08)
        i += 1
    print("\r" + " " * 60 + "\r", end="", flush=True)


def _run_task(task: str, keys: dict, quick: bool = False, stream: bool = True):
    from modules.agents.team import AgentTeam

    logs = []
    output_started = False

    def log_cb(msg):
        nonlocal output_started
        if not output_started:
            print()
        output_started = True
        print("  {}{}{}".format(GRY, msg, R))

    def stream_cb(chunk):
        pass  # output ditampilkan di hasil akhir

    print("\n{}{}  Task:{} {}{}".format(B, CYN, R, WHT, task[:120]))
    print(LINE)

    stop_spin = threading.Event()
    spin_thread = threading.Thread(
        target=_spinner, args=(stop_spin, "AI Team sedang bekerja..."), daemon=True)
    spin_thread.start()

    start = time.time()
    try:
        team = AgentTeam(keys=keys, log_cb=log_cb)
        if quick:
            result = team.quick(task, max_tokens=1024)
            agents_info = {}
            task_type = "quick"
        else:
            out = team.run(task, max_tokens=2048)
            result = out["result"]
            agents_info = out["agents_used"]
            task_type = out["task_type"]
    except Exception as e:
        stop_spin.set()
        print("\n\n  {}❌  Error: {}{}".format(RED, e, R))
        return
    finally:
        stop_spin.set()

    elapsed = time.time() - start

    # Print hasil
    print()
    print(LINE)
    print("  {}{} HASIL — {} ({:.1f}s){}".format(
        B, GRN, task_type.upper(), elapsed, R))
    print(LINE)
    print()

    # Wrap dan print result
    lines = result.split("\n")
    for line in lines:
        print("  {}".format(line))

    print()
    print(LINE)

    # Print agent info
    if agents_info:
        print("  {}{}Models yang digunakan:{}".format(DIM, GRY, R))
        for name, info in agents_info.items():
            print("  {}  {} · {}{}".format(GRY, name, info.get("model", ""), R))

    print()


def _interactive_mode(keys: dict):
    print("\n  {}{}💬  Mode Interaktif{}".format(B, CYN, R))
    print("  {}Ketik task kamu. Perintah: /quick /history /keys /clear /exit{}".format(
        GRY, R))
    print(LINE)

    from modules.agents.memory import AgentMemory
    mem = AgentMemory()

    while True:
        try:
            print()
            raw = input("  {}❯{} ".format(PRP, R)).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  {}Sampai jumpa!{}".format(GRN, R))
            break

        if not raw:
            continue

        if raw.lower() in ("/exit", "/quit", "exit", "quit"):
            print("\n  {}Sampai jumpa!{}".format(GRN, R))
            break

        elif raw.lower() == "/clear":
            _print_banner()
            print("\n  {}{}💬  Mode Interaktif{}".format(B, CYN, R))
            print("  {}Ketik task kamu. Perintah: /quick /history /keys /clear /exit{}".format(GRY, R))
            print(LINE)
            continue

        elif raw.lower() == "/keys":
            keys = _setup_keys()
            continue

        elif raw.lower() == "/history":
            sessions = mem.get_sessions(limit=8)
            if not sessions:
                print("  {}(belum ada history){}".format(GRY, R))
            else:
                print("\n  {}{}Riwayat Session:{}".format(B, YEL, R))
                for s in sessions:
                    ts = time.strftime("%d/%m %H:%M", time.localtime(s["created"]))
                    task_preview = (s["task"] or "")[:60]
                    status = "✓" if s["finished"] else "…"
                    print("  {} {} {}{}{}".format(
                        GRN if s["finished"] else YEL, status,
                        GRY, "[{}] {}".format(ts, task_preview), R))
            continue

        elif raw.lower().startswith("/quick "):
            task = raw[7:].strip()
            if task:
                _run_task(task, keys, quick=True)
            continue

        elif raw.startswith("/"):
            print("  {}Perintah tidak dikenal. Gunakan /quick /history /keys /clear /exit{}".format(
                YEL, R))
            continue

        _run_task(raw, keys, quick=False)


def main():
    parser = argparse.ArgumentParser(
        description="Synthex AI Team CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("task", nargs="?", help="Task yang ingin dikerjakan")
    parser.add_argument("--quick", "-q", action="store_true",
                        help="Mode cepat (single agent)")
    parser.add_argument("--setup", "-s", action="store_true",
                        help="Setup API keys")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Mode interaktif")
    args = parser.parse_args()

    _print_banner()

    keys = _load_keys()

    if args.setup:
        keys = _setup_keys()
        return

    if not _check_keys(keys):
        print("  {}{}⚠️  Belum ada API key yang diset.{}".format(B, YEL, R))
        print("  {}Jalankan: {}python agent_cli.py --setup{}".format(
            GRY, WHT, R))
        print()
        ans = input("  Setup sekarang? (y/n): ").strip().lower()
        if ans == "y":
            keys = _setup_keys()
        else:
            return

    active = [k for k, v in keys.items() if v]
    print("  {}✅  Provider aktif: {}{}{}".format(
        GRN, WHT, ", ".join(active), R))

    if args.task:
        _run_task(args.task, keys, quick=args.quick)
    else:
        _interactive_mode(keys)


if __name__ == "__main__":
    main()
