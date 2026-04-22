# -*- coding: utf-8 -*-
"""ui/icons.py - High-quality PIL icon set for Synthex (4x super-sampled)."""

import math
from PIL import Image, ImageDraw, ImageFilter

_S  = 20
_P  = 3
_SS = 4   # super-sample multiplier


def _new(size):
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    return img, draw


def _render(fn, color, size):
    """Draw at 4x, scale down with LANCZOS for crisp anti-aliased result."""
    S4 = size * _SS
    img, d = _new(S4)
    fn(d, color, S4)
    return img.resize((size, size), Image.LANCZOS)


def _c(color, alpha=255):
    r, g, b = color[:3]
    return (r, g, b, alpha)


def _lighter(color, amt=60):
    return tuple(min(255, v + amt) for v in color[:3]) + (255,)


def _darker(color, amt=60):
    return tuple(max(0, v - amt) for v in color[:3]) + (255,)


# ── Icon draw functions (all work at arbitrary S, using fractions) ────────────

def _draw_home(d, c, S):
    p = S // 8
    m = S // 2
    # Roof (filled triangle)
    d.polygon([(m, p), (p + 1, m + S // 10), (S - p - 1, m + S // 10)], fill=_c(c))
    # Body
    bw = S // 5
    d.rectangle([m - bw, m + S // 10, m + bw, S - p], fill=_c(c))
    # Door cutout
    door_c = _darker(c, 80)
    dw = bw // 2
    d.rectangle([m - dw, m + S // 6, m + dw, S - p], fill=door_c)
    # Windows
    wy = m + S // 12
    for wx in [m - bw + S // 12, m + S // 12]:
        wsize = S // 8
        d.rectangle([wx, wy, wx + wsize, wy + wsize], fill=_lighter(c, 80))


def _draw_web(d, c, S):
    p = S // 8
    m = S // 2
    w = 3 * _SS
    # Outer circle
    d.ellipse([p, p, S - p, S - p], outline=_c(c), width=w)
    # Vertical meridian
    d.line([(m, p + w), (m, S - p - w)], fill=_c(c), width=w)
    # Horizontal equator
    d.line([(p + w, m), (S - p - w, m)], fill=_c(c), width=w)
    # Upper latitude arc
    arc_pad = int((m - p) * 0.45)
    d.arc([p + arc_pad, p + arc_pad // 2, S - p - arc_pad, m - 1],
          0, 180, fill=_c(c), width=w)
    # Lower latitude arc
    d.arc([p + arc_pad, m + 1, S - p - arc_pad, S - p - arc_pad // 2],
          0, 180, fill=_c(c), width=w)


def _draw_spy(d, c, S):
    p = S // 8
    m = S // 2
    # Eye white fill
    pts_top = [(p, m)]
    pts_bot = [(S - p, m)]
    steps = 30
    for i in range(steps + 1):
        t = i / steps
        x = p + (S - 2 * p) * t
        y_top = m - int((m - p) * math.sin(math.pi * t) * 0.55)
        y_bot = m + int((m - p) * math.sin(math.pi * t) * 0.55)
        pts_top.append((x, y_top))
        pts_bot.append((x, y_bot))
    pts_top.append((S - p, m))
    full_eye = pts_top + list(reversed(pts_bot[1:-1]))
    d.polygon(full_eye, fill=_c(c, 30), outline=_c(c), width=2 * _SS)
    # Iris
    r = S // 5
    d.ellipse([m - r, m - r, m + r, m + r], fill=_c(c))
    # Pupil
    r2 = r // 2
    pupil_c = _darker(c, 100)
    d.ellipse([m - r2, m - r2, m + r2, m + r2], fill=pupil_c)
    # Highlight
    hx = m - r // 3; hy = m - r // 3; hs = r // 3
    d.ellipse([hx, hy, hx + hs, hy + hs], fill=(255, 255, 255, 200))


def _draw_record(d, c, S):
    p = S // 8
    m = S // 2
    w = 3 * _SS
    # Outer ring
    d.ellipse([p, p, S - p, S - p], outline=_c(c, 80), width=w)
    # Middle ring
    gap = S // 6
    d.ellipse([p + gap, p + gap, S - p - gap, S - p - gap],
              outline=_c(c, 160), width=w)
    # Inner filled circle (REC dot)
    r = S // 5
    d.ellipse([m - r, m - r, m + r, m + r], fill=_c(c))


def _draw_schedule(d, c, S):
    p = S // 8
    w = 2 * _SS
    # Calendar body
    d.rounded_rectangle([p, p + S // 6, S - p, S - p], radius=S // 10,
                         outline=_c(c), width=w)
    # Header filled area
    d.rounded_rectangle([p + w, p + S // 6 + w, S - p - w, p + S // 3],
                         radius=S // 12, fill=_c(c))
    # Binding pegs
    for bx in [S // 3, 2 * S // 3]:
        d.rounded_rectangle([bx - S // 16, p, bx + S // 16, p + S // 5],
                             radius=S // 20, fill=_c(c))
    # Grid dots (days)
    dot_r = S // 20
    for row in range(2):
        for col in range(3):
            dx = p + S // 8 + col * (S - 2 * p - S // 4) // 2
            dy = p + S // 3 + S // 10 + row * (S // 7)
            d.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=_c(c))


def _draw_sheet(d, c, S):
    p = S // 8
    w = 2 * _SS
    # Outer border
    d.rounded_rectangle([p, p, S - p, S - p], radius=S // 12,
                         outline=_c(c), width=w)
    cw = (S - 2 * p) // 3
    rh = (S - 2 * p) // 4
    # Header row filled
    d.rounded_rectangle([p + w, p + w, S - p - w, p + rh],
                         radius=S // 16, fill=_c(c))
    # Column dividers
    for i in [1, 2]:
        x = p + i * cw
        d.line([(x, p + rh + w), (x, S - p - w)], fill=_c(c, 140), width=w)
    # Row dividers
    for i in [1, 2, 3]:
        y = p + i * rh
        d.line([(p + w, y), (S - p - w, y)], fill=_c(c, 100), width=w)
    # Cell fills (mini data bars)
    for col in range(3):
        for row in range(1, 3):
            bx = p + col * cw + cw // 4
            by = p + row * rh + rh // 4
            bw2 = int(cw * 0.5 * (1 - col * 0.25))
            d.rounded_rectangle([bx, by, bx + bw2, by + rh // 2],
                                 radius=S // 30, fill=_c(c, 80))


def _draw_rekening(d, c, S):
    p = S // 8
    w = 2 * _SS
    # Card body
    d.rounded_rectangle([p, p + S // 8, S - p, S - p - S // 8],
                         radius=S // 8, outline=_c(c), width=w)
    # Chip (square with rounded corners)
    cx = p + S // 5; cy = S // 2 - S // 8
    cs = S // 5
    d.rounded_rectangle([cx, cy, cx + cs, cy + cs],
                         radius=S // 16, outline=_c(c), width=w)
    # Chip lines
    mid_cx = cx + cs // 2
    d.line([(mid_cx, cy), (mid_cx, cy + cs)], fill=_c(c), width=w // 2)
    d.line([(cx, cy + cs // 2), (cx + cs, cy + cs // 2)], fill=_c(c), width=w // 2)
    # Magnetic stripe
    d.rectangle([p + w, p + S // 8 + w, S - p - w, p + S // 8 + S // 6],
                fill=_c(c, 160))
    # Contactless arcs
    arc_x = S - p - S // 6
    arc_y = S // 2
    for r in [S // 12, S // 8, S // 6]:
        d.arc([arc_x - r, arc_y - r, arc_x + r, arc_y + r],
              -50, 50, fill=_c(c, 180), width=w)


def _draw_history(d, c, S):
    p = S // 8
    w = 2 * _SS
    m = S // 2
    # Clock circle
    d.ellipse([p, p, S - p, S - p], outline=_c(c), width=w)
    # Hour hand
    d.line([(m, m), (m, p + S // 6)], fill=_c(c), width=w)
    # Minute hand (pointing right)
    d.line([(m, m), (S - p - S // 6, m)], fill=_c(c), width=w)
    # Center dot
    r = S // 16
    d.ellipse([m - r, m - r, m + r, m + r], fill=_c(c))
    # Counter-clockwise arrow arc at bottom-left
    d.arc([p + w, p + w, S - p - w, S - p - w], 120, 210,
          fill=_c(c, 180), width=w)
    ax = p + S // 5; ay = S - p - S // 5
    d.polygon([(ax - S // 16, ay), (ax + S // 16, ay - S // 10), (ax + S // 16, ay + S // 10)],
              fill=_c(c, 180))


def _draw_settings(d, c, S):
    m = S // 2
    w = 2 * _SS
    teeth = 8
    ro = m - S // 10
    ri = m - S // 5
    pts = []
    for i in range(teeth * 2):
        a = math.pi * 2 * i / (teeth * 2) - math.pi / 2
        r = ro if (i % 2 == 0) else ri
        pts.append((m + r * math.cos(a), m + r * math.sin(a)))
    d.polygon(pts, fill=_c(c))
    # Inner ring
    rh = m - S // 3
    d.ellipse([m - rh, m - rh, m + rh, m + rh], fill=(0, 0, 0, 0))
    # Re-draw hole clearly
    d.ellipse([m - rh + w, m - rh + w, m + rh - w, m + rh - w], fill=_c(c, 60))
    # Center dot
    rc = S // 16
    d.ellipse([m - rc, m - rc, m + rc, m + rc], fill=_c(c))


def _draw_templates(d, c, S):
    p = S // 8
    w = 2 * _SS
    # Back page (shadow)
    d.rounded_rectangle([p + S // 6, p, S - p, S - p - S // 6],
                         radius=S // 12, fill=_c(c, 50), outline=_c(c, 100), width=w)
    # Middle page
    d.rounded_rectangle([p + S // 12, p + S // 12, S - p - S // 12, S - p - S // 12],
                         radius=S // 12, fill=_c(c, 80), outline=_c(c, 150), width=w)
    # Front page
    d.rounded_rectangle([p, p + S // 6, S - p - S // 6, S - p],
                         radius=S // 12, fill=_c(c, 200), outline=_c(c), width=w)
    # Lines on front page
    lx0 = p + S // 8; lx1 = S - p - S // 4
    for ly in [p + S // 3, p + S // 2, p + int(S * 0.62)]:
        d.rounded_rectangle([lx0, ly, lx1, ly + w], radius=w // 2, fill=_c(c))
    # Fold corner
    fc = S - p - S // 6
    ft = p + S // 6
    d.polygon([(fc - S // 8, ft), (fc, ft + S // 8), (fc, ft)], fill=_c(c, 120))


def _draw_logs(d, c, S):
    p = S // 8
    w = 2 * _SS
    # Terminal window rounded
    d.rounded_rectangle([p, p, S - p, S - p], radius=S // 10,
                         outline=_c(c), width=w)
    # Title bar
    d.rounded_rectangle([p + w, p + w, S - p - w, p + S // 5],
                         radius=S // 12, fill=_c(c, 180))
    # Traffic dots
    dot_r = S // 20
    for i, dc in enumerate([(255, 80, 80, 255), (255, 200, 0, 255), (80, 200, 80, 255)]):
        dx = p + S // 8 + i * S // 7
        dy = p + S // 10 + S // 20
        d.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=dc)
    # Prompt ">"
    prompt_y = p + S // 4
    d.polygon([(p + S // 8, prompt_y),
               (p + S // 5, prompt_y + S // 12),
               (p + S // 8, prompt_y + S // 6)], fill=_c(c))
    # Code lines
    for i, line_len in enumerate([0.45, 0.3, 0.55]):
        ly = prompt_y + S // 10 + i * S // 9
        d.rounded_rectangle([p + S // 5, ly,
                              p + S // 5 + int((S - 2 * p) * line_len), ly + w],
                             radius=w // 2, fill=_c(c, 160 - i * 30))


def _draw_monitor(d, c, S):
    p = S // 8
    w = 2 * _SS
    m = S // 2
    # Monitor bezel
    d.rounded_rectangle([p, p, S - p, S - p - S // 5],
                         radius=S // 10, outline=_c(c), width=w)
    # Screen area
    screen_top = p + S // 8
    screen_bot = S - p - S // 5 - S // 10
    # Chart line (rising)
    points = []
    n = 6
    for i in range(n):
        px = p + S // 8 + i * (S - 2 * p - S // 4) // (n - 1)
        vals = [0.7, 0.4, 0.8, 0.3, 0.9, 0.5]
        py = screen_bot - int((screen_bot - screen_top) * vals[i])
        points.append((px, py))
    for i in range(len(points) - 1):
        d.line([points[i], points[i + 1]], fill=_c(c), width=w)
    # Area fill under line
    fill_pts = [points[0]] + points + [(points[-1][0], screen_bot), (points[0][0], screen_bot)]
    d.polygon(fill_pts, fill=_c(c, 40))
    # Stand
    d.rectangle([m - w, S - p - S // 5, m + w, S - p - S // 10], fill=_c(c))
    d.rounded_rectangle([m - S // 6, S - p - S // 10, m + S // 6, S - p],
                         radius=w, fill=_c(c))


def _draw_remote(d, c, S):
    p = S // 8
    w = 2 * _SS
    m = S // 2
    # Phone body
    pw = S // 3
    d.rounded_rectangle([m - pw // 2, p, m + pw // 2, S - p],
                         radius=S // 8, outline=_c(c), width=w)
    # Screen
    sw = pw - S // 6
    d.rounded_rectangle([m - sw // 2, p + S // 8, m + sw // 2, S - p - S // 8],
                         radius=S // 16, fill=_c(c, 60))
    # Notch/camera
    nc = S // 20
    d.ellipse([m - nc, p + S // 20, m + nc, p + S // 10], fill=_c(c))
    # Home bar
    bw2 = S // 8
    d.rounded_rectangle([m - bw2, S - p - S // 12, m + bw2, S - p - S // 20],
                         radius=w, fill=_c(c))
    # Signal waves (top right)
    for r in [S // 10, S // 7]:
        d.arc([m + pw // 4 - r, p + w - r, m + pw // 4 + r, p + w + r],
              -60, 60, fill=_c(c, 160), width=w)


def _draw_chat(d, c, S):
    p = S // 8
    w = 2 * _SS
    # Main bubble
    d.rounded_rectangle([p, p, S - p, S - p - S // 5],
                         radius=S // 8, fill=_c(c, 220), outline=_c(c), width=w)
    # Tail
    tail_x = p + S // 4
    tail_y = S - p - S // 5
    d.polygon([(tail_x, tail_y),
               (tail_x - S // 8, S - p),
               (tail_x + S // 6, tail_y)], fill=_c(c, 220))
    # Message dots
    m = S // 2
    dot_r = S // 16
    for dx in [-S // 7, 0, S // 7]:
        cy = S // 2 - S // 12
        d.ellipse([m + dx - dot_r, cy - dot_r, m + dx + dot_r, cy + dot_r],
                  fill=_darker(c, 60))


def _draw_blog(d, c, S):
    p = S // 8
    w = 2 * _SS
    # Newspaper body
    d.rounded_rectangle([p, p, S - p, S - p], radius=S // 12,
                         outline=_c(c), width=w)
    # Header image block
    d.rounded_rectangle([p + w, p + w, S - p - w, p + S // 4],
                         radius=S // 16, fill=_c(c, 180))
    # Title line (thick)
    d.rounded_rectangle([p + S // 8, p + S // 4 + S // 12,
                          S - p - S // 8, p + S // 4 + S // 8],
                         radius=w, fill=_c(c))
    # Body text lines
    for i, ll in enumerate([0.75, 0.55, 0.65]):
        ly = p + S // 4 + S // 5 + i * S // 9
        d.rounded_rectangle([p + S // 8, ly,
                              p + S // 8 + int((S - 2 * p - S // 4) * ll), ly + w],
                             radius=w // 2, fill=_c(c, 120 - i * 20))


def _draw_inbox(d, c, S):
    p = S // 8
    w = 2 * _SS
    m = S // 2
    # Envelope body
    d.rounded_rectangle([p, p + S // 6, S - p, S - p],
                         radius=S // 10, fill=_c(c, 30), outline=_c(c), width=w)
    # Flap (V-shape)
    flap_top = p + S // 6
    d.polygon([(p + w, flap_top),
               (m, m + S // 8),
               (S - p - w, flap_top)], outline=_c(c), width=w)
    # Notification badge
    bx = S - p - S // 6; by = p
    br = S // 8
    d.ellipse([bx - br, by, bx + br, by + 2 * br], fill=(255, 60, 60, 255))
    # Badge number
    d.line([(bx, by + br // 2), (bx, by + br + br // 2)], fill=(255, 255, 255, 255), width=w)


def _draw_master(d, c, S):
    p = S // 8
    m = S // 2
    # Crown
    d.polygon([
        (p, S - p - S // 6),
        (p + S // 6, m - S // 8),
        (m - S // 8, m + S // 8),
        (m, p + S // 8),
        (m + S // 8, m + S // 8),
        (S - p - S // 6, m - S // 8),
        (S - p, S - p - S // 6),
    ], fill=_c(c))
    # Base bar
    d.rounded_rectangle([p, S - p - S // 5, S - p, S - p],
                         radius=S // 16, fill=_c(c))
    # Jewels
    for dx, jc in [(-S // 5, (255, 80, 80, 255)),
                   (0,       (255, 220, 60, 255)),
                   (S // 5,  (80, 180, 255, 255))]:
        jr = S // 20
        jy = S - p - S // 10
        d.ellipse([m + dx - jr, jy - jr, m + dx + jr, jy + jr], fill=jc)


# ── Registry ──────────────────────────────────────────────────────────────────

_ICON_FN = {
    "home":      _draw_home,
    "web":       _draw_web,
    "spy":       _draw_spy,
    "record":    _draw_record,
    "schedule":  _draw_schedule,
    "sheet":     _draw_sheet,
    "rekening":  _draw_rekening,
    "history":   _draw_history,
    "settings":  _draw_settings,
    "templates": _draw_templates,
    "logs":      _draw_logs,
    "monitor":   _draw_monitor,
    "remote":    _draw_remote,
    "chat":      _draw_chat,
    "blog":      _draw_blog,
    "inbox":     _draw_inbox,
    "master":    _draw_master,
}


def generate_all_icons(size=20, color=(108, 74, 255), keys=None):
    """Return {key: PIL.Image}. Pass keys=[...] to generate only specific icons."""
    targets = keys if keys else list(_ICON_FN.keys())
    result = {}
    for key in targets:
        fn = _ICON_FN.get(key)
        if fn is None:
            continue
        try:
            result[key] = _render(fn, color, size)
        except Exception:
            img, _ = _new(size)
            result[key] = img
    return result


def generate_all_icons_glow(size=20, color=(108, 74, 255), glow_color=(140, 106, 255)):
    """Same icons with a soft outer glow — for active/hover state."""
    base = generate_all_icons(size, color)
    result = {}
    for key, img in base.items():
        try:
            glow = img.filter(ImageFilter.GaussianBlur(1.8))
            combined = Image.alpha_composite(glow, img)
            result[key] = combined
        except Exception:
            result[key] = img
    return result
