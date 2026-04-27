# -*- coding: utf-8 -*-
"""test_all.py - Comprehensive automated test for all Synthex features."""
import ast, sys, os, threading, time, hashlib

# Fix Windows console encoding
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

results = []

def ok(name):
    results.append(("PASS", name))
    print("  [PASS] " + name)

def fail(name, e):
    results.append(("FAIL", name + " -> " + str(e)[:90]))
    print("  [FAIL] " + name + " -> " + str(e)[:90])

print("=" * 66)
print(" SYNTHEX - Automated Feature Test")
print("=" * 66)

# ─────────────────────────────────────────────────────────────────────
# T1: Syntax semua file Python utama
# ─────────────────────────────────────────────────────────────────────
print("\n[T1] Syntax check")
SYNTAX_FILES = [
    "ui/app.py",
    "ui/spy_window.py",
    "modules/macro/simple_recorder.py",
    "modules/macro/smart_macro.py",
    "modules/price_monitor.py",
    "modules/rekening.py",
    "modules/sheets/connector.py",
    "modules/remote_control.py",
    "modules/remote_macro.py",
    "modules/synthex_bridge.py",
    "modules/web_scraper.py",
    "modules/web_change_monitor.py",
]
for fp in SYNTAX_FILES:
    try:
        with open(fp, "r", encoding="utf-8") as f:
            ast.parse(f.read())
        ok("Syntax OK: " + fp)
    except Exception as e:
        fail("Syntax: " + fp, e)

# ─────────────────────────────────────────────────────────────────────
# T2: SimpleRecorder
# ─────────────────────────────────────────────────────────────────────
print("\n[T2] SimpleRecorder")
try:
    from modules.macro.simple_recorder import SimpleRecorder
    sr = SimpleRecorder()
    cases = [
        ({"type":"click","x":10,"y":20,"button":"left","delay":0.5,
          "uia":{"name":"Masuk","aid":"btn1","cls":"Button","ctrl":50000}}, "Click"),
        ({"type":"click","x":10,"y":20,"button":"left","delay":0.5}, "Click"),
        ({"type":"type","text":"Halo","delay":0.2}, "Type"),
        ({"type":"key","key":"enter","delay":0.1}, "Key"),
        ({"type":"scroll","x":10,"y":20,"amount":-3,"delay":0.1}, "Scroll"),
    ]
    for act, expected in cases:
        d = sr._action_desc(act)
        assert expected in d, "desc=" + d
    ok("_action_desc: semua 5 tipe OK")
except Exception as e:
    fail("SimpleRecorder._action_desc", e)

try:
    import modules.macro.simple_recorder as sr_mod

    class FakePG:
        FAILSAFE = False
        clicks = []
        def click(self, x, y, button="left"): self.clicks.append((x, y, button))
        def scroll(self, *a, **kw): pass
        def press(self, *a): pass
        def hotkey(self, *a): pass

    fpg = FakePG()
    sys.modules["pyautogui"] = fpg

    sr2 = SimpleRecorder()
    actions = [
        {"type":"click","x":100,"y":200,"button":"left","delay":0,
         "uia":{"aid":"btnTest","name":"Test","ctrl":50000}},
        {"type":"click","x":300,"y":400,"button":"left","delay":0},
    ]
    stop = threading.Event()
    sr2.play_recording(actions, stop_event=stop)
    assert fpg.clicks[0][:2] == (100, 200)
    assert fpg.clicks[1][:2] == (300, 400)
    ok("play_recording: koordinat rekaman dipakai langsung (2 klik)")
except Exception as e:
    fail("SimpleRecorder.play_recording", e)

# ─────────────────────────────────────────────────────────────────────
# T3: SpyWindow UIA
# ─────────────────────────────────────────────────────────────────────
print("\n[T3] SpyWindow UIA")
try:
    with open("ui/spy_window.py", "r", encoding="utf-8") as f:
        spy_src = f.read()
    required = ["_init_uia", "_get_uia_info", "_build_uia_selector",
                "_uia_loop", "_show_entry_detail", "_copy_as_step", "_save_coord"]
    missing = [fn for fn in required if fn not in spy_src]
    assert not missing, "Missing: " + str(missing)
    ok("Semua fungsi UIA ada (" + str(len(required)) + " fungsi)")
