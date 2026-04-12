# -*- coding: utf-8 -*-
"""
modules/browser/actions.py - Playwright-based browser automation for Synthex.
Playwright must run in a single persistent thread; all calls are dispatched
via a command queue to that thread.
"""

import json
import os
import queue
import threading
import time
import concurrent.futures
from core.config import Config
from core.logger import get_logger


class BrowserActions:
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger("browser")
        self._cmd_queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._started = False
        self._lock = threading.Lock()
        self._recording_events: list = []
        self._recording_active = False
        self._recording_thread: threading.Thread | None = None
        self.shared_store: dict = {}
        self._load_shared_store()
        self._chrome_conflict: bool = False
        self._browser_mode: str = ""   # "profile" | "fresh" | "cdp"
        self._spy_active: bool = False
        self._use_cdp: bool = False     # connect to existing Chrome via CDP

    # -- Browser launcher helper --
    def _launch_browser(self, p, headless: bool = True, slow_mo: int = 50):
        """Return a Playwright Browser (no-profile path: firefox / chromium / chrome fresh)."""
        btype = self.config.get(
            "browser.type",
            self.config.get("browser.browser_type", "chrome"),
        ).lower()
        if btype == "firefox":
            return p.firefox.launch(headless=headless, slow_mo=slow_mo)
        elif btype == "chromium":
            return p.chromium.launch(headless=headless, slow_mo=slow_mo)
        else:
            return p.chromium.launch(channel="chrome", headless=headless, slow_mo=slow_mo)

    def _default_user_data_dir(self) -> str:
        return os.path.join(
            os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data"
        )

    def _check_chrome_running(self) -> bool:
        """Return True if chrome.exe processes are running (would lock the profile)."""
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return "chrome.exe" in result.stdout.lower()
        except Exception:
            return False

    def reconnect_browser(self) -> bool:
        """Clear the conflict flag and restart the browser worker."""
        self._chrome_conflict = False
        self._browser_mode = ""
        self._use_cdp = False
        self.restart_browser()
        return True

    # -- Chrome CDP / remote-debugging helpers --

    def _find_chrome_exe(self) -> str:
        """Return the path to chrome.exe, or empty string if not found."""
        import os as _os
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        local = _os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(_os.path.join(
                local, "Google", "Chrome", "Application", "chrome.exe"))
        for path in candidates:
            if _os.path.exists(path):
                return path
        self.logger.warning(
            "Google Chrome is not installed. Please install Chrome first.")
        return ""

    def _ensure_chrome_debug_port(self, port: int = 9222) -> bool:
        """
        Ensure Chrome is listening on the remote-debugging port.
        If not, launch Chrome with --remote-debugging-port=<port>.
        Returns True when the port is ready.
        """
        import urllib.request as _req
        url = f"http://localhost:{port}/json/version"
        try:
            _req.urlopen(url, timeout=1).read()
            self.logger.info(f"Chrome already listening on debug port {port}.")
            return True
        except Exception:
            pass

        chrome = self._find_chrome_exe()
        if not chrome:
            self.logger.error(
                "Google Chrome is not installed. Please install Chrome first.")
            return False

        import subprocess
        try:
            subprocess.Popen(
                [chrome,
                 f"--remote-debugging-port={port}",
                 "--no-first-run",
                 "--no-default-browser-check"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            self.logger.error(f"Failed to start Chrome with debug port: {e}")
            return False

        for _ in range(15):
            time.sleep(0.5)
            try:
                _req.urlopen(url, timeout=1).read()
                self.logger.info(
                    f"Chrome now listening on debug port {port}.")
                return True
            except Exception:
                pass

        self.logger.error(
            f"Chrome did not open debug port {port} within 7.5 s.")
        return False

    def connect_to_existing_chrome(self,
                                   port: int = 9222) -> bool:
        """
        Connect Synthex to an already-running Chrome session via the
        Chrome DevTools Protocol (CDP).

        If Chrome is not yet running with --remote-debugging-port, this
        method launches it automatically.  Once the port is available,
        the browser worker is restarted and will attach via CDP so that
        the user's normal Chrome window remains open and usable while
        Synthex drives it.

        Returns True if the connection was set up successfully.
        """
        self.config.set("browser.cdp_port", port)
        if not self._ensure_chrome_debug_port(port):
            return False
        self._use_cdp = True        # worker reads this flag on next start
        self.restart_browser()
        self.logger.info(
            f"Browser worker will connect via CDP on port {port}.")
        return True

    # -- Shared data store --
    def _shared_store_path(self) -> str:
        return os.path.join(
            self.config.get("macro.save_path", "C:/Users/Admin/synthex/macros"),
            "shared_data.json",
        )

    def _load_shared_store(self):
        path = self._shared_store_path()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.shared_store.update(json.load(f))
                self.logger.info(f"Shared store loaded ({len(self.shared_store)} keys).")
            except Exception as e:
                self.logger.warning(f"Could not load shared store: {e}")

    def _save_shared_store(self):
        path = self._shared_store_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.shared_store, f, indent=2)

    def set_shared_data(self, key: str, value) -> None:
        """Store a value in the shared store and persist it to disk."""
        self.shared_store[key] = value
        self._save_shared_store()
        self.logger.info(f"Shared store: set {key!r}")

    def get_shared_data(self, key: str, default=None):
        """Retrieve a value from the shared store."""
        return self.shared_store.get(key, default)

    def switch_browser(self, browser_type: str) -> None:
        """Save shared store, update config, and restart with the new browser type."""
        self._save_shared_store()
        self.config.set("browser.type", browser_type.lower())
        self.config.save()
        self.restart_browser()
        self.logger.info(f"Switched to {browser_type}  -  shared data preserved on disk.")

    def restart_browser(self):
        """Shut down the running browser worker; next action starts a fresh one."""
        if self._started and self._thread and self._thread.is_alive():
            fut: concurrent.futures.Future = concurrent.futures.Future()
            self._cmd_queue.put((None, (), {}, fut))
        with self._lock:
            self._started = False
            self._thread = None
        self.logger.info("Browser worker stopped  -  will restart on next action.")

    # -- Playwright worker (runs entirely in one dedicated thread) --
    def _worker(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            btype       = self.config.get(
                "browser.type",
                self.config.get("browser.browser_type", "chrome")).lower()
            headless    = self.config.get("browser.headless", True)
            slow_mo     = self.config.get("browser.slow_mo", 50)
            use_profile = self.config.get("browser.use_profile", True)
            context     = None
            browser     = None

            # --- CDP mode: attach to existing Chrome via remote debugging ---
            if self._use_cdp:
                port    = self.config.get("browser.cdp_port", 9222)
                cdp_url = f"http://localhost:{port}"
                try:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    contexts = browser.contexts
                    context  = contexts[0] if contexts else browser.new_context()
                    self._browser_mode = "cdp"
                    self.logger.info(
                        f"Attached to existing Chrome via CDP at {cdp_url}.")
                except Exception as cdp_err:
                    self.logger.error(
                        f"CDP connection failed ({cdp_err}). "
                        "Falling back to fresh Chrome.")
                    self._use_cdp = False
                    try:
                        browser  = p.chromium.launch(
                            channel="chrome",
                            headless=False,
                            slow_mo=slow_mo)
                        context  = browser.new_context()
                        self._browser_mode = "fresh"
                    except Exception as fb_err:
                        self.logger.error(
                            f"Fresh Chrome fallback also failed: {fb_err}")
                        return

            # --- Chrome profile mode ---
            elif btype == "chrome" and use_profile:
                udd = (self.config.get("browser.user_data_dir", "")
                       or self._default_user_data_dir())
                profile_dir = self.config.get(
                    "browser.profile_path", "Default")

                if not os.path.exists(udd):
                    self.logger.warning(
                        f"Chrome user-data dir not found: {udd!r}. "
                        "Falling back to fresh Chrome instance.")
                    try:
                        browser  = self._launch_browser(
                            p, headless=headless, slow_mo=slow_mo)
                        context  = browser.new_context()
                        self._browser_mode = "fresh"
                        self.logger.info("Fresh browser launched (no profile).")
                    except Exception as e:
                        self.logger.error(f"Browser launch failed: {e}")
                        return
                else:
                    try:
                        context = p.chromium.launch_persistent_context(
                            udd,
                            channel="chrome",
                            headless=headless,
                            slow_mo=slow_mo,
                            args=[
                                f"--profile-directory={profile_dir}",
                                "--no-first-run",
                                "--no-default-browser-check",
                            ],
                        )
                        self._chrome_conflict = False
                        self._browser_mode = "profile"
                        self.logger.info(
                            f"Chrome launched with profile: {profile_dir}")
                    except Exception as exc:
                        msg = str(exc).lower()
                        is_locked = (
                            "user data directory" in msg
                            or "already running" in msg
                            or "in use" in msg
                            or "lock" in msg)
                        if is_locked:
                            self.logger.warning(
                                "Chrome profile is busy. "
                                "Synthex will use a fresh window instead.")
                            # Try CDP connect before falling back to fresh
                            try:
                                import urllib.request as _req
                                _req.urlopen(
                                    "http://localhost:9222/json/version",
                                    timeout=1).read()
                                browser = p.chromium.connect_over_cdp(
                                    "http://localhost:9222")
                                contexts = browser.contexts
                                context  = (contexts[0]
                                            if contexts
                                            else browser.new_context())
                                self._browser_mode = "cdp"
                                self.logger.info(
                                    "Connected to running Chrome via CDP.")
                            except Exception:
                                # CDP not available - launch fresh instance
                                self.logger.info(
                                    "CDP unavailable. Launching fresh "
                                    "Chrome alongside existing instance.")
                                try:
                                    browser = p.chromium.launch(
                                        channel="chrome",
                                        headless=headless,
                                        slow_mo=slow_mo)
                                    context = browser.new_context(
                                        user_agent=self.config.get(
                                            "browser.user_agent") or None)
                                    self._browser_mode = "fresh"
                                    self.logger.info(
                                        "Fresh Chrome window launched.")
                                except Exception as exc2:
                                    self.logger.error(
                                        "Could not start Chrome. "
                                        "Try closing Chrome and reopening "
                                        "Synthex, or click 'Connect Browser'.")
                                    return
                        else:
                            self.logger.error(
                                "Could not start Chrome. "
                                "Make sure Google Chrome is installed.")
                            return

            # --- Other browser types (firefox / chromium) ---
            else:
                try:
                    browser = self._launch_browser(
                        p, headless=headless, slow_mo=slow_mo)
                    context = browser.new_context(
                        user_agent=self.config.get(
                            "browser.user_agent") or None)
                    self._browser_mode = "fresh"
                    self.logger.info(
                        f"Browser launched: {btype} (fresh, no profile)")
                except Exception as e:
                    self.logger.error(
                        f"Failed to launch {btype}: {e}. "
                        "Check that the browser is installed.")
                    return

            page = (context.pages[0]
                    if context.pages else context.new_page())
            page.set_default_timeout(
                self.config.get("browser.timeout", 30000))

            while True:
                cmd, args, kwargs, fut = self._cmd_queue.get()
                if cmd is None:
                    break
                try:
                    fut.set_result(cmd(page, *args, **kwargs))
                except Exception as exc:
                    fut.set_exception(exc)

            try:
                if self._browser_mode == "cdp" and browser:
                    browser.disconnect()
                else:
                    context.close()
            except Exception:
                pass
            self.logger.info("Browser worker stopped.")

    def _ensure_started(self):
        with self._lock:
            if not self._started:
                self._thread = threading.Thread(
                    target=self._worker, daemon=True, name="playwright-worker"
                )
                self._thread.start()
                self._started = True

    def _dispatch(self, fn, *args, timeout: float = 60, **kwargs):
        """Send a callable to the Playwright thread and block until done."""
        self._ensure_started()
        # Give the worker thread a moment to set _chrome_conflict if it failed instantly
        if self._thread and not self._thread.is_alive():
            raise RuntimeError(
                "Chrome is not connected. Click 'Connect Browser' to start.")
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._cmd_queue.put((fn, args, kwargs, fut))
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                "Action took too long. The website may be slow or the element "
                "was not found.")
        except Exception as exc:
            # Re-raise with a friendly message where possible
            msg = str(exc).lower()
            if ("net::err_name_not_resolved" in msg
                    or "name_not_resolved" in msg):
                raise RuntimeError(
                    "Website not found. Check that the URL is correct "
                    "and you are online.") from exc
            if ("net::err_connection_refused" in msg
                    or "connection refused" in msg):
                raise RuntimeError(
                    "Could not reach the website. It may be down or the URL "
                    "may be wrong.") from exc
            if ("waiting for selector" in msg
                    or "element not found" in msg
                    or "no element matches" in msg
                    or "strict mode violation" in msg):
                raise RuntimeError(
                    "Could not find the element on the page. The website may "
                    "have changed.") from exc
            raise

    # -- Public API --
    def navigate(self, url: str) -> str:
        """Navigate to url, return page title."""
        def _nav(page, url):
            self.logger.info(f"Navigating to: {url}")
            page.goto(url)
            return page.title()
        title = self._dispatch(_nav, url, timeout=60)
        self.shared_store["last_url"] = url
        return title

    def get_text(self, selector: str) -> str:
        def _get(page, selector):
            return page.inner_text(selector)
        text = self._dispatch(_get, selector, timeout=30)
        self.shared_store["last_extracted"] = text
        return text

    def click(self, selector: str):
        def _click(page, selector):
            page.click(selector)
        self._dispatch(_click, selector, timeout=30)

    def type_text(self, selector: str, text: str):
        def _type(page, selector, text):
            page.fill(selector, text)
        self._dispatch(_type, selector, text, timeout=30)

    def screenshot(self, path: str):
        def _shot(page, path):
            page.screenshot(path=path)
        self._dispatch(_shot, path, timeout=30)

    def wait_for(self, selector: str, timeout: int = None):
        ms = timeout or self.config.get("browser.timeout", 30000)
        def _wait(page, selector, ms):
            page.wait_for_selector(selector, timeout=ms)
        self._dispatch(_wait, selector, ms, timeout=ms / 1000 + 10)

    def get_all_text(self) -> str:
        """Return all visible text on the current page."""
        def _all(page):
            return page.inner_text("body")
        return self._dispatch(_all, timeout=30)

    def query_elements(self, list_selector: str, field_selectors: dict) -> list:
        """Query all elements matching list_selector and extract sub-fields.

        Args:
            list_selector: CSS selector for the repeating container elements.
            field_selectors: mapping of field_name -> child CSS selector.

        Returns:
            List of dicts {field_name: extracted_text, ...}.
        """
        def _query(page, list_sel, fields):
            results = []
            try:
                elements = page.query_selector_all(list_sel)
            except Exception:
                return results
            for el in elements:
                row = {}
                for field_name, sub_sel in fields.items():
                    try:
                        sub = el.query_selector(sub_sel) if sub_sel else None
                        row[field_name] = sub.inner_text().strip() if sub else ""
                    except Exception:
                        row[field_name] = ""
                results.append(row)
            return results

        return self._dispatch(_query, list_selector, field_selectors, timeout=30)

    def find_and_click(self, description: str) -> str:
        """Find an element by text, aria-label, placeholder, role, or CSS selector and click it."""
        def _find_click(page, description):
            # 1. CSS selector
            try:
                if page.is_visible(description, timeout=1000):
                    page.click(description)
                    return f"Clicked via CSS selector: {description}"
            except Exception:
                pass
            # 2. Visible text
            try:
                loc = page.get_by_text(description, exact=False)
                if loc.count() > 0:
                    loc.first.click()
                    return f"Clicked via text: {description}"
            except Exception:
                pass
            # 3. ARIA label
            try:
                loc = page.get_by_label(description)
                if loc.count() > 0:
                    loc.first.click()
                    return f"Clicked via aria-label: {description}"
            except Exception:
                pass
            # 4. Placeholder
            try:
                loc = page.get_by_placeholder(description)
                if loc.count() > 0:
                    loc.first.click()
                    return f"Clicked via placeholder: {description}"
            except Exception:
                pass
            # 5. Button role / name
            try:
                loc = page.get_by_role("button", name=description)
                if loc.count() > 0:
                    loc.first.click()
                    return f"Clicked via button role: {description}"
            except Exception:
                pass
            raise ValueError(f"No element found matching: {description}")

        return self._dispatch(_find_click, description, timeout=30)

    def click_coordinates(self, x: int, y: int):
        """Click at exact pixel coordinates on the current page."""
        def _click_xy(page, x, y):
            page.mouse.click(x, y)
        self._dispatch(_click_xy, x, y, timeout=15)

    # -- Browser recording --
    def get_active_page(self) -> dict:
        """Return the current page's URL and title (empty dict if browser not started)."""
        def _info(page):
            return {"url": page.url, "title": page.title()}
        try:
            return self._dispatch(_info, timeout=5)
        except Exception:
            return {"url": "", "title": ""}

    def get_profile_email(self) -> str:
        """Read the Gmail address from the active Chrome profile Preferences file."""
        try:
            udd = self.config.get("browser.user_data_dir", "") or self._default_user_data_dir()
            profile = self.config.get("browser.profile_path", "Default")
            prefs = os.path.join(udd, profile, "Preferences")
            if not os.path.exists(prefs):
                return ""
            with open(prefs, encoding="utf-8", errors="ignore") as f:
                import json as _json
                data = _json.load(f)
            accounts = data.get("account_info", [])
            emails = [a.get("email", "") for a in accounts if a.get("email")]
            return emails[0] if emails else ""
        except Exception:
            return ""

    # -- Recording --
    _JS_CAPTURE = """
    window.__sx_events = window.__sx_events || [];
    document.addEventListener('click', function(e) {
        var el = e.target;
        var sel = el.tagName.toLowerCase();
        if (el.id)        sel += '#' + el.id;
        if (el.name)      sel += '[name="' + el.name + '"]';
        window.__sx_events.push({
            type: 'click', x: e.clientX, y: e.clientY,
            selector: sel, text: (el.innerText || '').slice(0, 80)
        });
    }, true);
    document.addEventListener('change', function(e) {
        var el = e.target;
        var sel = el.tagName.toLowerCase();
        if (el.id)    sel += '#' + el.id;
        if (el.name)  sel += '[name="' + el.name + '"]';
        window.__sx_events.push({
            type: 'fill', x: 0, y: 0,
            selector: sel, value: el.value || ''
        });
    }, true);
    """

    def start_browser_recording(self):
        """Launch a visible browser window (with Chrome profile if configured) and record actions."""
        # If the main worker is running with the profile, stop it first so
        # the profile directory is not locked when the recorder opens it.
        use_profile = self.config.get("browser.use_profile", True)
        btype = self.config.get("browser.type", "chrome").lower()
        if use_profile and btype == "chrome" and self._started:
            self.logger.info("Stopping main browser worker so recording can use Chrome profile.")
            self.restart_browser()
            time.sleep(1.0)

        self._recording_events = []
        self._recording_active = True
        self._recording_thread = threading.Thread(
            target=self._recording_worker, daemon=True, name="playwright-recorder"
        )
        self._recording_thread.start()
        self.logger.info("Browser recording started.")

    def _recording_worker(self):
        from playwright.sync_api import sync_playwright
        use_profile = self.config.get("browser.use_profile", True)
        btype = self.config.get("browser.type", "chrome").lower()

        with sync_playwright() as p:
            context = None
            browser  = None

            if btype == "chrome" and use_profile:
                udd = (self.config.get("browser.user_data_dir", "")
                       or self._default_user_data_dir())
                profile_dir = self.config.get("browser.profile_path", "Default")

                try:
                    context = p.chromium.launch_persistent_context(
                        udd,
                        channel="chrome",
                        headless=False,
                        slow_mo=50,
                        args=[
                            f"--profile-directory={profile_dir}",
                            "--no-first-run",
                            "--no-default-browser-check",
                        ],
                    )
                    self.logger.info(f"Recording with Chrome profile: {profile_dir}")
                except Exception as exc:
                    msg = str(exc).lower()
                    if "user data directory" in msg or "already running" in msg or "in use" in msg:
                        self.logger.info(
                            "Profile locked  -  recording with fresh Chrome window."
                        )
                        try:
                            browser = p.chromium.launch(channel="chrome", headless=False, slow_mo=50)
                            context = browser.new_context()
                            self.logger.info("Recording with fresh Chrome window (profile in use).")
                        except Exception as exc2:
                            self.logger.error(f"Could not launch Chrome for recording: {exc2}")
                            self._recording_active = False
                            return
                    else:
                        self.logger.error(f"Could not open Chrome for recording: {exc}")
                        self._recording_active = False
                        return
            else:
                browser = self._launch_browser(p, headless=False, slow_mo=50)
                context = browser.new_context()
                self.logger.info("Recording with fresh browser (no profile).")

            page = context.new_page() if not context.pages else context.pages[0]
            page.add_init_script(self._JS_CAPTURE)

            last_url = ""
            start_url = self.config.get("browser.target_url", "https://example.com")
            try:
                page.goto(start_url)
                self._recording_events.append(
                    {"type": "navigate", "url": start_url, "timestamp": time.time()}
                )
            except Exception:
                pass

            while self._recording_active:
                try:
                    current_url = page.url
                    if current_url != last_url:
                        if last_url:
                            self._recording_events.append(
                                {"type": "navigate", "url": current_url,
                                 "timestamp": time.time()}
                            )
                        last_url = current_url

                    events = page.evaluate(
                        "() => { var evs = window.__sx_events || []; "
                        "window.__sx_events = []; return evs; }"
                    )
                    for ev in events:
                        ev["timestamp"] = time.time()
                        self._recording_events.append(ev)
                except Exception:
                    pass
                time.sleep(0.4)

            try:
                context.close()
            except Exception:
                pass
        self.logger.info(
            f"Recording worker stopped ({len(self._recording_events)} events)."
        )

    def stop_browser_recording(self) -> int:
        """Stop recording and save sequence to macros/browser_sequence.json."""
        self._recording_active = False
        if self._recording_thread:
            self._recording_thread.join(timeout=6)
        save_path = os.path.join(
            self.config.get("macro.save_path", "C:/Users/Admin/synthex/macros"),
            "browser_sequence.json",
        )
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self._recording_events, f, indent=2)
        count = len(self._recording_events)
        self.logger.info(f"Browser sequence saved: {count} events -> {save_path}")
        return count

    def replay_browser_actions(self) -> int:
        """Replay macros/browser_sequence.json headlessly via the main browser."""
        save_path = os.path.join(
            self.config.get("macro.save_path", "C:/Users/Admin/synthex/macros"),
            "browser_sequence.json",
        )
        with open(save_path, encoding="utf-8") as f:
            events = json.load(f)

        def _replay(page, events):
            for ev in events:
                try:
                    if ev["type"] == "navigate":
                        page.goto(ev["url"])
                    elif ev["type"] == "click":
                        sel = ev.get("selector", "")
                        try:
                            page.click(sel, timeout=3000)
                        except Exception:
                            page.mouse.click(ev.get("x", 0), ev.get("y", 0))
                    elif ev["type"] == "fill":
                        sel = ev.get("selector", "")
                        if sel and ev.get("value") is not None:
                            try:
                                page.fill(sel, ev["value"])
                            except Exception:
                                pass
                except Exception as exc:
                    self.logger.warning(f"Replay skip: {exc}")
            return len(events)

        return self._dispatch(_replay, events, timeout=300)

    def get_recording_events(self) -> list:
        """Return a copy of the last recording's events."""
        return list(self._recording_events)

    # -- Sequence runner --
    def run_sequence(self, steps: list, on_step=None, sheets_write=None) -> list:
        """Execute a list of step dicts in order.

        Each step: {"type": str, "value": str}
        on_step(index, success: bool, message: str) called after each step.
        sheets_write(sheet_id, row_list) called for Save to Sheets steps.
        Stops at the first failed step.
        Returns list of result dicts.
        """
        results = []
        extracted: list = []   # accumulated by Extract Text steps

        for i, step in enumerate(steps):
            stype = step.get("type", "")
            value = step.get("value", "")
            try:
                msg = self._execute_step(stype, value, extracted, sheets_write)
                results.append({"index": i, "success": True, "message": msg})
                if on_step:
                    on_step(i, True, msg)
            except Exception as exc:
                err = str(exc)
                results.append({"index": i, "success": False, "message": err})
                if on_step:
                    on_step(i, False, err)
                self.logger.error(f"Sequence stopped at step {i + 1} ({stype}): {err}")
                break

        return results

    def _execute_step(self, stype: str, value: str, extracted: list, sheets_write) -> str:
        if stype == "Open URL":
            if not value.startswith(("http://", "https://")):
                value = "https://" + value
            title = self.navigate(value)
            return f"Navigated -> {title}"

        elif stype == "Click Element":
            return self.find_and_click(value)

        elif stype == "Click XY":
            parts = [p.strip() for p in value.split(",")]
            x, y = int(parts[0]), int(parts[1])
            self.click_coordinates(x, y)
            return f"Clicked ({x}, {y})"

        elif stype == "Type Text":
            if "|" not in value:
                raise ValueError("Format: 'selector | text'")
            sel, text = value.split("|", 1)
            self.type_text(sel.strip(), text.strip())
            return f"Typed into {sel.strip()!r}"

        elif stype == "Wait":
            seconds = float(value)
            time.sleep(seconds)
            return f"Waited {seconds}s"

        elif stype == "Extract Text":
            text = self.get_text(value)
            extracted.append(text)
            preview = text[:50].replace("\n", " ")
            return f"Got: {preview!r}"

        elif stype == "Save to Sheets":
            if not sheets_write:
                raise ValueError("No Sheets connection  -  set Sheet ID in Settings")
            row = extracted[:] if extracted else [value]
            sheets_write(value, row)
            return f"Saved {len(row)} value(s) to sheet"

        elif stype == "Take Screenshot":
            import datetime
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            screenshot_dir = self.config.get(
                "vision.screenshot_dir", "C:/Users/Admin/synthex/screenshots"
            )
            path = value if value else os.path.join(screenshot_dir, f"screenshot_{ts}.png")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            self.screenshot(path)
            return f"Saved: {os.path.basename(path)}"

        elif stype == "Press Key":
            def _press(page, k):
                page.keyboard.press(k)
            self._dispatch(_press, value, timeout=10)
            return f"Pressed: {value}"

        elif stype == "Save Data":
            # value: "key=literal_value"  or just "key" (saves last_extracted)
            if "=" in value:
                key, val = value.split("=", 1)
                self.set_shared_data(key.strip(), val.strip())
                return f"Saved {key.strip()!r} = {val.strip()[:40]!r}"
            else:
                last = self.shared_store.get("last_extracted", "")
                self.set_shared_data(value.strip(), last)
                return f"Saved last_extracted as {value.strip()!r}"

        elif stype == "Use Saved Data":
            # value: "data_key | css_selector"
            if "|" not in value:
                raise ValueError("Format: 'data_key | selector'")
            key, sel = value.split("|", 1)
            data = self.get_shared_data(key.strip())
            if data is None:
                raise ValueError(f"No shared data for key {key.strip()!r}")
            self.type_text(sel.strip(), str(data))
            return f"Typed shared {key.strip()!r} into {sel.strip()!r}"

        elif stype == "Scroll":
            parts = [p.strip() for p in value.split(",")]
            dx = int(parts[0]) if len(parts) > 1 else 0
            dy = int(parts[-1])
            def _scroll(page, dx, dy):
                page.mouse.wheel(dx, dy)
            self._dispatch(_scroll, dx, dy, timeout=10)
            return f"Scrolled ({dx}, {dy})"

        else:
            raise ValueError(f"Unknown step type: {stype!r}")

    # -- Spy mode --
    _JS_SPY = r"""
(function() {
    var tip = document.getElementById('__sx_tip');
    if (!tip) {
        tip = document.createElement('div');
        tip.id = '__sx_tip';
        tip.style.cssText = 'position:fixed;z-index:999999;background:#1a1a2e;color:#e0dfff;'
            + 'padding:8px 12px;border-radius:6px;font-size:12px;font-family:monospace;'
            + 'pointer-events:none;max-width:320px;box-shadow:0 2px 8px rgba(0,0,0,0.6);'
            + 'border:1px solid #6C63FF;display:none;line-height:1.55;';
        document.body.appendChild(tip);
    }

    function getXPath(el) {
        if (el.id) return '//*[@id="' + el.id + '"]';
        var parts = [], cur = el;
        while (cur && cur.nodeType === 1) {
            var idx = 1, sib = cur.previousSibling;
            while (sib) {
                if (sib.nodeType === 1 && sib.tagName === cur.tagName) idx++;
                sib = sib.previousSibling;
            }
            parts.unshift(cur.tagName.toLowerCase() + (idx > 1 ? '[' + idx + ']' : ''));
            cur = cur.parentNode;
        }
        return '/' + parts.join('/');
    }

    function getCSSSelector(el) {
        if (el.id) return '#' + el.id;
        var sel = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string' && el.className.trim()) {
            var cls = el.className.trim().split(/\s+/)[0];
            if (cls) sel += '.' + cls;
        }
        if (el.getAttribute && el.getAttribute('name'))
            sel += '[name="' + el.getAttribute('name') + '"]';
        return sel;
    }

    function elInfo(el, ex, ey) {
        var css = getCSSSelector(el);
        var xpath = getXPath(el);
        var tag = el.tagName.toLowerCase();
        var txt = (el.innerText || el.value || el.textContent || '').trim().slice(0, 100);
        return {
            tagName: tag, text: txt,
            id: el.id || '',
            className: (typeof el.className === 'string' ? el.className : '') || '',
            value: el.value || '',
            x: ex, y: ey,
            selector: css, css_selector: css, xpath: xpath,
            position: {x: ex, y: ey}
        };
    }

    if (typeof window.__sx_spy === 'undefined') {
        window.__sx_spy = {tagName:'',text:'',id:'',className:'',value:'',
            x:0,y:0,selector:'',css_selector:'',xpath:'',position:{x:0,y:0}};
    }
    window.__sx_spy_clicked = window.__sx_spy_clicked || null;

    if (!window.__sx_spy_listener) {
        window.__sx_spy_listener = true;

        document.addEventListener('mouseover', function(e) {
            var el = e.target;
            if (el.id === '__sx_tip') return;
            if (window.__sx_last_el && window.__sx_last_el !== el) {
                window.__sx_last_el.style.outline = window.__sx_last_outline || '';
            }
            window.__sx_last_el = el;
            window.__sx_last_outline = el.style.outline;
            el.style.outline = '2px solid #6C63FF';
            var info = elInfo(el, e.clientX, e.clientY);
            window.__sx_spy = info;
            var html = '<b>' + info.tagName.toUpperCase() + '</b>'
                + (info.id ? '<br>ID: ' + info.id : '')
                + (info.className.trim() ? '<br>Class: '
                    + info.className.trim().split(/\s+/).slice(0,2).join(' ') : '')
                + (info.text ? '<br>Teks: ' + info.text.slice(0,50) : '')
                + (info.value ? '<br>Nilai: ' + String(info.value).slice(0,40) : '')
                + '<br>CSS: ' + info.css_selector;
            tip.innerHTML = html;
            tip.style.display = 'block';
            tip.style.left = (e.clientX + 16) + 'px';
            tip.style.top  = (e.clientY + 16) + 'px';
        }, true);

        document.addEventListener('mousemove', function(e) {
            if (tip.style.display !== 'none') {
                tip.style.left = (e.clientX + 16) + 'px';
                tip.style.top  = (e.clientY + 16) + 'px';
            }
        }, true);

        document.addEventListener('mouseout', function(e) {
            if (e.target.id !== '__sx_tip') tip.style.display = 'none';
        }, true);

        document.addEventListener('click', function(e) {
            var el = e.target;
            if (el.id === '__sx_tip') return;
            window.__sx_spy_clicked = elInfo(el, e.clientX, e.clientY);
        }, true);
    }
})();
"""

    _JS_SPY_REMOVE = r"""
(function() {
    var tip = document.getElementById('__sx_tip');
    if (tip && tip.parentNode) tip.parentNode.removeChild(tip);
    if (window.__sx_last_el) {
        window.__sx_last_el.style.outline = window.__sx_last_outline || '';
        window.__sx_last_el = null;
    }
    window.__sx_spy = {};
    window.__sx_spy_clicked = null;
    window.__sx_spy_listener = false;
})();
"""

    def inject_spy_overlay(self) -> None:
        """Inject the interactive spy overlay (hover highlight + tooltip + click capture)."""
        def _inject(page):
            try:
                page.evaluate(self._JS_SPY)
            except Exception:
                pass
        try:
            self._dispatch(_inject, timeout=10)
            self._spy_active = True
            self.logger.info("Spy overlay injected.")
        except Exception as e:
            self.logger.warning(f"inject_spy_overlay failed: {e}")

    def remove_spy_overlay(self) -> None:
        """Remove the spy overlay from the active page and restore element styles."""
        def _remove(page):
            try:
                page.evaluate(self._JS_SPY_REMOVE)
            except Exception:
                pass
        try:
            self._dispatch(_remove, timeout=10)
        except Exception:
            pass
        self._spy_active = False
        self.logger.info("Spy overlay removed.")

    def start_spy_mode(self):
        """Inject element-hover spy script into the active page."""
        self.inject_spy_overlay()

    def get_spy_element(self) -> dict:
        """Return info about the element the user is hovering over."""
        if not self._started or not self._spy_active:
            return {}
        def _eval(page):
            return page.evaluate("() => window.__sx_spy || {}") or {}
        try:
            return self._dispatch(_eval, timeout=2)
        except Exception:
            return {}

    def get_element_info(self) -> dict:
        """Return info about the element currently hovered (alias for get_spy_element)."""
        return self.get_spy_element()

    def get_clicked_element(self) -> dict:
        """Return info about the last element clicked while spy overlay is active."""
        if not self._started or not self._spy_active:
            return {}
        def _eval(page):
            return page.evaluate("() => window.__sx_spy_clicked || {}") or {}
        try:
            return self._dispatch(_eval, timeout=2)
        except Exception:
            return {}

    def stop_spy_mode(self):
        """Deactivate spy mode and remove the overlay."""
        self.remove_spy_overlay()

    def get_page_url(self) -> str:
        """Return the current page URL."""
        def _url(page):
            return page.url
        try:
            return self._dispatch(_url, timeout=5)
        except Exception:
            return ""

    def close(self):
        if self._started and self._thread and self._thread.is_alive():
            fut: concurrent.futures.Future = concurrent.futures.Future()
            self._cmd_queue.put((None, (), {}, fut))
        self.logger.info("Browser close requested.")
