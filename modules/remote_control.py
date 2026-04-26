"""
modules/remote_control.py
──────────────────────────
ADB + scrcpy helper layer for the Remote page.

Features
────────
  AdbManager   – wraps adb.exe; connect/disconnect/pair/list devices
  ScrcpyManager – launch/stop scrcpy subprocess for phone mirroring
  NotifReader  – parse `adb shell dumpsys notification` output
"""

import os
import re
import subprocess
import threading
import time
from core.logger import get_logger

logger = get_logger("remote_control")

# ── Locate adb.exe ────────────────────────────────────────────────────────────
def _find_adb() -> str:
    """Return path to adb.exe, or '' if not found."""
    import sys
    # Bundled in tools/platform-tools/ next to exe or project root
    base = (os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.path.join(base, "tools", "platform-tools", "adb.exe"),
        os.path.join(base, "tools", "scrcpy", "adb.exe"),
        os.path.join(base, "tools", "adb.exe"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
        r"C:\Program Files\Android\platform-tools\adb.exe",
        r"C:\Program Files (x86)\Android\platform-tools\adb.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # Check PATH
    try:
        result = subprocess.run(
            ["where", "adb"], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if lines:
                return lines[0]
    except Exception:
        pass
    return ""

def _find_scrcpy() -> str:
    """Return path to scrcpy.exe, or '' if not found."""
    # Check project tools/ folder first
    import sys
    base = (os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local = os.path.join(base, "tools", "scrcpy", "scrcpy.exe")
    if os.path.isfile(local):
        return local
    local2 = os.path.join(base, "tools", "scrcpy.exe")
    if os.path.isfile(local2):
        return local2
    # Check PATH
    try:
        result = subprocess.run(
            ["where", "scrcpy"], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if lines:
                return lines[0]
    except Exception:
        pass
    return ""


class AdbManager:
    """Thin wrapper around adb.exe."""

    SCRCPY_DOWNLOAD_URL = (
        "https://github.com/Genymobile/scrcpy/releases/latest"
    )

    def __init__(self):
        self.adb = _find_adb()
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.adb)

    def _run(self, *args, timeout=8) -> tuple[int, str, str]:
        """Run adb command, return (returncode, stdout, stderr)."""
        if not self.adb:
            return (-1, "", "adb tidak ditemukan")
        try:
            r = subprocess.run(
                [self.adb] + list(args),
                capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            return (r.returncode, r.stdout.strip(), r.stderr.strip())
        except subprocess.TimeoutExpired:
            return (-1, "", "Timeout")
        except Exception as e:
            return (-1, "", str(e))

    def list_devices(self) -> list[dict]:
        """Return list of connected devices as [{"serial":…, "state":…}]."""
        code, out, _ = self._run("devices")
        devices = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                devices.append({"serial": parts[0], "state": parts[1]})
        return devices

    def connect(self, ip: str, port: int = 5555) -> tuple[bool, str]:
        """adb connect IP:PORT → (ok, message)"""
        target = "{}:{}".format(ip.strip(), port)
        code, out, err = self._run("connect", target, timeout=10)
        msg = out or err
        ok  = "connected" in msg.lower() or "already" in msg.lower()
        return (ok, msg)

    def disconnect(self, target: str = "") -> tuple[bool, str]:
        """adb disconnect [target]"""
        args = ["disconnect"] + ([target] if target else [])
        code, out, err = self._run(*args)
        return (code == 0, out or err)

    def pair(self, ip: str, port: int, code: str) -> tuple[bool, str]:
        """adb pair IP:PORT CODE  (Android 11+ wireless pairing)"""
        target = "{}:{}".format(ip.strip(), port)
        rc, out, err = self._run("pair", target, code, timeout=15)
        msg = out or err
        ok  = "successfully" in msg.lower() or rc == 0
        return (ok, msg)

    def tcpip(self, port: int = 5555) -> tuple[bool, str]:
        """adb tcpip PORT — switch device to TCP mode (requires USB first)."""
        rc, out, err = self._run("tcpip", str(port))
        return (rc == 0, out or err)

    def get_device_ip(self) -> str:
        """Return phone's WiFi (wlan0) IP, not USB/tethering IP."""
        # Priority: wlan0 specifically — avoid USB tethering IPs (rndis0, usb0)

        # Method 1: ip addr show wlan0 (most specific)
        _, out1, _ = self._run("shell", "ip", "addr", "show", "wlan0")
        m1 = re.search(r'inet\s+([\d.]+)/', out1)
        if m1 and not m1.group(1).startswith("127."):
            return m1.group(1)

        # Method 2: getprop dhcp.wlan0.ipaddress (MIUI/Samsung friendly)
        for prop in ("dhcp.wlan0.ipaddress", "dhcp.wlan0.result"):
            _, out2, _ = self._run("shell", "getprop", prop)
            out2 = out2.strip()
            if re.match(r'\d+\.\d+\.\d+\.\d+', out2) and not out2.startswith("127."):
                return out2

        # Method 3: ifconfig wlan0
        _, out3, _ = self._run("shell", "ifconfig", "wlan0")
        m3 = re.search(r'inet\s+(?:addr:)?\s*([\d.]+)', out3)
        if m3 and not m3.group(1).startswith("127."):
            return m3.group(1)

        # Method 4: ip -4 addr — filter only wlan lines
        _, out4, _ = self._run("shell", "ip", "-4", "addr")
        in_wlan = False
        for line in out4.splitlines():
            if re.search(r'^\d+:\s+wlan', line):
                in_wlan = True
            elif re.match(r'^\d+:', line):
                in_wlan = False
            if in_wlan:
                m4 = re.search(r'inet\s+([\d.]+)/', line)
                if m4 and not m4.group(1).startswith("127."):
                    return m4.group(1)

        # Method 5: ip route src — last resort, may return USB IP
        _, out5, _ = self._run("shell", "ip", "route")
        for line in out5.splitlines():
            if "wlan" in line:
                m5 = re.search(r'src\s+([\d.]+)', line)
                if m5 and not m5.group(1).startswith("127."):
                    return m5.group(1)

        return ""

    def probe_port(self, ip: str, port: int = 5555, timeout: float = 2.0) -> str:
        """Check if port is reachable. Returns: 'open', 'refused', 'timeout'."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                result = s.connect_ex((ip, port))
                return "open" if result == 0 else "refused"
        except socket.timeout:
            return "timeout"
        except Exception:
            return "timeout"

    # ── Synthex Companion App helpers ─────────────────────────────────────────

    _COMPANION_PKG = "com.yohn18.synthex"

    def is_companion_installed(self, serial: str = "") -> bool:
        """Check if Synthex companion APK is installed on device."""
        s = ["-s", serial] if serial else []
        _, out, _ = self._run(*s, "shell", "pm", "list", "packages",
                              self._COMPANION_PKG)
        return self._COMPANION_PKG in out

    def install_companion(self, apk_path: str,
                          serial: str = "") -> tuple[bool, str]:
        """
        Install Synthex companion APK on device.
        Returns (ok, message).
        """
        if not os.path.isfile(apk_path):
            return (False, "APK tidak ditemukan: {}".format(apk_path))
        s = ["-s", serial] if serial else []
        rc, out, err = self._run(*s, "install", "-r", "-d", apk_path,
                                 timeout=60)
        msg = out or err
        ok  = rc == 0 and ("success" in msg.lower() or not err)
        return (ok, msg)

    def launch_companion(self, serial: str = "") -> tuple[bool, str]:
        """Launch Synthex companion app on device."""
        s = ["-s", serial] if serial else []
        rc, out, err = self._run(
            *s, "shell", "am", "start", "-n",
            "{}/com.yohn18.synthex.MainActivity".format(self._COMPANION_PKG))
        return (rc == 0, out or err)

    def get_companion_apk_path(self) -> str:
        """Return path to bundled Synthex.apk if it exists."""
        base = (os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = [
            os.path.join(base, "tools", "Synthex.apk"),
            os.path.join(base, "assets", "Synthex.apk"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return ""


class NotifReader:
    """Read active Android notifications via adb."""

    def __init__(self, adb_manager: AdbManager):
        self._adb = adb_manager

    def fetch(self) -> list[dict]:
        """
        Return list of notification dicts:
          {"app": str, "title": str, "text": str, "time": str}
        """
        if not self._adb.available:
            return []
        _, out, _ = self._adb._run(
            "shell", "dumpsys", "notification", "--noredact", timeout=10)
        return self._parse(out)

    @staticmethod
    def _parse(raw: str) -> list[dict]:
        notifs = []
        current: dict | None = None
        for line in raw.splitlines():
            s = line.strip()
            # New notification block
            m = re.match(r'NotificationRecord\(.*?pkg=([^\s,]+)', s)
            if m:
                if current:
                    notifs.append(current)
                current = {"app": m.group(1), "title": "", "text": "", "time": ""}
                continue
            if current is None:
                continue
            # Title
            if s.startswith("android.title=") or "extras.title=" in s:
                current["title"] = s.split("=", 1)[-1].strip().strip('"')
            # Text
            elif s.startswith("android.text=") or "extras.text=" in s:
                current["text"] = s.split("=", 1)[-1].strip().strip('"')
            # Time
            elif s.startswith("when="):
                current["time"] = s.split("=", 1)[-1].strip()

        if current:
            notifs.append(current)
        # Filter out empty / system noise
        return [n for n in notifs if n["app"] and (n["title"] or n["text"])][-30:]


class ScrcpyManager:
    """Launch and stop scrcpy for phone mirroring + control."""

    def __init__(self, adb_manager: AdbManager):
        self._adb   = adb_manager
        self._proc  = None
        self._lock  = threading.Lock()
        self.path   = _find_scrcpy()

    @property
    def available(self) -> bool:
        return bool(self.path)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self, serial: str = "",
              max_size: int = 1024,
              bitrate: str = "8M",
              fps: int = 60,
              orientation: str = "Auto",
              stay_awake: bool = True,
              show_touches: bool = False,
              always_on_top: bool = True,
              no_audio: bool = False) -> tuple[bool, str]:
        """
        Launch scrcpy subprocess.
        Returns (ok, message).
        """
        if not self.path:
            return (False, "scrcpy tidak ditemukan. Download di:\n"
                    + AdbManager.SCRCPY_DOWNLOAD_URL)
        if self.running:
            return (False, "scrcpy sudah berjalan.")

        cmd = [self.path,
               "--max-size", str(max_size),
               "--video-bit-rate", bitrate,
               "--max-fps", str(fps),
               "--window-title", "Synthex Mirror"]
        if orientation == "Portrait":
            cmd += ["--lock-video-orientation", "0"]
        elif orientation == "Landscape":
            cmd += ["--lock-video-orientation", "1"]
        if serial:
            cmd += ["--serial", serial]
        if stay_awake:
            cmd.append("--stay-awake")
        if show_touches:
            cmd.append("--show-touches")
        if always_on_top:
            cmd.append("--always-on-top")
        if no_audio:
            cmd.append("--no-audio")

        try:
            with self._lock:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=(subprocess.CREATE_NO_WINDOW
                                   if os.name == "nt" else 0))
            logger.info("scrcpy started: %s", " ".join(cmd))
            return (True, "Mirror dimulai.")
        except Exception as e:
            logger.error("scrcpy start error: %s", e)
            return (False, str(e))

    def stop(self):
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=3)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
            self._proc = None
        logger.info("scrcpy stopped.")

    def poll(self) -> bool:
        """Check if scrcpy process is still alive."""
        with self._lock:
            if self._proc is None:
                return False
            return self._proc.poll() is None