except Exception as e:
    fail("SpyWindow fungsi check", e)

try:
    from ui.spy_window import _init_uia, _build_uia_selector
    uia = _init_uia()
    assert uia is not None
    ok("_init_uia: IUIAutomation singleton OK")
    s = _build_uia_selector(50000, "button", "btnSubmit", "", "Kirim")
    assert "#btnSubmit" in s, s
    ok("_build_uia_selector (aid): " + s)
    s2 = _build_uia_selector(50004, "edit", "", "RichEditD2DPT", "")
    assert "input" in s2 or "RichEdit" in s2, s2
    ok("_build_uia_selector (cls): " + s2)
    s3 = _build_uia_selector(50000, "button", "", "", "Cari")
    assert "Cari" in s3 or "button" in s3, s3
    ok("_build_uia_selector (name): " + s3)
except Exception as e:
    fail("SpyWindow._init_uia / _build_uia_selector", e)

# ─────────────────────────────────────────────────────────────────────
# T4: Rekening
# ─────────────────────────────────────────────────────────────────────
print("\n[T4] Rekening")
try:
    from modules.rekening import check_rekening, BANK_CODES, EWALLETS, _BASE_DEFAULT
    r = check_rekening("BCA", "123", api_key="TEST")
    assert "tidak valid" in r["status"].lower(), r
    ok("Nomor pendek ditolak: " + r["status"])
    r2 = check_rekening("BCA", "", api_key="TEST")
    assert "tidak valid" in r2["status"].lower(), r2
    ok("Nomor kosong ditolak: " + r2["status"])
    assert "BCA" in BANK_CODES and "BRI" in BANK_CODES and "MANDIRI" in BANK_CODES
    ok("BANK_CODES: {} bank terdaftar".format(len(BANK_CODES)))
    assert "DANA" in EWALLETS and "OVO" in EWALLETS and "GOPAY" in EWALLETS
    ok("EWALLETS: {} provider terdaftar".format(len(EWALLETS)))
    assert "apivalidasi" in _BASE_DEFAULT or "http" in _BASE_DEFAULT
    ok("_BASE_DEFAULT URL OK: " + _BASE_DEFAULT[:40])
except Exception as e:
    fail("Rekening", e)

# ─────────────────────────────────────────────────────────────────────
# T5: PriceMonitor
# ─────────────────────────────────────────────────────────────────────
print("\n[T5] PriceMonitor")
try:
    from modules.price_monitor import PriceMonitor, _find_chrome, _free_port
    pm = PriceMonitor(on_status=lambda m: None)
    pm.configure(url="https://example.com", table_selector="table.harga",
                 mode="requests", interval_sec=300, worksheet="Harga")
    assert pm._cfg["url"] == "https://example.com"
    assert pm._cfg["interval_sec"] == 300
    ok("configure() parameter OK")
except Exception as e:
    fail("PriceMonitor.configure", e)

try:
    from bs4 import BeautifulSoup
    html = ("<table><tr><th>Produk</th><th>Harga</th></tr>"
            "<tr><td>Apel</td><td>Rp5.000</td></tr>"
            "<tr><td>Mangga</td><td>Rp8.000</td></tr></table>")
    tbl = BeautifulSoup(html, "html.parser").find("table")
    rows = PriceMonitor._parse_html_table(tbl)
    assert rows[0] == ["Produk", "Harga"]
    assert rows[1] == ["Apel", "Rp5.000"]
    ok("_parse_html_table: {} baris x {} kolom".format(len(rows), len(rows[0])))
except Exception as e:
    fail("PriceMonitor._parse_html_table", e)

try:
    ok("_find_chrome: " + ("ADA: " + _find_chrome() if _find_chrome() else "tidak ada (OK)"))
    port = _free_port()
    assert 1024 < port < 65535
    ok("_free_port: {} (valid)".format(port))
except Exception as e:
    fail("PriceMonitor utilities", e)

