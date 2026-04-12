# -*- coding: utf-8 -*-
"""
modules/sheets/credentials_helper.py
Friendly setup guide for Google Sheets credentials.
Renders inside a tkinter Frame provided by the caller.
"""

import json
import os
import shutil
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CREDS_DEST = os.path.join(_ROOT, "credentials.json")
_CONSOLE_URL = "https://console.cloud.google.com/"

BG   = "#0A0A0F"; CARD = "#12121A"; SIDE = "#0D0D16"
ACC  = "#6C63FF"; FG   = "#E0DFFF"; MUT  = "#555575"
GRN  = "#4CAF88"; RED  = "#F06070"; YEL  = "#F0C060"


def _lbl(parent, text, fg=FG, bg=CARD, font=("Segoe UI", 10), **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, **kw)


class CredentialsSetupPanel:
    """
    Drop-in panel that guides the user through getting credentials.json.
    Call build(parent_frame) to render it.
    Calls on_done() when credentials are placed correctly.
    """

    STEPS = [
        ("1", "Go to console.cloud.google.com"),
        ("2", "Create a new project named  Synthex"),
        ("3", "Enable the Google Sheets API  (search for it)"),
        ("4", "Go to IAM & Admin -> Service Accounts"),
        ("5", "Click  + Create Service Account  -> fill in a name -> Done"),
        ("6", "Open the account -> Keys tab -> Add Key -> JSON"),
        ("7", "Rename the downloaded file to  credentials.json"),
        ("8", "Place it at:  {}".format(_CREDS_DEST)),
    ]

    def __init__(self, on_done=None):
        self.on_done = on_done

    def build(self, parent):
        f = tk.Frame(parent, bg=CARD, padx=20, pady=18)
        f.pack(fill="both", expand=True)

        _lbl(f, "Setup Google Sheets Access",
             fg=ACC, font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 4))
        _lbl(f, "Follow these steps to connect Synthex to Google Sheets:",
             fg=MUT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 14))

        steps_frame = tk.Frame(f, bg=CARD)
        steps_frame.pack(fill="x", pady=(0, 16))

        for num, text in self.STEPS:
            row = tk.Frame(steps_frame, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=num, bg=ACC, fg=BG,
                     font=("Segoe UI", 9, "bold"),
                     width=2, padx=4, pady=2).pack(side="left", padx=(0, 10))
            _lbl(row, text, fg=FG, font=("Segoe UI", 9),
                 justify="left").pack(side="left", anchor="w")

        btn_frame = tk.Frame(f, bg=CARD)
        btn_frame.pack(fill="x", pady=(4, 0))

        tk.Button(
            btn_frame, text="Open Google Cloud Console",
            bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=lambda: webbrowser.open(_CONSOLE_URL),
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame, text="I have the file - let me select it",
            bg=SIDE, fg=FG, font=("Segoe UI", 9),
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=lambda: self._pick_file(parent),
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame, text="Check if file is ready",
            bg=SIDE, fg=FG, font=("Segoe UI", 9),
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=lambda: self._check_file(parent),
        ).pack(side="left")

        self._status_var = tk.StringVar()
        _lbl(f, "", fg=GRN, font=("Segoe UI", 9),
             textvariable=self._status_var).pack(anchor="w", pady=(10, 0))

    def _pick_file(self, parent):
        path = filedialog.askopenfilename(
            parent=parent,
            title="Select your credentials JSON file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "client_email" not in data or "private_key" not in data:
                messagebox.showerror(
                    "Invalid File",
                    "This does not look like a Google service account key.\n"
                    "Make sure you downloaded the JSON key from Service Accounts.",
                    parent=parent,
                )
                return
            shutil.copy2(path, _CREDS_DEST)
            self._status_var.set(
                "credentials.json saved! Click 'Check if file is ready'."
            )
        except json.JSONDecodeError:
            messagebox.showerror(
                "Invalid File",
                "The file is not valid JSON. Please select the correct file.",
                parent=parent,
            )
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=parent)

    def _check_file(self, parent):
        if not os.path.isfile(_CREDS_DEST):
            self._status_var.set("")
            messagebox.showwarning(
                "Not Found",
                "credentials.json not found at:\n{}\n\n"
                "Use 'I have the file' to select and copy it.".format(_CREDS_DEST),
                parent=parent,
            )
            return
        try:
            with open(_CREDS_DEST, "r", encoding="utf-8") as f:
                data = json.load(f)
            email = data.get("client_email", "")
            if not email:
                messagebox.showerror(
                    "Invalid File",
                    "The credentials.json exists but does not contain a service "
                    "account email. Please download the file again.",
                    parent=parent,
                )
                return
            self._status_var.set("File is valid. Service account: {}".format(email))
            if self.on_done:
                self.on_done()
        except Exception as e:
            messagebox.showerror("Error reading file", str(e), parent=parent)
