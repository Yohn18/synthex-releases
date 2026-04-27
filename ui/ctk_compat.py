# -*- coding: utf-8 -*-
"""
ui/ctk_compat.py — CustomTkinter compatibility wrappers.
Drop-in replacements for tk/ttk widgets that accept old tkinter
parameter names (bg, fg, relief, bd, padx, pady, …) and translate
them to CustomTkinter equivalents.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Parameter translation ─────────────────────────────────────────────────────

_RENAME = {
    "bg":               "fg_color",
    "fg":               "text_color",
    "activebackground": "hover_color",
}

# Params unsupported by CTk containers (Frame, Entry, etc.) — silently dropped
_DROP = {
    "relief", "bd", "borderwidth",
    "highlightthickness", "highlightcolor", "highlightbackground",
    "insertbackground", "insertwidth", "insertborderwidth",
    "selectbackground", "selectforeground", "selectcolor",
    "disabledforeground", "activeforeground",
    "takefocus", "overrelief",
    "readonlybackground", "invalidbackground",
    # geometry params invalid in Frame/Entry constructors
    "padx", "pady", "ipadx", "ipady",
}

# CTkLabel supports padx/pady internally — lighter drop set for Label only
_DROP_LABEL = _DROP - {"padx", "pady"}

# Per-widget extra renames
_SCROLLBAR_RENAME = {"orient": "orientation"}
_COMBOBOX_RENAME  = {"textvariable": "variable"}

def _tr(kw: dict, extra: dict = None, drop: set = None) -> dict:
    if drop is None:
        drop = _DROP
    out = {}
    renames = dict(_RENAME)
    if extra:
        renames.update(extra)
    for k, v in kw.items():
        if k in drop:
            continue
        out[renames.get(k, k)] = v
    return out


# ── Frame ─────────────────────────────────────────────────────────────────────

class Frame(ctk.CTkFrame):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 0)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        try:
            super().configure(**_tr(kw))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)


# ── Label ─────────────────────────────────────────────────────────────────────

class Label(ctk.CTkLabel):
    def __init__(self, parent=None, **kw):
        kw.setdefault("text", "")
        kw.setdefault("fg_color", "transparent")
        super().__init__(parent, **_tr(kw, drop=_DROP_LABEL))

    def configure(self, **kw):
        try:
            super().configure(**_tr(kw, drop=_DROP_LABEL))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)


# ── Button ────────────────────────────────────────────────────────────────────

class Button(ctk.CTkButton):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 6)
        kw.setdefault("border_width", 0)
        super().__init__(parent, **_tr(kw))  # padx/pady dropped (CTkButton unsupported)

    def configure(self, **kw):
        try:
            super().configure(**_tr(kw))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)


# ── Entry ─────────────────────────────────────────────────────────────────────

class Entry(ctk.CTkEntry):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 6)
        kw.setdefault("border_width", 1)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        try:
            super().configure(**_tr(kw))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)


# ── Text (Textbox) ────────────────────────────────────────────────────────────

class Text(ctk.CTkTextbox):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 6)
        kw.pop("yscrollcommand", None)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        kw.pop("yscrollcommand", None)
        try:
            super().configure(**_tr(kw))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)

    @property
    def yview(self):
        return self._textbox.yview

    def tag_configure(self, *args, **kw):
        self._textbox.tag_configure(*args, **kw)

    def tag_add(self, *args, **kw):
        self._textbox.tag_add(*args, **kw)

    def tag_remove(self, *args, **kw):
        self._textbox.tag_remove(*args, **kw)


# ── ScrolledText ──────────────────────────────────────────────────────────────

class ScrolledText(ctk.CTkTextbox):
    def __init__(self, parent=None, **kw):
        kw.setdefault("corner_radius", 6)
        kw.pop("yscrollcommand", None)
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        kw.pop("yscrollcommand", None)
        try:
            super().configure(**_tr(kw))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)

    def tag_configure(self, *args, **kw):
        self._textbox.tag_configure(*args, **kw)

    def tag_add(self, *args, **kw):
        self._textbox.tag_add(*args, **kw)

    def tag_remove(self, *args, **kw):
        self._textbox.tag_remove(*args, **kw)


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
        try:
            super().configure(**_tr(kw))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)


# ── Radiobutton ───────────────────────────────────────────────────────────────

class Radiobutton(ctk.CTkRadioButton):
    def __init__(self, parent=None, **kw):
        super().__init__(parent, **_tr(kw))

    def configure(self, **kw):
        try:
            super().configure(**_tr(kw))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)


# ── Scrollbar ─────────────────────────────────────────────────────────────────

class Scrollbar(ctk.CTkScrollbar):
    def __init__(self, parent=None, **kw):
        kw.pop("troughcolor", None)
        super().__init__(parent, **_tr(kw, _SCROLLBAR_RENAME))

    def configure(self, **kw):
        kw.pop("troughcolor", None)
        try:
            super().configure(**_tr(kw, _SCROLLBAR_RENAME))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)


# ── Combobox ──────────────────────────────────────────────────────────────────

class Combobox(ctk.CTkComboBox):
    def __init__(self, parent=None, **kw):
        kw.pop("postcommand", None)
        kw.pop("exportselection", None)
        super().__init__(parent, **_tr(kw, _COMBOBOX_RENAME))

    def configure(self, **kw):
        kw.pop("postcommand", None)
        kw.pop("exportselection", None)
        try:
            super().configure(**_tr(kw, _COMBOBOX_RENAME))
        except Exception:
            pass

    def config(self, **kw):
        self.configure(**kw)

    def current(self, idx=None):
        if idx is None:
            vals = self.cget("values")
            cur  = self.get()
            return list(vals).index(cur) if cur in vals else -1
        vals = list(self.cget("values"))
        if vals and idx < len(vals):
            self.set(vals[idx])