# ─────────────────────────────────────────────────────────────────────
# T6: WebScraper
# ─────────────────────────────────────────────────────────────────────
print("\n[T6] WebScraper")
try:
    from modules.web_scraper import _TextExtractor, scrape_url

    # Test HTML parser langsung
    parser = _TextExtractor()
    html = """<html><head><title>Test Halaman</title>
    <script>var x=1;</script><style>.a{color:red}</style></head>
    <body><nav>Menu</nav>
    <main><h1>Judul Utama</h1><p>Paragraf pertama</p>
    <p>Paragraf kedua dengan info penting</p></main>
    <footer>Footer nav</footer></body></html>"""
    parser.feed(html)
    assert parser.title == "Test Halaman", "title=" + parser.title
    ok("_TextExtractor: title='{}' OK".format(parser.title))

    text = parser.get_text()
    assert "Judul Utama" in text, "text=" + text[:100]
    assert "Paragraf pertama" in text
    ok("_TextExtractor: body text diekstrak, {} karakter".format(len(text)))

    # Pastikan script/style/nav/footer diabaikan
    assert "var x=1" not in text, "Script bocor ke output"
    assert "color:red" not in text, "Style bocor ke output"
    ok("_TextExtractor: script/style/nav/footer diabaikan")
except Exception as e:
    fail("WebScraper._TextExtractor", e)

try:
    # Test truncation
    from modules.web_scraper import _MAX_CHARS
    assert _MAX_CHARS >= 1000, "MAX_CHARS terlalu kecil: " + str(_MAX_CHARS)
    ok("_MAX_CHARS = {} (reasonable)".format(_MAX_CHARS))

    # Test callable
    assert callable(scrape_url)
    ok("scrape_url callable")
except Exception as e:
    fail("WebScraper constants/callable", e)

try:
    # Scrape real URL
    result = scrape_url("https://example.com", max_chars=500)
    assert len(result) > 10, "Hasil kosong"
    assert "terpotong" not in result or True  # OK baik terpotong atau tidak
    assert isinstance(result, str)
    ok("scrape_url('example.com'): {} karakter diterima".format(len(result)))
except Exception as e:
    fail("scrape_url live (network)", e)

# ─────────────────────────────────────────────────────────────────────
# T7: WebChangeMonitor
# ─────────────────────────────────────────────────────────────────────
print("\n[T7] WebChangeMonitor")
try:
    from modules.web_change_monitor import WebChangeMonitor, _short_diff

    # Test _short_diff
    old = "harga Rp 50.000\nstok tersedia\nwarna merah"
    new = "harga Rp 75.000\nstok tersedia\nwarna biru"
    diff = _short_diff(old, new)
    assert len(diff) > 0
    ok("_short_diff: '{}…'".format(diff[:60]))

    # Test _short_diff identik
    diff2 = _short_diff("sama", "sama")
    assert diff2 == "(konten berubah)" or diff2 == ""
    ok("_short_diff identik: '{}'".format(diff2))
except Exception as e:
    fail("WebChangeMonitor._short_diff", e)

try:
    statuses = []
    wcm = WebChangeMonitor(on_status=lambda m: statuses.append(m))
    wcm.configure(url="https://example.com", interval_sec=9999,
                  keyword="Example Domain", ai_analysis=False)
    assert wcm._cfg["url"] == "https://example.com"
    assert wcm._cfg["interval_sec"] == 9999
    assert wcm._cfg["keyword"] == "Example Domain"
    assert not wcm._cfg["ai_analysis"]
    ok("WebChangeMonitor.configure() OK")
except Exception as e:
    fail("WebChangeMonitor.configure", e)

try:
    # Test check_now — run one cycle, verify keyword detection
    changes = []
    wcm2 = WebChangeMonitor(
        on_status=lambda m: None,
        on_change=lambda old, new, s: changes.append(s))
    wcm2.configure(url="https://example.com",
                   keyword="Example Domain", ai_analysis=False)
    wcm2.check_now()   # first run sets baseline
    assert wcm2.check_count == 1
    assert wcm2._last_hash != ""
    ok("check_now baseline: hash='{}…' count={}".format(
        wcm2._last_hash[:8], wcm2.check_count))

    # Second run — same content, no change expected
    wcm2.check_now()
    assert wcm2.check_count == 2
    assert len(changes) == 0, "Harusnya tidak ada perubahan: " + str(changes)
    ok("check_now round 2: tidak ada perubahan (benar)")
