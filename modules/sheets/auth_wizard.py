# -*- coding: utf-8 -*-
"""
modules/sheets/auth_wizard.py
Step-by-step Google Sheets connection wizard for Synthex.
Non-technical users are guided through 5 steps.
"""

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from modules.sheets import connector

BG   = "#0A0A0F"; CARD = "#12121A"; SIDE = "#0D0D16"
ACC  = "#6C63FF"; FG   = "#E0DFFF"; MUT  = "#555575"
GRN  = "#4CAF88"; RED  = "#F06070"; YEL  = "#F0C060"


def _lbl(parent, text, fg=FG, bg=CARD, font=("Segoe UI", 10), **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, **kw)


def _btn(parent, text, command, bg=ACC, fg=BG):
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, font=("Segoe UI", 9, "bold"),
        relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
    )


class SheetsAuthWizard:
    """
    5-step wizard shown in a top-level window.
    When complete, calls on_done(sheet_entry_dict).
    sheet_entry_dict has keys: name, url, spreadsheet_id, worksheet, last_synced.
    """

    STEPS = [
        "Open Google Sheet",
        "Share with Synthex",
        "Paste Sheet URL",
        "Select Worksheet",
        "Test Connection",
    ]

    def __init__(self, parent_widget, on_done=None):
        self._parent = parent_widget
        self.on_done = on_done
        self._step = 0
        self._sheet_id = ""
        self._sheet_url = ""
        self._worksheets = []
        self._selected_ws = ""
        self._win = None

    def start_wizard(self):
        """Launch the wizard window."""
        self._win = tk.Toplevel(self._parent)
        self._win.title("Connect Google Sheet - Synthex")
        self._win.configure(bg=BG)
        self._win.geometry("560x480")
        self._win.resizable(False, False)
        self._win.grab_set()

        # Progress bar area
        self._header = tk.Frame(self._win, bg=SIDE, padx=20, pady=14)
        self._header.pack(fill="x")

        self._step_label = tk.Label(
            self._header, text="", bg=SIDE, fg=ACC,
            font=("Segoe UI", 11, "bold"),
        )
        self._step_label.pack(anchor="w")

        self._progress_row = tk.Frame(self._header, bg=SIDE)
        self._progress_row.pack(fill="x", pady=(8, 0))
        self._dot_labels = []
        for i, name in enumerate(self.STEPS):
            dot = tk.Label(
                self._progress_row, text="  {}  ".format(i + 1),
                bg=CARD, fg=MUT, font=("Segoe UI", 8, "bold"),
                relief="flat", padx=4, pady=2,
            )
            dot.pack(side="left", padx=2)
            self._dot_labels.append(dot)

        # Content area
        self._content = tk.Frame(self._win, bg=BG, padx=24, pady=20)
        self._content.pack(fill="both", expand=True)

        # Bottom nav
        nav = tk.Frame(self._win, bg=SIDE, padx=20, pady=12)
        nav.pack(fill="x", side="bottom")
        self._back_btn = _btn(nav, "Back", self._go_back, bg=CARD, fg=FG)
        self._back_btn.pack(side="left")
        self._next_btn = _btn(nav, "Next", self._go_next)
        self._next_btn.pack(side="right")

        self._url_var = tk.StringVar()
        self._ws_var = tk.StringVar()

        self._show_step(0)

    # ------------------------------------------------------------------
    def _show_step(self, idx):
        self._step = idx
        for w in self._content.winfo_children():
            w.destroy()
        for i, dot in enumerate(self._dot_labels):
            if i < idx:
                dot.configure(bg=GRN, fg=BG)
            elif i == idx:
                dot.configure(bg=ACC, fg=BG)
            else:
                dot.configure(bg=CARD, fg=MUT)
        self._step_label.configure(
            text="Step {} of {}:  {}".format(idx + 1, len(self.STEPS), self.STEPS[idx])
        )
        self._back_btn.configure(state="normal" if idx > 0 else "disabled")
        self._next_btn.configure(text="Finish" if idx == len(self.STEPS) - 1 else "Next")

        [self.step1_open_sheet, self.step2_share_sheet, self.step3_paste_url,
         self.step4_select_worksheet, self.step5_test_connection][idx]()

    def _go_next(self):
        if self._step == 2:
            if not self._validate_url():
                return
        if self._step == 3:
            if not self._ws_var.get():
                messagebox.showwarning("Select Worksheet",
                                       "Please select a worksheet tab.",
                                       parent=self._win)
                return
            self._selected_ws = self._ws_var.get()
        if self._step == len(self.STEPS) - 1:
            self._finish()
            return
        self._show_step(self._step + 1)

    def _go_back(self):
        if self._step > 0:
            self._show_step(self._step - 1)

    # ------------------------------------------------------------------
    def step1_open_sheet(self):
        c = self._content
        _lbl(c, "Open the Google Sheet you want to connect.",
             fg=FG, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 10))
        _lbl(c,
             "If you do not have a sheet yet, click the button below\n"
             "to open Google Sheets in your browser and create one.",
             fg=MUT, font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 20))
        _btn(c, "Open Google Sheets",
             command=lambda: webbrowser.open("https://sheets.google.com"),
             bg=ACC, fg=BG).pack(anchor="w")

    def step2_share_sheet(self):
        c = self._content
        email = connector.get_service_account_email()
        _lbl(c, "Share your sheet with Synthex.",
             fg=FG, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 10))

        instructions = (
            "1. Open your Google Sheet\n"
            "2. Click the  Share  button (top-right)\n"
            "3. Paste the email below into the 'Add people' field\n"
            "4. Set access to  Editor\n"
            "5. Click  Send"
        )
        _lbl(c, instructions, fg=MUT, font=("Segoe UI", 9),
             justify="left").pack(anchor="w", pady=(0, 14))

        if email:
            _lbl(c, "Share with this email:", fg=MUT,
                 font=("Segoe UI", 9)).pack(anchor="w")
            email_row = tk.Frame(c, bg=BG)
            email_row.pack(fill="x", pady=(4, 0))
            email_entry = tk.Entry(email_row, font=("Segoe UI", 10),
                                   bg=CARD, fg=ACC, insertbackground=FG,
                                   relief="flat", bd=0)
            email_entry.insert(0, email)
            email_entry.configure(state="readonly")
            email_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=4)
            _btn(email_row, "Copy",
                 command=lambda: self._copy_to_clipboard(email),
                 bg=SIDE, fg=FG).pack(side="left")
        else:
            _lbl(c, "Could not read service account email from credentials.json.",
                 fg=RED, font=("Segoe UI", 9)).pack(anchor="w")

    def step3_paste_url(self):
        c = self._content
        _lbl(c, "Paste the URL of your Google Sheet.",
             fg=FG, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 10))
        _lbl(c,
             "Copy the full URL from your browser address bar\n"
             "while the sheet is open, then paste it below.",
             fg=MUT, font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 14))

        _lbl(c, "Sheet URL:", fg=MUT, font=("Segoe UI", 9)).pack(anchor="w")
        url_entry = tk.Entry(c, textvariable=self._url_var,
                             font=("Segoe UI", 9), bg=CARD, fg=FG,
                             insertbackground=FG, relief="flat", bd=0)
        url_entry.pack(fill="x", pady=(4, 0), ipady=6)
        url_entry.focus_set()

        self._url_status = _lbl(c, "", fg=MUT, font=("Segoe UI", 8))
        self._url_status.pack(anchor="w", pady=(4, 0))
        self._url_var.trace_add("write", self._on_url_change)

    def _on_url_change(self, *_):
        url = self._url_var.get().strip()
        sid = connector.extract_sheet_id(url)
        if sid:
            self._url_status.configure(
                text="Sheet ID found: {}".format(sid), fg=GRN
            )
        elif url:
            self._url_status.configure(
                text="Paste a full Google Sheets URL (e.g. https://docs.google.com/spreadsheets/d/...)",
                fg=YEL,
            )
        else:
            self._url_status.configure(text="", fg=MUT)

    def _validate_url(self):
        url = self._url_var.get().strip()
        sid = connector.extract_sheet_id(url)
        if not sid:
            messagebox.showerror(
                "Invalid URL",
                "Could not find a spreadsheet ID in the URL you entered.\n"
                "Make sure to copy the full URL from the browser address bar.",
                parent=self._win,
            )
            return False
        self._sheet_id = sid
        self._sheet_url = url
        return True

    def step4_select_worksheet(self):
        c = self._content
        _lbl(c, "Select which worksheet (tab) to use.",
             fg=FG, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 10))
        _lbl(c, "Loading worksheet list...", fg=MUT,
             font=("Segoe UI", 9)).pack(anchor="w")

        def _load():
            names, err = connector.get_worksheets(self._sheet_id)
            self._win.after(0, lambda: self._show_ws_list(c, names, err))

        threading.Thread(target=_load, daemon=True).start()

    def _show_ws_list(self, c, names, err):
        for w in c.winfo_children():
            w.destroy()
        _lbl(c, "Select which worksheet (tab) to use.",
             fg=FG, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 10))

        if err:
            _lbl(c, err, fg=RED, font=("Segoe UI", 9),
                 justify="left", wraplength=480).pack(anchor="w")
            return

        if not names:
            _lbl(c, "No worksheets found. Check the sheet URL and sharing settings.",
                 fg=YEL, font=("Segoe UI", 9)).pack(anchor="w")
            return

        self._worksheets = names
        if not self._ws_var.get() or self._ws_var.get() not in names:
            self._ws_var.set(names[0])

        _lbl(c, "Worksheet:", fg=MUT, font=("Segoe UI", 9)).pack(anchor="w")
        cb = ttk.Combobox(c, textvariable=self._ws_var,
                          values=names, state="readonly", width=30)
        cb.pack(anchor="w", pady=(4, 14))

        # Show preview of first 3 rows
        _lbl(c, "Loading preview...", fg=MUT, font=("Segoe UI", 9)).pack(anchor="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._load_preview(c))
        self._preview_frame = tk.Frame(c, bg=BG)
        self._preview_frame.pack(fill="x", pady=(4, 0))
        self._load_preview(c)

    def _load_preview(self, c):
        for w in self._preview_frame.winfo_children():
            w.destroy()
        _lbl(self._preview_frame, "Loading preview...",
             fg=MUT, bg=BG, font=("Segoe UI", 9)).pack(anchor="w")

        ws_name = self._ws_var.get()
        sid = self._sheet_id

        def _fetch():
            dummy_sheets = [{
                "name": "__wizard__",
                "spreadsheet_id": sid,
                "worksheet": ws_name,
            }]
            rows, err = connector.preview_data(dummy_sheets, "__wizard__", max_rows=3)
            self._win.after(0, lambda: self._show_preview(rows, err))

        threading.Thread(target=_fetch, daemon=True).start()

    def _show_preview(self, rows, err):
        for w in self._preview_frame.winfo_children():
            w.destroy()
        if err:
            _lbl(self._preview_frame, err, fg=RED, bg=BG,
                 font=("Segoe UI", 8), justify="left",
                 wraplength=480).pack(anchor="w")
            return
        if not rows:
            _lbl(self._preview_frame, "(Sheet appears empty)",
                 fg=MUT, bg=BG, font=("Segoe UI", 8)).pack(anchor="w")
            return
        _lbl(self._preview_frame, "Preview (first 3 rows):",
             fg=MUT, bg=BG, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))
        tbl = tk.Frame(self._preview_frame, bg=BG)
        tbl.pack(anchor="w")
        max_cols = min(max(len(r) for r in rows), 6)
        for ri, row in enumerate(rows):
            for ci in range(max_cols):
                val = row[ci] if ci < len(row) else ""
                bg = SIDE if ri == 0 else BG
                tk.Label(tbl, text=str(val)[:16], bg=bg,
                         fg=ACC if ri == 0 else FG,
                         font=("Segoe UI", 8),
                         relief="flat", padx=6, pady=3,
                         borderwidth=1).grid(row=ri, column=ci, sticky="w")

    def step5_test_connection(self):
        c = self._content
        _lbl(c, "Testing connection...",
             fg=FG, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 10))
        _lbl(c, "Checking read and write access to your sheet.",
             fg=MUT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 14))

        self._test_status = _lbl(c, "Please wait...", fg=YEL, font=("Segoe UI", 10))
        self._test_status.pack(anchor="w")

        self._next_btn.configure(state="disabled")

        def _run():
            dummy = [{
                "name": "__test__",
                "spreadsheet_id": self._sheet_id,
                "worksheet": self._selected_ws,
            }]
            val, err = connector.read_cell(dummy, "__test__", "A1")
            if err:
                self._win.after(0, lambda: self._test_result(False, err))
                return
            ok, err2 = connector.write_cell(
                dummy, "__test__", "A1",
                val  # write back what we read (non-destructive)
            )
            if err2:
                self._win.after(0, lambda: self._test_result(False, err2))
            else:
                self._win.after(0, lambda: self._test_result(True, ""))

        threading.Thread(target=_run, daemon=True).start()

    def _test_result(self, success, err):
        self._next_btn.configure(state="normal")
        if success:
            self._test_status.configure(
                text="Connection successful! Sheet is ready to use.",
                fg=GRN,
            )
        else:
            self._test_status.configure(
                text="Connection failed: {}".format(err),
                fg=RED,
            )

    def _copy_to_clipboard(self, text):
        try:
            self._win.clipboard_clear()
            self._win.clipboard_append(text)
        except Exception:
            pass

    def _finish(self):
        ws = self._selected_ws or "Sheet1"
        entry = {
            "name": "Sheet {}".format(self._sheet_id[:8]),
            "url": self._sheet_url,
            "spreadsheet_id": self._sheet_id,
            "worksheet": ws,
            "last_synced": "-",
        }
        self._win.destroy()
        if self.on_done:
            self.on_done(entry)
