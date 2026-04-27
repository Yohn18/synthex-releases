# -*- coding: utf-8 -*-
"""
ui/ctk_compat.py — CustomTkinter compatibility wrappers.
Drop-in replacements for tk/ttk widgets that accept old tkinter
parameter names (bg, fg, relief, bd, …) and translate them to CTk.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Parameter translation maps ────────────────────────────────────────────────

_RENAME = {
    "bg":              "fg_color",
    "fg":              "text_color",
    "activebackground":"hover_color",
}

_DROP = {
    "relief", "bd", "borderwidth",
    "highlightthickness", "highlightcolor", "highlightbackground",
    "insertbackground", "insertwidth", "insertborderwidth",
    "selectbackground", "selectforeground", "selectcolor",
    "disabledforeground", "activeforeground",
    "takefocus", "overrelief",
    "readonlybackground", "invalidbackground",
}

def _tr(kw: dict) -> dict:
    out = {}
    for k, v in kw.items():
        if k in _DROP:
            continue
        out[_RENAME.get(k, k)] = v
    return out


# ── Frame ─────────────────────────────────────────────────────────────────────

class Frame(ctk.CTkFrame):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 0)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)


# ── Label ─────────────────────────────────────────────────────────────────────

class Label(ctk.CTkLabel):
    def __init__(self, parent=None, **kw):
        # CTkLabel needs text= always
        kw.setdefault("text", "")
        # anchor → justify for CTkLabel
        if "anchor" in kw:
            anchor = kw.pop("anchor")
            if anchor in ("w", "nw", "sw"):
                kw.setdefault("justify", "left")
            elif anchor in ("e", "ne", "se"):
                kw.setdefault("justify", "right")
        kw.setdefault("fg_color", "transparent")
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        if "anchor" in kw:
            anchor = kw.pop("anchor")
            if anchor in ("w", "nw", "sw"):
                kw.setdefault("justify", "left")
            elif anchor in ("e", "ne", "se"):
                kw.setdefault("justify", "right")
        if "fg_color" not in kw and "bg" not in kw:
            pass
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)


# ── Button ────────────────────────────────────────────────────────────────────

class Button(ctk.CTkButton):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 4)
        kw.setdefault("border_width", 0)
        # ipady → not supported, drop
        kw.pop("ipady", None)
        kw.pop("ipadx", None)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        kw.pop("ipady", None)
        kw.pop("ipadx", None)
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)


# ── Entry ─────────────────────────────────────────────────────────────────────

class Entry(ctk.CTkEntry):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 4)
        kw.setdefault("border_width", 1)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)


# ── Text (Textbox) ────────────────────────────────────────────────────────────

class Text(ctk.CTkTextbox):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 4)
        # CTkTextbox has built-in scrollbar — if caller adds external one, disable internal
        if "yscrollcommand" in kw:
            # keep yscrollcommand for internal textbox
            pass
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)

    # Expose internal textbox scrollbar command for external ttk.Scrollbar
    @property
    def yview(self):
        return self._textbox.yview


# ── ScrolledText (CTkTextbox already has scrollbar) ──────────────────────────

class ScrolledText(ctk.CTkTextbox):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 4)
        kw.pop("yscrollcommand", None)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        kw.pop("yscrollcommand", None)
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)


# ── Checkbutton ───────────────────────────────────────────────────────────────

class Checkbutton(ctk.CTkCheckBox):
    def __init__(self, parent=None, **kw):
        kw.pop("onvalue", None)
        kw.pop("offvalue", None)
        kw.pop("indicatoron", None)
        kw.setdefault("corner_radius", 3)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        kw.pop("onvalue", None)
        kw.pop("offvalue", None)
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)


# ── Radiobutton ───────────────────────────────────────────────────────────────

class Radiobutton(ctk.CTkRadioButton):
    def __init__(self, parent=None, **kw):
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)


# ── Scrollbar (ttk replacement) ───────────────────────────────────────────────

class Scrollbar(ctk.CTkScrollbar):
    def __init__(self, parent=None, **kw):
        # CTkScrollbar: orient supported, command supported
        kw.pop("troughcolor", None)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        kw.pop("troughcolor", None)
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)


# ── Combobox (ttk replacement) ────────────────────────────────────────────────

class Combobox(ctk.CTkComboBox):
    def __init__(self, parent=None, **kw):
        # CTkComboBox uses 'values' list — same as ttk.Combobox
        kw.pop("postcommand", None)
        kw.pop("exportselection", None)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        kw.pop("postcommand", None)
        kw.pop("exportselection", None)
        super().configure(**_tr(kw))

    def config(self, **kw):
        self.configure(**kw)

    # ttk.Combobox compat: get() / set() / current()
    def current(self, idx=None):
        if idx is None:
            vals = self.cget("values")
            cur  = self.get()
            return vals.index(cur) if cur in vals else -1
        vals = self.cget("values")
        if vals and idx < len(vals):
            self.set(vals[idx])