except Exception as e:
    fail("WebChangeMonitor.check_now live", e)

try:
    # Test keyword disappear simulation (inject fake last state)
    changes3 = []
    wcm3 = WebChangeMonitor(
        on_status=lambda m: None,
        on_change=lambda old, new, s: changes3.append(s))
    wcm3.configure(url="https://example.com",
                   keyword="KATA_YANG_TIDAK_ADA_DI_HALAMAN_INI_XYZ123",
                   ai_analysis=False)
    # Force baseline to say keyword WAS found
    wcm3._last_content   = "keyword ada di sini KATA_YANG_TIDAK_ADA_DI_HALAMAN_INI_XYZ123"
    wcm3._last_hash      = hashlib.md5(wcm3._last_content.encode()).hexdigest()
    wcm3._last_kw_found  = True
    wcm3.check_count     = 1   # skip first_run
    wcm3._run_cycle(first_run=False)
    assert len(changes3) == 1, "Harusnya ada 1 perubahan (keyword hilang)"
    assert "HILANG" in changes3[0], changes3
    ok("keyword hilang terdeteksi: '{}'".format(changes3[0][:50]))
except Exception as e:
    fail("WebChangeMonitor keyword disappear", e)

# ─────────────────────────────────────────────────────────────────────
# T8: RemoteMacro fixes
# ─────────────────────────────────────────────────────────────────────
print("\n[T8] RemoteMacro")
try:
    from modules.remote_macro import MacroEngine

    class FakeAdb:
        calls = []
        available = True
        def _run(self, *args, **kw): self.calls.append(args); return (0, "", "")

    adb = FakeAdb()
    eng = MacroEngine(adb)
    assert eng._serial == ""
    assert eng._serial_fn is None
    ok("MacroEngine init: serial='', serial_fn=None")
except Exception as e:
    fail("MacroEngine init", e)

try:
    # Test serial_fn override
    adb2 = FakeAdb()
    eng2 = MacroEngine(adb2)
    eng2._serial_fn = lambda: "192.168.1.10:5555"

    rule = {"action": "tap", "x": 540, "y": 960, "enabled": True}
    eng2._execute(rule)
    assert any("-s" in str(c) and "192.168.1.10:5555" in str(c)
               for c in adb2.calls), str(adb2.calls)
    ok("serial_fn dinamis dipakai saat execute: 192.168.1.10:5555")
except Exception as e:
    fail("MacroEngine._serial_fn", e)

try:
    # Test ping reset timer
    adb3 = FakeAdb()
    eng3 = MacroEngine(adb3)
    eng3._last_activity = 0.0
    eng3.ping()
    assert eng3._last_activity > 0
    ok("ping() reset _last_activity")
except Exception as e:
    fail("MacroEngine.ping", e)

try:
    # Test semua action types
    adb4 = FakeAdb()
    eng4 = MacroEngine(adb4)
    eng4.set_serial("dev1")

    for action, extra in [
        ("tap",        {"x": 100, "y": 200}),
        ("swipe_down", {}),
        ("swipe_up",   {}),
        ("swipe_left", {}),
        ("swipe_right",{}),
        ("swipe_custom",{"x1":0,"y1":0,"x2":100,"y2":200,"ms":300}),
        ("key_home",   {}),
        ("key_back",   {}),
        ("key_wakeup", {}),
    ]:
        adb4.calls.clear()
        rule = dict(action=action, enabled=True, **extra)
        eng4._execute(rule)
        assert len(adb4.calls) >= 1, "Tidak ada call ADB untuk: " + action
    ok("Semua 9 action type memanggil ADB")
except Exception as e:
    fail("MacroEngine action types", e)

# ─────────────────────────────────────────────────────────────────────
# T9: SynthexBridge fixes
# ─────────────────────────────────────────────────────────────────────
print("\n[T9] SynthexBridge")
try:
    from modules.synthex_bridge import SynthexBridge

    bridge = SynthexBridge(adb_manager=None, port=18765)

    # running=False sebelum start
    assert not bridge.running
    ok("running=False sebelum start")

    # running check memeriksa thread juga
    import inspect
    src = inspect.getsource(SynthexBridge.running.fget)
    assert "_thread" in src and "is_alive" in src, "running tidak cek thread"
    ok("running property cek _thread.is_alive()")
