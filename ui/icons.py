# -*- coding: utf-8 -*-
"""ui/icons.py - PIL-generated icon set for Synthex sidebar & UI."""

import math
from PIL import Image, ImageDraw, ImageFilter

# Default sizes
_S  = 20   # icon canvas size
_P  = 3    # padding from edge


def _new(size=_S):
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    return img, draw


def _icon_home(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7); m = s // 2
    # roof triangle
    d.polygon([(m, p), (p, m + 1), (s - p, m + 1)], fill=c)
    # body
    d.rectangle([p + 3, m, s - p - 3, s - p - 1], fill=c)
    # door cutout (darker)
    dc = tuple(max(0, v - 60) for v in c[:3]) + (255,)
    d.rectangle([m - 2, m + 3, m + 2, s - p - 1], fill=dc)
    return img


def _icon_web(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7); m = s // 2
    d.ellipse([p, p, s - p, s - p], outline=c, width=2)
    d.line([(m, p + 1), (m, s - p - 1)], fill=c, width=1)
    d.line([(p + 1, m), (s - p - 1, m)], fill=c, width=1)
    # latitude ellipse
    ry = max(1, (m - p) // 3)
    d.ellipse([p + 2, m - ry, s - p - 2, m + ry], outline=c, width=1)
    return img


def _icon_spy(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7); m = s // 2
    # eye outline
    pts = [(p, m)]
    for i in range(20):
        a = math.pi * i / 19
        x = p + (s - 2*p) * i / 19
        y = m + int((m - p - 1) * math.sin(a) * 0.6)
        pts.append((x, y))
    pts.append((s - p, m))
    for i in range(20):
        a = math.pi * (19 - i) / 19
        x = p + (s - 2*p) * (19 - i) / 19
        y = m - int((m - p - 1) * math.sin(a) * 0.6)
        pts.append((x, y))
    d.polygon(pts, outline=c, width=1)
    r = max(2, s // 6)
    d.ellipse([m - r, m - r, m + r, m + r], fill=c)
    return img


def _icon_record(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7); m = s // 2
    # outer ring
    d.ellipse([p, p, s - p, s - p], outline=c, width=2)
    # inner filled circle
    r = max(3, s // 4)
    d.ellipse([m - r, m - r, m + r, m + r], fill=c)
    return img


def _icon_schedule(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    # calendar body
    d.rectangle([p, p + 3, s - p, s - p], outline=c, width=1)
    # top bar
    d.rectangle([p, p + 3, s - p, p + 6], fill=c)
    # binding tabs
    m3 = s // 3; m23 = 2 * s // 3
    for bx in [m3, m23]:
        d.rectangle([bx - 1, p, bx + 1, p + 5], fill=c)
    # grid lines
    mid_y = (p + 6 + s - p) // 2
    d.line([(p + 2, mid_y), (s - p - 2, mid_y)], fill=c, width=1)
    d.line([(s // 2, p + 7), (s // 2, s - p - 2)], fill=c, width=1)
    return img


def _icon_sheet(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    d.rectangle([p, p, s - p, s - p], outline=c, width=1)
    # column lines
    cw = (s - 2*p) // 3
    for i in range(1, 3):
        x = p + i * cw
        d.line([(x, p), (x, s - p)], fill=c, width=1)
    # row lines
    rh = (s - 2*p) // 4
    for i in range(1, 4):
        y = p + i * rh
        d.line([(p, y), (s - p, y)], fill=c, width=1)
    # header fill
    d.rectangle([p + 1, p + 1, s - p - 1, p + rh - 1], fill=c)
    return img


def _icon_rekening(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    # card shape
    d.rectangle([p, p + 2, s - p, s - p - 2], outline=c, width=1)
    # magnetic stripe
    d.rectangle([p + 1, p + 5, s - p - 1, p + 8], fill=c)
    # chip
    d.rectangle([p + 3, p + 10, p + 8, s - p - 4], outline=c, width=1)
    # dots (contactless)
    for i in range(3):
        r = 2 + i * 2
        d.arc([s - p - 3 - r, (s // 2) - r,
               s - p - 3 + r, (s // 2) + r], -90, 90, fill=c, width=1)
    return img


def _icon_history(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    # clipboard body
    d.rectangle([p + 2, p + 2, s - p - 2, s - p], outline=c, width=1)
    # clip at top
    d.rectangle([s // 2 - 3, p, s // 2 + 3, p + 4], fill=c)
    # lines
    for i, y in enumerate([p + 7, p + 10, p + 13]):
        w = s - 2*p - 6 - (i * 3)
        d.line([(p + 4, y), (p + 4 + w, y)], fill=c, width=1)
    return img


def _icon_settings(c, s=_S):
    img, d = _new(s)
    m = s // 2
    # outer gear
    teeth = 8; ro = m - 3; ri = m - 5
    pts = []
    for i in range(teeth * 2):
        a = math.pi * 2 * i / (teeth * 2)
        r = ro if (i % 2 == 0) else ri
        pts.append((m + r * math.cos(a), m + r * math.sin(a)))
    d.polygon(pts, fill=c)
    # inner hole
    rh = max(2, m // 3)
    d.ellipse([m - rh, m - rh, m + rh, m + rh],
              fill=(0, 0, 0, 0))
    return img


def _icon_templates(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    # stacked pages (back)
    d.rectangle([p + 4, p + 2, s - p, s - p - 2],
                outline=(*c[:3], 120), width=1)
    d.rectangle([p + 2, p + 4, s - p - 2, s - p],
                outline=(*c[:3], 160), width=1)
    # front page
    d.rectangle([p, p + 6, s - p - 4, s - p], outline=c, width=1)
    # lines on front page
    for y in [p + 9, p + 12]:
        d.line([(p + 2, y), (s - p - 6, y)], fill=c, width=1)
    return img


def _icon_logs(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    # terminal window
    d.rectangle([p, p, s - p, s - p], outline=c, width=1)
    # title bar
    d.rectangle([p + 1, p + 1, s - p - 1, p + 4], fill=c)
    # > prompt
    d.polygon([(p + 3, p + 8), (p + 6, p + 10), (p + 3, p + 12)], fill=c)
    # cursor line
    d.line([(p + 8, p + 10), (s - p - 4, p + 10)], fill=c, width=1)
    d.line([(p + 3, p + 14), (s - p - 6, p + 14)], fill=c, width=1)
    return img


def _icon_monitor(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    # chart area
    d.rectangle([p, p, s - p, s - p - 4], outline=c, width=1)
    # candlestick bars
    bars = [(p + 3, p + 8, p + 5, s - p - 6),
            (p + 7, p + 5, p + 9, s - p - 8),
            (p + 11, p + 9, p + 13, s - p - 5),
            (p + 15, p + 4, p + 17, s - p - 7)]
    for bx0, by0, bx1, by1 in bars:
        d.rectangle([bx0, by0, bx1, by1], fill=c)
    # stand
    d.line([(s // 2, s - p - 4), (s // 2, s - p)], fill=c, width=2)
    d.line([(s // 2 - 4, s - p), (s // 2 + 4, s - p)], fill=c, width=2)
    return img


def _icon_remote(c, s=_S):
    img, d = _new(s)
    m = s // 2
    # phone body
    d.rectangle([m - 4, _P, m + 4, s - _P], outline=c, width=1)
    # screen
    d.rectangle([m - 3, _P + 3, m + 3, s - _P - 5], fill=c)
    # home button
    r = 1
    d.ellipse([m - r, s - _P - 4, m + r, s - _P - 2], fill=c)
    return img


def _icon_chat(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    # bubble
    d.rounded_rectangle([p, p, s - p, s - p - 4],
                         radius=3, outline=c, width=1)
    # tail
    d.polygon([(p + 4, s - p - 4), (p + 2, s - p), (p + 8, s - p - 4)],
              fill=c)
    # dots inside
    m = s // 2
    for dx in [-4, 0, 4]:
        d.ellipse([m + dx - 1, m - 3, m + dx + 1, m - 1], fill=c)
    return img


def _icon_blog(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7)
    # newspaper body
    d.rectangle([p, p, s - p, s - p], outline=c, width=1)
    # header block
    d.rectangle([p + 2, p + 2, s - p - 2, p + 6], fill=c)
    # columns
    mid = s // 2
    for col_x0, col_x1 in [(p + 2, mid - 1), (mid + 1, s - p - 2)]:
        for y in [p + 9, p + 12, p + 15]:
            d.line([(col_x0, y), (col_x1, y)], fill=c, width=1)
    return img


def _icon_inbox(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7); m = s // 2
    # envelope body
    d.rectangle([p, p + 3, s - p, s - p], outline=c, width=1)
    # flap
    d.polygon([(p, p + 3), (m, m + 1), (s - p, p + 3)], outline=c, width=1)
    # notification dot
    d.ellipse([s - p - 5, p - 1, s - p - 1, p + 3],
              fill=(255, 80, 80, 255))
    return img


def _icon_master(c, s=_S):
    img, d = _new(s)
    p = max(2, s // 7); m = s // 2
    # crown body
    d.polygon([
        (p, s - p - 2), (p, m - 1), (m - 4, m + 4),
        (m, p + 1), (m + 4, m + 4), (s - p, m - 1),
        (s - p, s - p - 2)
    ], fill=c)
    # base bar
    d.rectangle([p, s - p - 4, s - p, s - p], fill=c)
    # jewel dots
    for dx in [-5, 0, 5]:
        d.ellipse([m + dx - 1, s - p - 6,
                   m + dx + 1, s - p - 4],
                  fill=(255, 220, 80, 255))
    return img


# ── Generator ─────────────────────────────────────────────────────────────────
_ICON_FN = {
    "home":      _icon_home,
    "web":       _icon_web,
    "spy":       _icon_spy,
    "record":    _icon_record,
    "schedule":  _icon_schedule,
    "sheet":     _icon_sheet,
    "rekening":  _icon_rekening,
    "history":   _icon_history,
    "settings":  _icon_settings,
    "templates": _icon_templates,
    "logs":      _icon_logs,
    "monitor":   _icon_monitor,
    "remote":    _icon_remote,
    "chat":      _icon_chat,
    "blog":      _icon_blog,
    "inbox":     _icon_inbox,
    "master":    _icon_master,
}


def generate_all_icons(size=20, color=(108, 74, 255), keys=None):
    """Return {key: PIL.Image}. Pass keys=[...] to only generate specific icons."""
    targets = keys if keys else list(_ICON_FN.keys())
    result = {}
    for key in targets:
        fn = _ICON_FN.get(key)
        if fn is None:
            continue
        try:
            result[key] = fn(color, size)
        except Exception:
            img, d = _new(size)
            m = size // 2; r = size // 2 - 3
            d.ellipse([m - r, m - r, m + r, m + r], fill=color)
            result[key] = img
    return result


def generate_all_icons_glow(size=20, color=(108, 74, 255), glow_color=(140, 106, 255)):
    """Same icons with a subtle glow blur — for active/hover state."""
    base = generate_all_icons(size, color)
    result = {}
    for key, img in base.items():
        try:
            glow = img.filter(ImageFilter.GaussianBlur(1.5))
            combined = Image.alpha_composite(glow, img)
            result[key] = combined
        except Exception:
            result[key] = img
    return result
