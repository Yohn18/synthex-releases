# -*- coding: utf-8 -*-
"""ui/templates.py - Template picker for Synthex macro builder."""
import tkinter as tk
from tkinter import ttk

BG   = "#111118"; CARD = "#1A1A24"; SIDE = "#0D0D12"
ACC  = "#6C4AFF"; FG   = "#E0DFFF"; MUT  = "#555575"
GRN  = "#4CAF88"; YEL  = "#F0C060"; BLUE = "#4A9EFF"; PRP = "#9D5CF6"

TEMPLATES = [
    {
        "name": "Update Price to Sheet",
        "icon": "->",
        "color": YEL,
        "description": "Get price from website, save to Google Sheet automatically.",
        "steps_preview": [
            "->  Go to product URL",
            "<-T Get price text",
            "[W] Write to Sheet cell",
            "[!] Notify when done",
        ],
        "steps": [
            {"type": "go_to_url",        "url": "https://example.com/product"},
            {"type": "get_text",         "selector": ".price", "var": "price"},
            {"type": "sheet_write_cell", "sheet": "Sheet1",    "cell": "B2", "value": "{price}"},
            {"type": "notify",           "message": "Price updated: {price}"},
        ],
    },
    {
        "name": "Confirm Order on Website",
        "icon": "[?]",
        "color": GRN,
        "description": "Read order ID from sheet, find and confirm it on website.",
        "steps_preview": [
            "[R] Read order ID from Sheet",
            "->  Go to order page",
            "[*] Click Confirm button",
            "[W] Write status back",
        ],
        "steps": [
            {"type": "sheet_read_cell", "sheet": "Orders", "cell": "A2", "var": "order_id"},
            {"type": "go_to_url",       "url": "https://example.com/orders/{order_id}"},
            {"type": "click",           "selector": "#btn-confirm"},
            {"type": "sheet_write_cell","sheet": "Orders", "cell": "B2", "value": "Confirmed"},
        ],
    },
    {
        "name": "Monitor Stock Level",
        "icon": "[~]",
        "color": BLUE,
        "description": "Check stock level on site, send alert notification if low.",
        "steps_preview": [
            "->  Go to inventory page",
            "<-# Get stock number",
            "[=] If stock < threshold",
            "[!] Send low-stock alert",
        ],
        "steps": [
            {"type": "go_to_url",   "url": "https://example.com/inventory"},
            {"type": "get_number",  "selector": ".stock-qty", "var": "stock"},
            {"type": "if_greater",  "num1": "10", "num2": "{stock}"},
            {"type": "notify",      "message": "Low stock alert: {stock} units remaining"},
        ],
    },
    {
        "name": "Copy Data from Web to Sheet",
        "icon": "<-T",
        "color": PRP,
        "description": "Grab multiple values from a web page, paste them into a sheet.",
        "steps_preview": [
            "->  Go to data source URL",
            "<-T Extract title/name",
            "<-# Extract numeric value",
            "[+] Append row to Sheet",
        ],
        "steps": [
            {"type": "go_to_url",        "url": "https://example.com/data"},
            {"type": "get_text",         "selector": "h1",      "var": "title"},
            {"type": "get_number",       "selector": ".value",  "var": "amount"},
            {"type": "sheet_append_row", "sheet": "Data",
             "values": ["{title}", "{amount}"]},
        ],
    },
]


class TemplatePickerDialog:
    """Modal dialog that lets the user pick a macro template."""

    def __init__(self, parent, on_select=None):
        self._parent    = parent
        self._on_select = on_select
        self._result    = None

    def show(self):
        dlg = tk.Toplevel(self._parent)
        dlg.title("Choose a Template")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.transient(self._parent)
        dlg.grab_set()

        W, H = 820, 520
        px = self._parent.winfo_rootx() + (self._parent.winfo_width()  - W) // 2
        py = self._parent.winfo_rooty() + (self._parent.winfo_height() - H) // 2
        dlg.geometry("{}x{}+{}+{}".format(W, H, px, py))

        # Header
        hdr = tk.Frame(dlg, bg=SIDE, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Choose a Template", bg=SIDE, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=24, pady=14)
        tk.Button(hdr, text="\u2715  Start Blank", bg=CARD, fg=MUT,
                  activebackground=ACC, activeforeground=BG,
                  font=("Segoe UI", 9), relief="flat", bd=0,
                  padx=14, pady=6, cursor="hand2",
                  command=lambda: (dlg.destroy())).pack(side="right", padx=16, pady=12)

        tk.Label(dlg, text="Pick a starting point \u2014 you can edit all steps afterwards.",
                 bg=BG, fg=MUT, font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(12, 8))

        # 2x2 grid
        grid = tk.Frame(dlg, bg=BG)
        grid.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        for i, tmpl in enumerate(TEMPLATES):
            row_idx = i // 2
            col_idx = i  % 2
            clr = tmpl["color"]

            card = tk.Frame(grid, bg=CARD, padx=20, pady=16, cursor="hand2")
            card.grid(row=row_idx, column=col_idx, padx=8, pady=8, sticky="nsew")
            grid.rowconfigure(row_idx, weight=1)
            grid.columnconfigure(col_idx, weight=1)

            # Top accent line
            tk.Frame(card, bg=clr, height=3).pack(fill="x", pady=(0, 10))

            # Icon + title
            title_row = tk.Frame(card, bg=CARD)
            title_row.pack(fill="x", pady=(0, 6))
            tk.Label(title_row, text=tmpl["icon"], bg=CARD, fg=clr,
                     font=("Courier New", 16, "bold")).pack(side="left", padx=(0, 10))
            tk.Label(title_row, text=tmpl["name"], bg=CARD, fg=clr,
                     font=("Segoe UI", 10, "bold")).pack(side="left")

            # Description
            tk.Label(card, text=tmpl["description"], bg=CARD, fg=MUT,
                     font=("Segoe UI", 8), wraplength=320,
                     justify="left").pack(anchor="w", pady=(0, 8))

            # Step preview
            prev_frame = tk.Frame(card, bg=SIDE, padx=10, pady=8)
            prev_frame.pack(fill="x", pady=(0, 10))
            for line in tmpl["steps_preview"]:
                tk.Label(prev_frame, text=line, bg=SIDE, fg=MUT,
                         font=("Courier New", 8)).pack(anchor="w")

            def _use(t=tmpl, d=dlg):
                self._result = t
                if self._on_select:
                    self._on_select(t)
                d.destroy()

            tk.Button(card, text="Use This Template \u2192",
                      bg=clr, fg=BG, font=("Segoe UI", 9, "bold"),
                      relief="flat", bd=0, padx=12, pady=6,
                      cursor="hand2", command=_use).pack(anchor="w")

        dlg.wait_window()
        return self._result