except Exception as e:
    fail("SynthexBridge.running", e)

try:
    # Test tidak ada replace %s untuk teks
    import inspect
    from modules.synthex_bridge import SynthexBridge as _SB
    src = inspect.getsource(_SB.start)
    assert 'replace(" ", "%s")' not in src, "Bug %s masih ada di bridge"
    assert 'replace(" ", "%s")' not in src
    ok("synthex_bridge: tidak ada replace space→%s")
except Exception as e:
    fail("SynthexBridge no %s bug", e)

try:
    # Test executor ada
    b2 = SynthexBridge(port=18766)
    assert hasattr(b2, "_executor")
    import concurrent.futures
    assert isinstance(b2._executor, concurrent.futures.ThreadPoolExecutor)
    ok("SynthexBridge._executor ThreadPoolExecutor OK")
except Exception as e:
    fail("SynthexBridge executor", e)

# ─────────────────────────────────────────────────────────────────────
# T10: RemoteControl fixes
# ─────────────────────────────────────────────────────────────────────
print("\n[T10] RemoteControl")
try:
    import inspect
    from modules.remote_control import AdbManager
    src = inspect.getsource(AdbManager.install_companion)
    assert '"-d"' not in src and "'-d'" not in src, "Flag -d masih ada"
    ok("install_companion: flag -d sudah dihapus")
except Exception as e:
    fail("RemoteControl -d flag", e)

try:
    from modules.remote_control import AdbManager
    am = AdbManager()
    assert hasattr(am, "is_companion_installed")
    assert hasattr(am, "install_companion")
    assert hasattr(am, "launch_companion")
    assert hasattr(am, "get_companion_apk_path")
    ok("AdbManager companion methods semua ada (4 method)")
except Exception as e:
    fail("RemoteControl companion methods", e)

# ─────────────────────────────────────────────────────────────────────
# T11: SmartMacro scrape_url step
# ─────────────────────────────────────────────────────────────────────
print("\n[T11] SmartMacro scrape_url")
try:
    from modules.macro.smart_macro import SmartMacro
    sm = SmartMacro(engine=None)
    assert hasattr(sm, "_run_scrape_url")
    ok("SmartMacro._run_scrape_url ada")
except Exception as e:
    fail("SmartMacro._run_scrape_url exist", e)

try:
    from modules.macro.smart_macro import SmartMacro
    sm2 = SmartMacro(engine=None)
    variables = {}
    step = {"type": "scrape_url", "url": "https://example.com",
            "keyword": "", "var": "hasil_scrape"}
    result = sm2._run_scrape_url(step, variables)
    assert "hasil_scrape" in variables, "variabel tidak disimpan"
    assert len(variables["hasil_scrape"]) > 5, "konten kosong"
    assert "hasil_scrape" in result
    ok("scrape_url step live: {} chars → {{hasil_scrape}}".format(
        len(variables["hasil_scrape"])))
except Exception as e:
    fail("SmartMacro._run_scrape_url live", e)

try:
    from modules.macro.smart_macro import SmartMacro
    sm3 = SmartMacro(engine=None)
    variables = {}
    step = {"type": "scrape_url", "url": "https://example.com",
            "keyword": "Example Domain", "var": "filtered"}
    result = sm3._run_scrape_url(step, variables)
    assert "filtered" in variables
    content = variables["filtered"]
    assert "Example Domain" in content or "(keyword" in content
    ok("scrape_url + keyword filter: '{}'".format(content[:60]))
except Exception as e:
    fail("SmartMacro scrape_url keyword", e)

try:
    # URL kosong harus raise
    from modules.macro.smart_macro import SmartMacro
    sm4 = SmartMacro(engine=None)
    try:
        sm4._run_scrape_url({"url": "", "var": "x"}, {})
        fail("scrape_url URL kosong", Exception("Harusnya raise ValueError"))
    except ValueError:
        ok("scrape_url URL kosong → ValueError (benar)")
except Exception as e:
    fail("SmartMacro scrape_url empty URL", e)

