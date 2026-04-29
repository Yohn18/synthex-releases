# -*- coding: utf-8 -*-
"""
modules/macro/smart_macro.py - Smart Macro task executor for Synthex.
Executes structured task steps using Playwright browser + Google Sheets.
"""

import csv
import os
import re
import time
from datetime import datetime
from core.logger import get_logger


class StopTaskException(Exception):
    """Raised by logic steps to stop task execution gracefully."""
    pass


class SmartMacro:
    def __init__(self, engine=None, notify_callback=None):
        self.engine = engine
        self.logger = get_logger("smart_macro")
        self._notify_cb = notify_callback
        self._last_validation_result = None   # set by validate_and_confirm_orders

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def run_task(self, task: dict, progress_cb=None, step_callback=None,
                 dry_run=False, stop_flag=None, enable_retry: bool = False) -> list:
        """Execute a smart macro task. Returns list of per-step result dicts.

        Args:
            task:          Task dict with 'steps' list.
            progress_cb:   Called before each step: (step_idx, total, step_type).
            step_callback: Called after each step: (step_num, result, ok).
            dry_run:       If True, sheet write operations are simulated (not executed).
            stop_flag:     threading.Event; when set, execution stops after current step.
            enable_retry:  If True, retry up to max_retries times on failure (for
                           scheduled/automated runs). Defaults to False for manual UI runs.
        """
        max_retries = task.get("max_retries", 3) if enable_retry else 0
        retry_delay = task.get("retry_delay", 300)   # seconds between retries
        name = task.get("name", "?")
        last_results: list = []

        for attempt in range(max_retries + 1):
            if attempt > 0:
                self.logger.info(
                    "Retry %d/%d for task '%s' — waiting %ds...",
                    attempt, max_retries, name, retry_delay)
                elapsed = 0
                while elapsed < retry_delay:
                    if stop_flag and stop_flag.is_set():
                        return last_results
                    time.sleep(1)
                    elapsed += 1

            last_results = self._execute_task_steps(
                task, progress_cb, step_callback, dry_run, stop_flag)

            if stop_flag and stop_flag.is_set():
                return last_results

            all_ok = all(r.get("ok") for r in last_results) if last_results else False
            if all_ok:
                return last_results

            if attempt < max_retries:
                self.logger.warning(
                    "Task '%s' failed (attempt %d/%d). Will retry in %ds.",
                    name, attempt + 1, max_retries + 1, retry_delay)
            else:
                self.logger.error(
                    "Task '%s' failed after %d retries. Marking as Error.", name, max_retries)
                self.notify(
                    "Task '{}' failed after {} retries.".format(name, max_retries))

        return last_results

    def _execute_task_steps(self, task: dict, progress_cb=None, step_callback=None,
                            dry_run=False, stop_flag=None) -> list:
        """Run all steps in a task once. Returns list of per-step result dicts."""
        steps = task.get("steps", [])
        variables = {
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_date": datetime.now().strftime("%Y-%m-%d"),
        }
        results = []

        for i, step in enumerate(steps):
            if stop_flag and stop_flag.is_set():
                self.logger.info("Task stopped by user at step %d", i + 1)
                break

            step_type = step.get("type", "")
            resolved = self._resolve_vars(step, variables)

            if progress_cb:
                progress_cb(i, len(steps), step_type)

            try:
                if dry_run and step_type == "sheet_write_cell":
                    result = (
                        "[DRY RUN] Would write '{}' to {}!{}".format(
                            resolved.get("value", ""),
                            resolved.get("sheet", ""),
                            resolved.get("cell", ""),
                        )
                    )
                    ok = True
                elif dry_run and step_type == "sheet_append_row":
                    result = "[DRY RUN] Would append row to {}: {}".format(
                        resolved.get("sheet", ""), resolved.get("values", []))
                    ok = True
                else:
                    result = self._execute_step(resolved, variables)
                    ok = True
                results.append({"step": i, "type": step_type, "ok": ok, "result": result})
                self.logger.info("Step %d (%s): OK  %s", i + 1, step_type, result)
            except StopTaskException as e:
                self.logger.info("Task stopped at step %d: %s", i + 1, e)
                results.append({"step": i, "type": step_type, "ok": True, "result": "Stopped: {}".format(e)})
                if step_callback:
                    step_callback(i, "Stopped: {}".format(e), True)
                break
            except Exception as e:
                self.logger.error("Step %d (%s) failed: %s", i + 1, step_type, e)
                results.append({"step": i, "type": step_type, "ok": False, "result": str(e)})
                ok = False
                result = str(e)

            if step_callback:
                step_callback(i, results[-1]["result"], results[-1]["ok"])

        return results

    def run_single_step(self, step: dict, variables: dict = None) -> dict:
        """Run a single step in isolation. Returns {'ok': bool, 'result': str}."""
        if variables is None:
            variables = {
                "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "current_date": datetime.now().strftime("%Y-%m-%d"),
            }
        resolved = self._resolve_vars(step, variables)
        try:
            result = self._execute_step(resolved, variables)
            return {"ok": True, "result": result}
        except StopTaskException as e:
            return {"ok": True, "result": f"Stopped: {e}"}
        except Exception as e:
            self.logger.error(f"Single step ({step.get('type','?')}) failed: {e}")
            return {"ok": False, "result": str(e)}

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _resolve_vars(self, step: dict, variables: dict) -> dict:
        """Replace {var_name} placeholders with current variable values."""
        resolved = {}
        for k, v in step.items():
            if isinstance(v, str):
                resolved[k] = re.sub(
                    r"\{(\w+)\}",
                    lambda m, vv=variables: str(vv.get(m.group(1), m.group(0))),
                    v,
                )
            else:
                resolved[k] = v
        return resolved

    def _resolve_single(self, text: str, variables: dict) -> str:
        return re.sub(
            r"\{(\w+)\}",
            lambda m: str(variables.get(m.group(1), m.group(0))),
            text,
        )

    def _execute_step(self, step: dict, variables: dict) -> str:
        t = step.get("type", "")

        # -- Browser -------------------------------------------------------
        if t == "go_to_url":
            return self.go_to_url(step.get("url", ""))

        if t == "click":
            return self.click_element(step.get("selector", ""))

        if t == "type":
            return self.type_text(step.get("selector", ""), step.get("text", ""))

        if t == "get_text":
            text = self.get_text(step.get("selector", ""))
            if step.get("var"):
                variables[step["var"]] = text
            return text

        if t == "get_number":
            num = self.get_number(step.get("selector", ""))
            if step.get("var"):
                variables[step["var"]] = str(num)
            return str(num)

        if t == "wait_for_element":
            return self.wait_for_element(
                step.get("selector", ""), int(step.get("timeout", 10))
            )

        if t == "wait":
            return self.wait_seconds(float(step.get("seconds", 1)))

        if t == "screenshot":
            return self.take_screenshot(step.get("filename", "screenshot.png"))

        # -- Google Sheets -------------------------------------------------
        if t == "sheet_read_cell":
            val = self.sheet_read_cell(step.get("sheet", ""), step.get("cell", ""))
            if step.get("var"):
                variables[step["var"]] = val
            return val

        if t == "sheet_write_cell":
            return self.sheet_write_cell(
                step.get("sheet", ""), step.get("cell", ""), step.get("value", "")
            )

        if t == "sheet_find_row":
            row = self.sheet_find_row(
                step.get("sheet", ""), step.get("column", ""), step.get("value", "")
            )
            if step.get("var"):
                variables[step["var"]] = str(row)
            return str(row)

        if t == "sheet_read_row":
            data = self.sheet_read_row(step.get("sheet", ""), int(step.get("row", 1)))
            if step.get("var"):
                variables[step["var"]] = str(data)
            return str(data)

        if t == "sheet_append_row":
            vals = step.get("values", [])
            if isinstance(vals, str):
                vals = [v.strip() for v in vals.split(",")]
            return self.sheet_append_row(step.get("sheet", ""), vals)

        # -- Logic ---------------------------------------------------------
        if t == "if_equals":
            ok = self.if_equals(step.get("value1", ""), step.get("value2", ""))
            if not ok and step.get("action_false", "stop") == "stop":
                raise StopTaskException(step.get("stop_message", "Condition not met"))
            return f"equals: {ok}"

        if t == "if_contains":
            ok = self.if_contains(step.get("text", ""), step.get("keyword", ""))
            if ok and step.get("action_true") == "notify":
                msg = self._resolve_single(step.get("notify_message", ""), variables)
                self.notify(msg)
            if not ok and step.get("action_false", "skip") == "stop":
                raise StopTaskException(step.get("stop_message", "Condition not met"))
            return f"contains: {ok}"

        if t == "if_greater":
            try:
                ok = self.if_greater_than(
                    float(step.get("num1", 0)), float(step.get("num2", 0))
                )
            except ValueError:
                ok = False
            return f"greater: {ok}"

        # -- Bulk Order steps ----------------------------------------------
        if t == "sheet_get_pending_rows":
            rows = self.sheet_get_pending_rows(
                step.get("sheet", ""),
                step.get("status_column", "E"),
                step.get("status_value", "Pending"),
                step.get("order_id_column", "A"),
                step.get("name_column", "B"),
                step.get("total_column", "C"),
            )
            if step.get("var"):
                variables[step["var"]] = rows
            return "Found {} pending rows".format(len(rows))

        if t == "web_get_order_list":
            orders = self.web_get_order_list(
                step.get("list_selector", ""),
                step.get("id_selector", ""),
                step.get("name_selector", ""),
                step.get("total_selector", ""),
            )
            if step.get("var"):
                variables[step["var"]] = orders
            return "Found {} orders on web".format(len(orders))

        if t == "validate_and_confirm_orders":
            pending = variables.get(step.get("pending_var", "pending_rows"), [])
            web_orders = variables.get(step.get("web_orders_var", "web_orders"), [])
            result = self.validate_and_confirm_orders(
                pending,
                web_orders,
                step.get("sheet", ""),
                step.get("status_column", "E"),
                step.get("confirm_url_template", ""),
                step.get("confirm_selector", ""),
            )
            if step.get("var"):
                variables[step["var"]] = result
            return (
                "Confirmed: {confirmed}, Skipped: {skipped}, "
                "Mismatches: {mismatches}, Not found: {not_found}, "
                "Unverified on web: {unverified_on_web}".format(**result)
            )

        # -- Notification --------------------------------------------------
        if t == "notify":
            return self.notify(step.get("message", ""))

        # -- AI Prompt -----------------------------------------------------
        if t == "ai_prompt":
            return self._run_ai_prompt(step, variables)

        # -- Scrape URL ----------------------------------------------------
        if t == "scrape_url":
            return self._run_scrape_url(step, variables)

        # -- PowerShell Agent ----------------------------------------------
        if t == "run_powershell":
            return self._run_powershell(step, variables)

        # -- OCR -----------------------------------------------------------
        if t == "ocr_image":
            return self._run_ocr_image(step, variables)

        self.logger.warning(f"Unknown step type: {t}")
        return f"unknown: {t}"

    # ------------------------------------------------------------------ #
    #  Browser actions                                                     #
    # ------------------------------------------------------------------ #

    def go_to_url(self, url: str) -> str:
        if not self.engine or not self.engine.browser:
            raise RuntimeError("Browser not available")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.engine.browser.navigate(url)
        return f"Navigated to {url}"

    def click_element(self, selector: str) -> str:
        if not self.engine or not self.engine.browser:
            raise RuntimeError("Browser not available")
        self.engine.browser.click(selector)
        return f"Clicked: {selector}"

    def type_text(self, selector: str, text: str) -> str:
        if not self.engine or not self.engine.browser:
            raise RuntimeError("Browser not available")
        self.engine.browser.fill(selector, text)
        return f"Typed in {selector}"

    def get_text(self, selector: str) -> str:
        if not self.engine or not self.engine.browser:
            raise RuntimeError("Browser not available")
        return self.engine.browser.get_text(selector) or ""

    def get_number(self, selector: str) -> float:
        text = self.get_text(selector)
        cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def wait_for_element(self, selector: str, timeout: int = 10) -> str:
        if not self.engine or not self.engine.browser:
            raise RuntimeError("Browser not available")
        self.engine.browser.wait_for_selector(selector, timeout=timeout * 1000)
        return f"Element visible: {selector}"

    def wait_seconds(self, seconds: float) -> str:
        time.sleep(seconds)
        return f"Waited {seconds}s"

    def take_screenshot(self, filename: str) -> str:
        if not self.engine or not self.engine.browser:
            raise RuntimeError("Browser not available")
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(_root, "screenshots", filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.engine.browser.screenshot(path)
        return f"Screenshot: {filename}"

    # ------------------------------------------------------------------ #
    #  Google Sheets actions                                               #
    # ------------------------------------------------------------------ #

    def _get_worksheet(self, sheet_name: str):
        if not self.engine or not self.engine.sheets:
            raise RuntimeError("Sheets module not available")
        spreadsheet_id = self.engine.config.get("google.spreadsheet_id", "")
        if not spreadsheet_id:
            raise RuntimeError("google.spreadsheet_id not configured")
        client = self.engine.sheets._get_client()
        return client.open_by_key(spreadsheet_id).worksheet(sheet_name)

    def sheet_read_cell(self, sheet_name: str, cell: str) -> str:
        ws = self._get_worksheet(sheet_name)
        return str(ws.acell(cell).value or "")

    def sheet_write_cell(self, sheet_name: str, cell: str, value) -> str:
        ws = self._get_worksheet(sheet_name)
        ws.update(cell, [[str(value)]])
        return f"Wrote '{value}' to {sheet_name}!{cell}"

    def sheet_find_row(self, sheet_name: str, column: str, value: str) -> int:
        ws = self._get_worksheet(sheet_name)
        col_idx = ord(column.upper()) - ord("A") + 1
        col_values = ws.col_values(col_idx)
        for i, v in enumerate(col_values, 1):
            if str(v) == str(value):
                return i
        return -1

    def sheet_read_row(self, sheet_name: str, row: int) -> list:
        ws = self._get_worksheet(sheet_name)
        return ws.row_values(row)

    def sheet_append_row(self, sheet_name: str, values: list) -> str:
        ws = self._get_worksheet(sheet_name)
        ws.append_row([str(v) for v in values])
        return f"Appended row to {sheet_name}: {values}"

    # ------------------------------------------------------------------ #
    #  Logic actions                                                       #
    # ------------------------------------------------------------------ #

    def if_equals(self, value1, value2) -> bool:
        return str(value1).strip() == str(value2).strip()

    def if_contains(self, text: str, keyword: str) -> bool:
        return keyword.lower() in text.lower()

    def if_greater_than(self, num1: float, num2: float) -> bool:
        return float(num1) > float(num2)

    # ------------------------------------------------------------------ #
    #  Notification                                                        #
    # ------------------------------------------------------------------ #

    def notify(self, message: str) -> str:
        self.logger.info(f"NOTIFY: {message}")
        if self._notify_cb:
            self._notify_cb(message)
        return f"Notified: {message}"

    # ------------------------------------------------------------------ #
    #  AI Prompt                                                           #
    # ------------------------------------------------------------------ #

    def _run_ai_prompt(self, step: dict, variables: dict) -> str:
        """Execute an ai_prompt step: call the configured AI and save result."""
        import os as _os, json as _json

        # Load AI config from config.json
        _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))))
        _cfg_path = _os.path.join(_root, "config.json")
        try:
            with open(_cfg_path, encoding="utf-8") as _f:
                _cfg = _json.load(_f).get("ai", {})
        except Exception:
            _cfg = {}

        provider   = _cfg.get("provider", "openai")
        api_key    = _cfg.get("api_key", "")
        model      = step.get("model", "") or _cfg.get("model", "")
        system     = step.get("system", "").strip() or _cfg.get(
            "system_prompt", "You are a helpful automation assistant.")
        max_tokens = int(step.get("max_tokens", _cfg.get("max_tokens", 800)) or 800)

        # Resolve {variables} in prompt
        raw_prompt = step.get("prompt", "")
        prompt = raw_prompt
        for k, v in variables.items():
            prompt = prompt.replace("{" + k + "}", str(v))

        if not prompt.strip():
            raise ValueError("ai_prompt: prompt kosong.")

        from modules.ai_client import call_ai
        response = call_ai(
            prompt=prompt,
            provider=provider,
            api_key=api_key,
            model=model,
            system=system,
            max_tokens=max_tokens,
        )

        var_name = step.get("var", "ai_result") or "ai_result"
        variables[var_name] = response
        self.logger.info("AI Prompt → %s = %s…", var_name, response[:60])
        return "AI response saved to {{{}}}: {}…".format(var_name, response[:50])

    # ------------------------------------------------------------------ #
    #  Scrape URL                                                          #
    # ------------------------------------------------------------------ #

    def _run_scrape_url(self, step: dict, variables: dict) -> str:
        """Execute a scrape_url step: fetch URL text and save to variable."""
        from modules.web_scraper import scrape_url

        url = step.get("url", "").strip()
        if not url:
            raise ValueError("scrape_url: URL kosong")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        self.logger.info("Scraping: %s", url)
        text = scrape_url(url)

        # Optional keyword filter — keep only lines containing keyword
        keyword = step.get("keyword", "").strip()
        if keyword:
            lines = [l for l in text.splitlines()
                     if keyword.lower() in l.lower() and l.strip()]
            text = "\n".join(lines) if lines else "(keyword '{}' tidak ditemukan)".format(keyword)

        var = step.get("var", "scraped_text") or "scraped_text"
        variables[var] = text
        self.logger.info("scrape_url → {%s} = %s…", var, text[:60])
        return "Scraped {} chars → {{{}}}".format(len(text), var)

    # ------------------------------------------------------------------ #
    #  PowerShell Agent                                                    #
    # ------------------------------------------------------------------ #

    def _run_powershell(self, step: dict, variables: dict) -> str:
        """
        Execute a run_powershell step.
        mode="auto"   → Haiku generates PS command from natural-language task
        mode="manual" → task field IS the raw PowerShell command
        """
        from modules.ps_agent import run_task

        # Resolve {variables} in task string
        raw_task = step.get("task", "").strip()
        task = raw_task
        for k, v in variables.items():
            task = task.replace("{" + k + "}", str(v))

        if not task:
            raise ValueError("run_powershell: field 'task' kosong")

        mode    = step.get("mode", "auto")
        timeout = int(step.get("timeout", 30) or 30)
        var     = step.get("var", "ps_output") or "ps_output"

        self.logger.info("PowerShell [%s]: %s…", mode, task[:60])

        result = run_task(task, mode=mode, timeout=timeout)

        output = result.get("output", "")
        error  = result.get("error", "")
        cmd    = result.get("command", task)

        variables[var] = output or error or "(no output)"

        if result.get("ok"):
            self.logger.info("PS OK → {%s} = %s…", var, output[:60])
            return "[PS] {} → {{{}}}: {}…".format(
                cmd[:40], var, output[:50])
        else:
            self.logger.warning("PS Error: %s", error[:100])
            return "[PS ERROR] {}: {}".format(cmd[:40], error[:80])

    # ------------------------------------------------------------------ #
    #  OCR Image                                                          #
    # ------------------------------------------------------------------ #

    def _run_ocr_image(self, step: dict, variables: dict) -> str:
        from modules.vision.ocr import extract_text, screenshot_and_ocr
        import os as _os, json as _json

        _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))))
        try:
            with open(_os.path.join(_root, "config.json"), encoding="utf-8") as _f:
                _cfg = _json.load(_f).get("ai", {})
        except Exception:
            _cfg = {}

        api_key  = _cfg.get("api_key", "")
        provider = _cfg.get("provider", "anthropic")
        model    = step.get("model", "") or _cfg.get("model", "")
        language = step.get("language", "")
        var      = step.get("var", "ocr_text") or "ocr_text"

        image_path = step.get("image_path", "").strip()
        if image_path:
            text = extract_text(image_path, api_key=api_key, provider=provider,
                                model=model, language=language)
            self.logger.info("OCR %s → %s…", image_path[:40], text[:60])
            result_desc = "OCR {} → {{{}}}".format(image_path[:30], var)
        else:
            text, path = screenshot_and_ocr(api_key=api_key, provider=provider, model=model)
            self.logger.info("OCR screenshot %s → %s…", path[:40], text[:60])
            result_desc = "OCR screenshot → {{{}}}".format(var)

        variables[var] = text
        return "{}: {}…".format(result_desc, text[:60])

    # ------------------------------------------------------------------ #
    #  Bulk Order Confirmation                                             #
    # ------------------------------------------------------------------ #

    def compare_values(self, val1: str, val2: str) -> bool:
        """Compare two values after normalizing currency symbols and whitespace.

        For numeric values: strips Rp, $, commas, spaces before comparing.
        For non-numeric values: case-insensitive string comparison.
        """
        def _as_number(v: str):
            cleaned = re.sub(r"[Rp$€£¥,\s]", "", str(v).strip(), flags=re.IGNORECASE)
            try:
                return str(float(cleaned))
            except ValueError:
                return None

        n1 = _as_number(val1)
        n2 = _as_number(val2)
        if n1 is not None and n2 is not None:
            return n1 == n2
        return str(val1).strip().lower() == str(val2).strip().lower()

    def sheet_get_pending_rows(self, sheet_name: str, status_column: str,
                               status_value: str, order_id_column: str,
                               name_column: str, total_column: str) -> list:
        """Read all rows from sheet where status_column == status_value.

        Returns list of {order_id, nama, total, row_number}.
        """
        ws = self._get_worksheet(sheet_name)
        all_values = ws.get_all_values()

        def _col_idx(letter: str) -> int:
            return ord(letter.strip().upper()[0]) - ord("A")

        s_idx = _col_idx(status_column)
        id_idx = _col_idx(order_id_column)
        nm_idx = _col_idx(name_column)
        tt_idx = _col_idx(total_column)
        max_idx = max(s_idx, id_idx, nm_idx, tt_idx)

        pending = []
        for row_num, row in enumerate(all_values, 1):
            if row_num == 1:          # skip header
                continue
            if len(row) <= max_idx:
                continue
            if str(row[s_idx]).strip().lower() == status_value.lower():
                pending.append({
                    "order_id":   str(row[id_idx]).strip(),
                    "nama":       str(row[nm_idx]).strip(),
                    "total":      str(row[tt_idx]).strip(),
                    "row_number": row_num,
                })
        return pending

    def web_get_order_list(self, list_selector: str, id_selector: str,
                           name_selector: str, total_selector: str) -> list:
        """Scrape all visible orders from the current web page.

        Returns list of {order_id, nama, total}.
        """
        if not self.engine or not self.engine.browser:
            raise RuntimeError("Browser not available")

        raw = self.engine.browser.query_elements(
            list_selector,
            {
                "order_id": id_selector,
                "nama":     name_selector,
                "total":    total_selector,
            },
        )
        return [
            {
                "order_id": r.get("order_id", "").strip(),
                "nama":     r.get("nama", "").strip(),
                "total":    r.get("total", "").strip(),
            }
            for r in raw
            if r.get("order_id", "").strip()
        ]

    def validate_and_confirm_orders(self, sheet_pending: list, web_orders: list,
                                    sheet_name: str, status_column: str,
                                    confirm_url_template: str = "",
                                    confirm_selector: str = "") -> dict:
        """Cross-check sheet pending rows against web orders and confirm matches.

        Logic:
          - Sheet row NOT on web  → write "Not Found on Web"
          - Nama mismatch         → write "MISMATCH - Nama"
          - Total mismatch        → write "MISMATCH - Total"
          - All match             → click confirm, write "Confirmed <timestamp>"
          - Web order not in sheet → log warning, add to report, do NOT confirm

        Returns dict with keys: confirmed, skipped, mismatches, not_found,
        unverified_on_web, checked, warnings, details.
        """
        result = {
            "confirmed":        0,
            "skipped":          0,
            "mismatches":       0,
            "not_found":        0,
            "unverified_on_web": 0,
            "errors":           0,
            "checked":          len(sheet_pending),
            "warnings":         [],
            "details":          [],
        }

        web_lookup = {str(o["order_id"]).strip(): o for o in web_orders}
        sheet_ids  = {str(r["order_id"]).strip() for r in sheet_pending}

        def _col_cell(col_letter: str, row_num: int) -> str:
            return "{}{}".format(col_letter.strip().upper(), row_num)

        for row in sheet_pending:
            order_id   = str(row["order_id"]).strip()
            sheet_nama = str(row["nama"]).strip()
            sheet_total = str(row["total"]).strip()
            row_num    = row["row_number"]
            cell       = _col_cell(status_column, row_num)

            if order_id not in web_lookup:
                self.sheet_write_cell(sheet_name, cell, "Not Found on Web")
                result["not_found"] += 1
                result["skipped"]   += 1
                result["details"].append({
                    "order_id": order_id, "nama": sheet_nama,
                    "total_sheet": sheet_total, "total_web": "",
                    "status": "Not Found on Web", "timestamp": "", "notes": "",
                })
                self._export_confirmation_csv({
                    "order_id": order_id, "nama": sheet_nama,
                    "total_sheet": sheet_total, "total_web": "",
                    "status": "Not Found on Web",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": "",
                })
                continue

            web = web_lookup[order_id]

            if not self.compare_values(sheet_nama, web["nama"]):
                status = "MISMATCH - Nama"
                self.sheet_write_cell(sheet_name, cell, status)
                result["mismatches"] += 1
                result["skipped"]    += 1
                result["details"].append({
                    "order_id": order_id, "nama": sheet_nama,
                    "total_sheet": sheet_total, "total_web": web["total"],
                    "status": status, "timestamp": "", "notes": web["nama"],
                })
                self._export_confirmation_csv({
                    "order_id": order_id, "nama": sheet_nama,
                    "total_sheet": sheet_total, "total_web": web["total"],
                    "status": status,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": "Web nama: {}".format(web["nama"]),
                })
                continue

            if not self.compare_values(sheet_total, web["total"]):
                status = "MISMATCH - Total"
                self.sheet_write_cell(sheet_name, cell, status)
                result["mismatches"] += 1
                result["skipped"]    += 1
                result["details"].append({
                    "order_id": order_id, "nama": sheet_nama,
                    "total_sheet": sheet_total, "total_web": web["total"],
                    "status": status, "timestamp": "", "notes": "",
                })
                self._export_confirmation_csv({
                    "order_id": order_id, "nama": sheet_nama,
                    "total_sheet": sheet_total, "total_web": web["total"],
                    "status": status,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": "Web total: {}".format(web["total"]),
                })
                continue

            # All match — confirm with retries
            confirmed = False
            if confirm_selector:
                if confirm_url_template:
                    url = confirm_url_template.replace("{order_id}", order_id)
                    try:
                        self.go_to_url(url)
                    except Exception as e:
                        self.logger.error(
                            "Failed to navigate for order %s: %s", order_id, e)

                retries = 0
                while retries < 3:
                    try:
                        self.click_element(confirm_selector)
                        confirmed = True
                        break
                    except Exception as e:
                        retries += 1
                        self.logger.warning(
                            "Confirm click failed (attempt %d/3) for order %s: %s",
                            retries, order_id, e)
                        if retries < 3:
                            for _ in range(30):
                                time.sleep(1)

                if not confirmed:
                    status = "Error - Manual Check Needed"
                    self.sheet_write_cell(sheet_name, cell, status)
                    result["errors"]  += 1
                    result["skipped"] += 1
                    result["details"].append({
                        "order_id": order_id, "nama": sheet_nama,
                        "total_sheet": sheet_total, "total_web": web["total"],
                        "status": status, "timestamp": "", "notes": "Max retries reached",
                    })
                    self._export_confirmation_csv({
                        "order_id": order_id, "nama": sheet_nama,
                        "total_sheet": sheet_total, "total_web": web["total"],
                        "status": status,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "notes": "Max retries reached",
                    })
                    continue
            else:
                confirmed = True

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status = "Confirmed - {}".format(timestamp)
            self.sheet_write_cell(sheet_name, cell, status)
            result["confirmed"] += 1
            result["details"].append({
                "order_id": order_id, "nama": sheet_nama,
                "total_sheet": sheet_total, "total_web": web["total"],
                "status": "Confirmed", "timestamp": timestamp, "notes": "",
            })
            self._export_confirmation_csv({
                "order_id": order_id, "nama": sheet_nama,
                "total_sheet": sheet_total, "total_web": web["total"],
                "status": "Confirmed", "timestamp": timestamp, "notes": "",
            })

        # Web orders not in sheet → log as unverified, do NOT confirm
        for order_id, web_order in web_lookup.items():
            if order_id not in sheet_ids:
                msg = "Unverified order on web - no sheet record: {}".format(order_id)
                self.logger.warning(msg)
                result["unverified_on_web"] += 1
                result["warnings"].append(msg)
                self._export_confirmation_csv({
                    "order_id": order_id,
                    "nama":     web_order.get("nama", ""),
                    "total_sheet": "",
                    "total_web": web_order.get("total", ""),
                    "status": "Unverified on Web",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": "No sheet record",
                })

        self._last_validation_result = result
        return result

    def _export_confirmation_csv(self, row: dict) -> None:
        """Append one result row to the daily confirmation report CSV."""
        _root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        date_str = datetime.now().strftime("%Y-%m-%d")
        csv_path = os.path.join(
            _root, "data", "confirmation_report_{}.csv".format(date_str))
        fieldnames = [
            "Order ID", "Nama", "Total Sheet", "Total Web",
            "Status", "Timestamp", "Notes",
        ]
        file_exists = os.path.exists(csv_path)
        try:
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    "Order ID":    row.get("order_id", ""),
                    "Nama":        row.get("nama", ""),
                    "Total Sheet": row.get("total_sheet", ""),
                    "Total Web":   row.get("total_web", ""),
                    "Status":      row.get("status", ""),
                    "Timestamp":   row.get("timestamp", ""),
                    "Notes":       row.get("notes", ""),
                })
        except Exception as e:
            self.logger.error("CSV export error: %s", e)

    # ------------------------------------------------------------------ #
    #  Continuous Loop Mode                                                #
    # ------------------------------------------------------------------ #

    def run_continuous(self, task: dict, loop_cb=None, stop_flag=None) -> None:
        """Run task in a continuous loop until stop_flag is set.

        Args:
            task:      Task dict.  Must include ``continuous_interval`` (seconds,
                       default 60).
            loop_cb:   Optional callable(state_dict).  Called with phase keys:
                         "start"     — loop beginning
                         "end"       — loop finished, stats available
                         "countdown" — each second of the wait period
            stop_flag: threading.Event; loop exits when set.
        """
        interval = int(task.get("continuous_interval", 60))
        loop_num = 0
        all_time = {
            "confirmed":        0,
            "mismatches":       0,
            "not_found":        0,
            "unverified_on_web": 0,
            "errors":           0,
        }

        while not (stop_flag and stop_flag.is_set()):
            loop_num += 1
            loop_stats = {
                "loop":      loop_num,
                "checked":   0,
                "confirmed": 0,
                "skipped":   0,
                "mismatches": 0,
                "not_found": 0,
            }

            self.logger.info("Loop #%d started", loop_num)
            if loop_cb:
                loop_cb({
                    "phase":    "start",
                    "loop":     loop_num,
                    "stats":    dict(loop_stats),
                    "all_time": dict(all_time),
                })

            error_retries = 0
            while error_retries <= 3:
                try:
                    self._last_validation_result = None
                    self._execute_task_steps(task, stop_flag=stop_flag)

                    vr = self._last_validation_result
                    if vr:
                        loop_stats.update({
                            "checked":    vr.get("checked", 0),
                            "confirmed":  vr.get("confirmed", 0),
                            "mismatches": vr.get("mismatches", 0),
                            "not_found":  vr.get("not_found", 0),
                            "skipped":    (vr.get("not_found", 0)
                                          + vr.get("mismatches", 0)
                                          + vr.get("errors", 0)),
                        })
                        all_time["confirmed"]        += vr.get("confirmed", 0)
                        all_time["mismatches"]       += vr.get("mismatches", 0)
                        all_time["not_found"]        += vr.get("not_found", 0)
                        all_time["unverified_on_web"] += vr.get("unverified_on_web", 0)
                        all_time["errors"]           += vr.get("errors", 0)
                    break

                except Exception as e:
                    error_retries += 1
                    all_time["errors"] += 1
                    self.logger.error(
                        "Loop #%d error (attempt %d/3): %s",
                        loop_num, error_retries, e)
                    if error_retries <= 3:
                        self.logger.info("Waiting 30s before retry...")
                        for _ in range(30):
                            if stop_flag and stop_flag.is_set():
                                return
                            time.sleep(1)

            if loop_stats["checked"] == 0:
                self.logger.info(
                    "No pending orders. Checking again in %ds...", interval)
            else:
                self.logger.info(
                    "Loop #%d complete — confirmed: %d, skipped: %d, "
                    "mismatches: %d, not found: %d",
                    loop_num, loop_stats["confirmed"], loop_stats["skipped"],
                    loop_stats["mismatches"], loop_stats["not_found"])

            if loop_cb:
                loop_cb({
                    "phase":    "end",
                    "loop":     loop_num,
                    "stats":    dict(loop_stats),
                    "all_time": dict(all_time),
                })

            if stop_flag and stop_flag.is_set():
                break

            for remaining in range(interval, 0, -1):
                if stop_flag and stop_flag.is_set():
                    return
                if loop_cb:
                    loop_cb({
                        "phase":     "countdown",
                        "loop":      loop_num,
                        "remaining": remaining,
                        "stats":     dict(loop_stats),
                        "all_time":  dict(all_time),
                    })
                time.sleep(1)
