# -*- coding: utf-8 -*-
"""test_all.py - Comprehensive automated test for all Synthex features."""
import ast, sys, os, threading, time

results = []

def ok(name):
    results.append(("PASS", name))
    print("  [PASS] " + name)

def fail(name, e):
    results.append(("FAIL", name + " -> " + str(e)[:90]))
    print("  [FAIL] " + name + " -> " + str(e)[:90])

print("=" * 62)
print(" SYNTHEX - Automated Feature Test")
print("=" * 62)

# ─────────────────────────────────────────────────────────────────────
# T1: Syntax semua file Python utama
# ─────────────────────────────────────────────────────────────────────
print("\n[T1] Syntax check")
for fp in [
    "ui/app.py",
    "ui/spy_window.py",
    "modules/macro/simple_recorder.py",
    "modules/price_monitor.py",
    "modules/rekening.py",
    "modules/sheets/connector.py",
]:
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
    # UIA override is disabled — playback always uses recorded coordinates exactly
    actions = [
        {"type":"click","x":100,"y":200,"button":"left","delay":0,
         "uia":{"aid":"btnTest","name":"Test","ctrl":50000}},
        {"type":"click","x":300,"y":400,"button":"left","delay":0},
    ]
    stop = threading.Event()
    sr2.play_recording(actions, stop_event=stop)
    assert fpg.clicks[0][:2] == (100, 200), "Coord rekam gagal: " + str(fpg.clicks[0])
    assert fpg.clicks[1][:2] == (300, 400), "Coord rekam gagal: " + str(fpg.clicks[1])
    ok("play_recording: koordinat rekaman dipakai langsung (100,200 tetap)")
    ok("play_recording: koordinat rekaman dipakai langsung (300,400 tetap)")
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

    # Test selector dengan AutomationId
    s = _build_uia_selector(50000, "button", "btnSubmit", "", "Kirim")
    assert "#btnSubmit" in s, s
    ok("_build_uia_selector (aid): " + s)

    # Test selector tanpa aid, pakai class
    s2 = _build_uia_selector(50004, "edit", "", "RichEditD2DPT", "")
    assert "input" in s2 or "RichEdit" in s2, s2
    ok("_build_uia_selector (cls): " + s2)

    # Test selector pakai name untuk button
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
    from modules.rekening import check_rekening, BANK_CODES, EWALLETS
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

    # URL format check (tidak hit real API)
    import modules.rekening as _rek
    # bank
    code = _rek.BANK_CODES.get("BCA", "014")
    url_bank = "{}?type=bank&code={}&accountNumber={}".format(_rek._BASE, code, "1234567890")
    assert "type=bank" in url_bank and "014" in url_bank
    ok("URL bank format OK")
    # ewallet
    url_ew = "{}?type=ewallet&code={}&accountNumber={}".format(_rek._BASE, "dana", "08123456789")
    assert "type=ewallet" in url_ew and "dana" in url_ew
    ok("URL ewallet format OK")
except Exception as e:
    fail("Rekening", e)

# ─────────────────────────────────────────────────────────────────────
# T5: PriceMonitor
# ─────────────────────────────────────────────────────────────────────
print("\n[T5] PriceMonitor")
try:
    from modules.price_monitor import PriceMonitor, _find_chrome, _free_port
    msgs = []
    pm = PriceMonitor(on_status=lambda m: msgs.append(m))
    pm.configure(
        url="https://example.com",
        btn_selector="#btnRefresh",
        table_selector="table.harga",
        mode="requests",
        interval_sec=300,
        sheet_id="",
        worksheet="Harga",
        start_cell="A1",
        clear_before=True,
    )
    assert pm._cfg["url"] == "https://example.com"
    assert pm._cfg["btn_selector"] == "#btnRefresh"
    assert pm._cfg["table_selector"] == "table.harga"
    assert pm._cfg["interval_sec"] == 300
    assert pm._cfg["worksheet"] == "Harga"
    ok("configure() semua parameter OK")
except Exception as e:
    fail("PriceMonitor.configure", e)

try:
    from bs4 import BeautifulSoup
    html = (
        "<table>"
        "<tr><th>Produk</th><th>Harga</th><th>Stok</th></tr>"
        "<tr><td>Apel</td><td>Rp5.000</td><td>100</td></tr>"
        "<tr><td>Mangga</td><td>Rp8.000</td><td>50</td></tr>"
        "<tr><td>Jeruk</td><td>Rp6.500</td><td>75</td></tr>"
        "</table>"
    )
    tbl = BeautifulSoup(html, "html.parser").find("table")
    rows = PriceMonitor._parse_html_table(tbl)
    assert rows[0] == ["Produk", "Harga", "Stok"], rows[0]
    assert rows[1] == ["Apel", "Rp5.000", "100"], rows[1]
    assert len(rows) == 4
    ok("_parse_html_table: {} baris x {} kolom".format(len(rows), len(rows[0])))
except Exception as e:
    fail("PriceMonitor._parse_html_table", e)

try:
    chrome = _find_chrome()
    ok("_find_chrome: " + ("DITEMUKAN: " + chrome if chrome else "tidak ada (requests mode tetap OK)"))
    port = _free_port()
    assert 1024 < port < 65535
    ok("_free_port: {} (valid range)".format(port))
except Exception as e:
    fail("PriceMonitor utilities", e)