# ─────────────────────────────────────────────────────────────────────
# T12: app.py feature completeness
# ─────────────────────────────────────────────────────────────────────
print("\n[T12] app.py structure & new features")
try:
    with open("ui/app.py", "r", encoding="utf-8") as f:
        app_src = f.read()

    nav_keys = ["home","web","spy","record","schedule","templates",
                "sheet","rekening","monitor","remote","history","logs","settings"]
    missing = [k for k in nav_keys if k not in app_src]
    assert not missing, "Missing nav: " + str(missing)
    ok("NAV: {} keys semua ada".format(len(nav_keys)))

    builders = ["_pg_home","_pg_web","_pg_spy","_pg_record","_pg_schedule",
                "_pg_sheet","_pg_rekening","_pg_monitor","_pg_remote",
                "_pg_history","_pg_logs","_pg_settings","_pg_ai_chat"]
    missing_b = [b for b in builders if b not in app_src]
    assert not missing_b, "Missing builders: " + str(missing_b)
    ok("Page builders: {} semua terdaftar".format(len(builders)))
except Exception as e:
    fail("app.py nav/builders", e)

try:
    with open("ui/app.py", "r", encoding="utf-8") as f:
        app_src = f.read()

    # AI Chat UX features
    ai_feats = [
        "_QUICK",           # quick prompt chips
        "↺  Ulangi jawaban",# regenerate button
        "_copy_fn",         # copy button
        "_animate_typing",  # animated dots
        "ts.*%H:%M",        # timestamp — pattern
        "_model_var",       # model switcher
        "char_var",         # char counter
        "_show_status",     # error toast
        "@url",             # scrape hint
    ]
    import re as _re
    missing_ai = [f for f in ai_feats
                  if not _re.search(f.replace(".*", ".*"), app_src)]
    assert not missing_ai, "Missing AI Chat features: " + str(missing_ai)
    ok("AI Chat: {} UX fitur semua ada".format(len(ai_feats)))
except Exception as e:
    fail("app.py AI Chat features", e)

try:
    with open("ui/app.py", "r", encoding="utf-8") as f:
        app_src = f.read()

    # Monitor tab baru
    monitor_feats = [
        "Tabel Otomatis",   # tab 1 label
        "Pantau Perubahan", # tab 2 label
        "WebChangeMonitor", # new monitor class
        "MULAI PANTAU",     # start button
        "CEK SEKARANG",     # one-shot button
        "_wcm",             # state variable
        "keyword",          # keyword field
        "Analisis perubahan dengan AI", # AI toggle
    ]
    missing_mon = [f for f in monitor_feats if f not in app_src]
    assert not missing_mon, "Missing Monitor features: " + str(missing_mon)
    ok("Monitor: {} fitur baru semua ada".format(len(monitor_feats)))
except Exception as e:
    fail("app.py Monitor new tab", e)

try:
    with open("ui/app.py", "r", encoding="utf-8") as f:
        app_src = f.read()

    # scrape_url di automation builder
    scrape_feats = [
        "scrape_url",       # step type
        "[SC]",             # icon
        "Scrape URL",       # display name
        "scraped_text",     # default variable name
        "Filter keyword",   # keyword field label
    ]
    missing_sc = [f for f in scrape_feats if f not in app_src]
    assert not missing_sc, "Missing scrape_url builder: " + str(missing_sc)
    ok("Automation scrape_url: {} elemen UI ada".format(len(scrape_feats)))
except Exception as e:
    fail("app.py scrape_url builder", e)

try:
    with open("ui/app.py", "r", encoding="utf-8") as f:
        app_src = f.read()

    # Remote fixes di app.py
    remote_feats = [
        "macro_engine.ping()",  # ping calls
        "_bridge_poll_id",      # bridge timer cancel
        "for _ns in new_devices",  # loop all devices
        "_serial_fn",           # dynamic serial
        "_get_mirror_serial",   # serial getter
    ]
    missing_rem = [f for f in remote_feats if f not in app_src]
    assert not missing_rem, "Missing remote fixes: " + str(missing_rem)
    ok("Remote fixes: {} semua ada di app.py".format(len(remote_feats)))
except Exception as e:
    fail("app.py remote fixes", e)

# ─────────────────────────────────────────────────────────────────────
# T13: app.py – no space→%s bug di _tap_input
# ─────────────────────────────────────────────────────────────────────
print("\n[T13] Bug fixes verifikasi")
try:
    with open("ui/app.py", "r", encoding="utf-8") as f:
        app_src = f.read()
    assert 'replace(" ", "%s")' not in app_src, "Bug %s masih ada di app.py"
    ok("app.py: tidak ada replace space→%s (bug teks terkirim)")
except Exception as e:
    fail("app.py no %s bug", e)

try:
    with open("modules/synthex_bridge.py", "r", encoding="utf-8") as f:
        bridge_src = f.read()
    assert 'replace(" ", "%s")' not in bridge_src
    ok("synthex_bridge.py: tidak ada replace space→%s")
except Exception as e:
    fail("synthex_bridge no %s bug", e)

try:
    with open("modules/remote_control.py", "r", encoding="utf-8") as f:
        rc_src = f.read()
    assert '"-d"' not in rc_src and "'-d'" not in rc_src
    ok("remote_control.py: flag -d sudah dihapus dari install")
except Exception as e:
    fail("remote_control -d removed", e)

try:
    with open("android_app/app/src/main/java/com/yohn18/synthex/MainActivity.kt") as f:
        kt_src = f.read()
    assert "isForMainFrame" in kt_src, "Fix onReceivedError belum ada"
    ok("MainActivity.kt: onReceivedError filter isForMainFrame OK")
except Exception as e:
    fail("MainActivity.kt onReceivedError fix", e)

# ─────────────────────────────────────────────────────────────────────
# T14: Sheets connector
# ─────────────────────────────────────────────────────────────────────
print("\n[T14] Sheets connector")
try:
    from modules.sheets.connector import extract_sheet_id
    sid = extract_sheet_id(
        "https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsT/edit#gid=0")
    assert sid == "1aBcDeFgHiJkLmNoPqRsT", sid
    ok("extract_sheet_id dari URL: " + sid)
    sid2 = extract_sheet_id("1aBcDeFgHiJkLmNoPqRsT")
    assert sid2 == "1aBcDeFgHiJkLmNoPqRsT"
    ok("extract_sheet_id dari plain ID")
    sid3 = extract_sheet_id("bukan-id-valid!!!")
    assert sid3 == "", sid3
    ok("extract_sheet_id: invalid → kosong")
except Exception as e:
    fail("Sheets.extract_sheet_id", e)

# ─────────────────────────────────────────────────────────────────────
# T15: EXE & Desktop shortcut
# ─────────────────────────────────────────────────────────────────────
print("\n[T15] EXE & Desktop shortcut")
try:
    import datetime
    exe = r"C:\Users\Admin\synthex\dist\Synthex.exe"
    assert os.path.exists(exe), "EXE tidak ada"
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(exe))
    size_mb = os.path.getsize(exe) / 1024 / 1024
    ok("EXE ada: {:.1f} MB, dibuat {}".format(size_mb, mtime.strftime("%Y-%m-%d %H:%M")))
except Exception as e:
    fail("EXE check", e)

try:
    import subprocess
    lnk = r"C:\Users\Admin\Desktop\Synthex.lnk"
    assert os.path.exists(lnk), "Shortcut tidak ada di Desktop"
    res = subprocess.run(
        ["powershell", "-Command",
         r'(New-Object -COM WScript.Shell).CreateShortcut("' + lnk + r'").TargetPath'],
        capture_output=True, text=True)
    target = res.stdout.strip()
    assert "Synthex.exe" in target and os.path.exists(target)
    ok("Desktop shortcut → " + target)
except Exception as e:
    fail("Desktop shortcut", e)

# ─────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────
passes = [r for r in results if r[0] == "PASS"]
fails  = [r for r in results if r[0] == "FAIL"]

print()
print("=" * 66)
print("  HASIL: {}/{} PASS   {} FAIL".format(
    len(passes), len(results), len(fails)))
if fails:
    print()
    print("  Item yang GAGAL:")
    for _, msg in fails:
        print("    - " + msg)
else:
    print("  Semua fitur lulus pengujian otomatis.")
print("=" * 66)

sys.exit(0 if not fails else 1)