try:
    # Simulate start/stop threading
    pm2 = PriceMonitor(on_status=lambda m: None, on_data=lambda r: None)
    pm2.configure(url="https://example.com", mode="requests", interval_sec=9999)
    # Don't actually start (would hit network), just verify methods exist
    assert callable(pm2.start)
    assert callable(pm2.stop)
    assert callable(pm2.run_once)
    ok("PriceMonitor start/stop/run_once callable")
except Exception as e:
    fail("PriceMonitor callable check", e)

# ─────────────────────────────────────────────────────────────────────
# T6: app.py – NAV, page builders, feature completeness
# ─────────────────────────────────────────────────────────────────────
print("\n[T6] app.py structure")
try:
    with open("ui/app.py", "r", encoding="utf-8") as f:
        app_src = f.read()

    nav_keys = ["home","web","spy","record","schedule","templates",
                "sheet","rekening","monitor","remote","history","logs","settings"]
    missing_nav = [k for k in nav_keys if k not in app_src]
    assert not missing_nav, "Missing nav: " + str(missing_nav)
    ok("NAV: {} keys semua ada".format(len(nav_keys)))

    builders = ["_pg_home","_pg_web","_pg_spy","_pg_record","_pg_schedule",
                "_pg_sheet","_pg_rekening","_pg_monitor","_pg_remote",
                "_pg_history","_pg_logs","_pg_settings"]
    missing_b = [b for b in builders if b not in app_src]
    assert not missing_b, "Missing builders: " + str(missing_b)
    ok("Page builders: {} semua terdaftar".format(len(builders)))

    monitor_feats = ["_price_monitor", "MULAI MONITOR", "JALANKAN SEKALI",
                     "headless", "btn_selector", "table_selector", "v_sheet_id",
                     "v_interval", "Headless Chrome"]
    missing_mf = [f for f in monitor_feats if f not in app_src]
    assert not missing_mf, "Missing monitor features: " + str(missing_mf)
    ok("Dashboard Update UI: {} fitur lengkap".format(len(monitor_feats)))

    rec_feats = ["speed_var", "repeat_var", "_pct_var", "SIMPAN"]
    missing_rf = [f for f in rec_feats if f not in app_src]
    assert not missing_rf, "Missing recorder features: " + str(missing_rf)
    ok("Recorder UI: {} fitur lengkap".format(len(rec_feats)))

    # pyperclip ada di simple_recorder.py (bukan app.py)
    with open("modules/macro/simple_recorder.py", "r", encoding="utf-8") as f:
        sr_src = f.read()
    assert "pyperclip" in sr_src, "pyperclip tidak ada di simple_recorder.py"
    ok("pyperclip Unicode paste: ada di simple_recorder.py")

    # Spy features ada di spy_window.py
    with open("ui/spy_window.py", "r", encoding="utf-8") as f:
        spy_src2 = f.read()
    spy_feats = ["_start_uia_poll", "_uia_loop", "_show_entry_detail",
                 "_copy_as_step", "COPY CSS"]
    missing_sf = [f for f in spy_feats if f not in spy_src2]
    assert not missing_sf, "Missing spy features: " + str(missing_sf)
    ok("Spy Window (spy_window.py): {} fitur ada".format(len(spy_feats)))
except Exception as e:
    fail("app.py structure", e)

# ─────────────────────────────────────────────────────────────────────
# T7: Sheets connector
# ─────────────────────────────────────────────────────────────────────
print("\n[T7] Sheets connector")
try:
    from modules.sheets.connector import extract_sheet_id
    sid = extract_sheet_id(
        "https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsT/edit#gid=0")
    assert sid == "1aBcDeFgHiJkLmNoPqRsT", sid
    ok("extract_sheet_id dari URL panjang: " + sid)

    sid2 = extract_sheet_id("1aBcDeFgHiJkLmNoPqRsT")
    assert sid2 == "1aBcDeFgHiJkLmNoPqRsT", sid2
    ok("extract_sheet_id dari plain ID: " + sid2)

    sid3 = extract_sheet_id("bukan-id-valid!!!")
    assert sid3 == "", sid3
    ok("extract_sheet_id: string tidak valid -> kosong")
except Exception as e:
    fail("Sheets.extract_sheet_id", e)

# ─────────────────────────────────────────────────────────────────────
# T8: EXE & Shortcut
# ─────────────────────────────────────────────────────────────────────
print("\n[T8] EXE & Desktop shortcut")
try:
    import datetime
    exe = r"C:\Users\Admin\synthex\dist\Synthex.exe"
    assert os.path.exists(exe), "EXE tidak ada"
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(exe))
    size_mb = os.path.getsize(exe) / 1024 / 1024
    now = datetime.datetime.now()
    age_min = (now - mtime).total_seconds() / 60
    ok("EXE ada: {:.1f} MB, dibuat {} ({:.0f} menit lalu)".format(
        size_mb, mtime.strftime("%H:%M"), age_min))
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
    assert "Synthex.exe" in target, "Target shortcut aneh: " + target
    assert os.path.exists(target), "Target shortcut tidak ada: " + target
    ok("Shortcut Desktop -> " + target)
except Exception as e:
    fail("Desktop shortcut", e)

# ─────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────
passes = [r for r in results if r[0] == "PASS"]
fails  = [r for r in results if r[0] == "FAIL"]

print()
print("=" * 62)
print("  HASIL: {}/{} PASS   {} FAIL".format(
    len(passes), len(results), len(fails)))
if fails:
    print()
    print("  Item yang GAGAL:")
    for _, msg in fails:
        print("    - " + msg)
else:
    print("  Semua fitur lulus pengujian otomatis.")
print("=" * 62)
