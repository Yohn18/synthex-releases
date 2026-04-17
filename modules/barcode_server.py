"""
modules/barcode_server.py
─────────────────────────
Lightweight HTTP server that lets a phone scan barcodes and trigger
Synthex recordings remotely.

Architecture
────────────
  PC runs BarcodeServer on http://<LAN-IP>:7788
  Phone opens that URL in Chrome → sees a camera barcode scanner page
  User scans a barcode  →  POST /scan {"code": "…"}
  Server calls on_scan(code) callback  →  app plays the matching recording
  Response JSON {"ok": true/false, "message": "…"}  →  phone shows result

Endpoints
  GET  /          → mobile scanner UI (HTML)
  GET  /ping      → {"status":"ready","recordings":[…]}
  POST /scan      → {"code":"<barcode>"} → {"ok":…,"message":"…"}
  GET  /list      → {"recordings":[{"name":"…","type":"…"},…]}
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from core.logger import get_logger

logger = get_logger("barcode_server")

# ── HTML scanner page (served to phone) ───────────────────────────────────────
_SCANNER_HTML = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
<title>Synthex Remote</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#111118;color:#E0DFFF;font-family:'Segoe UI',system-ui,sans-serif;
     display:flex;flex-direction:column;min-height:100dvh;padding-bottom:env(safe-area-inset-bottom)}
header{background:#1A1A24;padding:12px 16px;display:flex;align-items:center;gap:10px;
       border-bottom:1px solid #2A2A44}
.logo{background:#6C4AFF;color:#fff;font-size:11px;font-weight:700;padding:4px 8px;
      border-radius:4px;letter-spacing:.5px}
.title{font-size:15px;font-weight:600;color:#E0DFFF}
.sub{font-size:11px;color:#555575;margin-top:1px}
#reader-wrap{position:relative;background:#0A0A0F;overflow:hidden;
             flex:0 0 auto;height:min(56vw,320px);max-height:320px}
#reader-wrap video{width:100%;height:100%;object-fit:cover}
.scan-box{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
          width:200px;height:200px;border:2px solid #6C4AFF;border-radius:8px;
          pointer-events:none}
.scan-box::before,.scan-box::after{content:'';position:absolute;border-color:#6C4AFF;
  border-style:solid;width:20px;height:20px}
.scan-box::before{top:-2px;left:-2px;border-width:3px 0 0 3px;border-radius:4px 0 0 4px}
.scan-box::after{bottom:-2px;right:-2px;border-width:0 3px 3px 0;border-radius:0 0 4px 4px}
.scan-line{position:absolute;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,#6C4AFF,transparent);
           animation:scan 2s ease-in-out infinite}
@keyframes scan{0%{top:10%}100%{top:90%}}
#status-bar{background:#14141E;padding:12px 16px;font-size:13px;min-height:48px;
            display:flex;align-items:center;gap:10px;border-bottom:1px solid #1A1A2A}
.dot{width:8px;height:8px;border-radius:50%;background:#555575;flex-shrink:0;
     transition:background .3s}
.dot.ready{background:#4CAF88}
.dot.scanning{background:#6C4AFF;animation:pulse 1s infinite}
.dot.error{background:#F06070}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
#log{flex:1;overflow-y:auto;padding:8px}
.log-item{background:#1A1A24;border-radius:8px;padding:10px 12px;margin-bottom:8px;
          border-left:3px solid #2A2A44;font-size:13px;transition:border-color .3s}
.log-item.ok{border-color:#4CAF88}
.log-item.err{border-color:#F06070}
.log-item .code{font-weight:600;color:#E0DFFF;word-break:break-all}
.log-item .msg{font-size:11px;color:#555575;margin-top:3px}
.log-item .time{font-size:10px;color:#3A3A5A;float:right}
.btn-row{padding:12px 16px;display:flex;gap:8px;background:#14141E;
         border-top:1px solid #1A1A2A}
button{flex:1;padding:11px;border:none;border-radius:6px;font-size:13px;font-weight:600;
       cursor:pointer;transition:opacity .2s}
button:active{opacity:.7}
#btn-start{background:#6C4AFF;color:#fff}
#btn-stop{background:#F06070;color:#fff;display:none}
#btn-torch{background:#1A1A24;color:#E0DFFF}
.empty{text-align:center;color:#3A3A5A;font-size:13px;padding:32px 0}
</style>
</head>
<body>
<header>
  <span class="logo">SYNTHEX</span>
  <div><div class="title">Remote Scanner</div>
       <div class="sub" id="server-label">Connecting...</div></div>
</header>
<div id="reader-wrap">
  <video id="video" playsinline autoplay muted></video>
  <div class="scan-box"><div class="scan-line"></div></div>
</div>
<div id="status-bar"><span class="dot" id="dot"></span><span id="status-msg">Tap Mulai Scanner</span></div>
<div id="log"><div class="empty" id="empty-msg">Belum ada scan.</div></div>
<div class="btn-row">
  <button id="btn-start" onclick="startScan()">Mulai Scanner</button>
  <button id="btn-stop"  onclick="stopScan()">Stop</button>
  <button id="btn-torch" onclick="toggleTorch()">Senter</button>
</div>
<script>
let stream=null, track=null, raf=null, torchOn=false, lastCode='', lastCodeTime=0;
let detector=null;

function setStatus(msg,state){
  document.getElementById('status-msg').textContent=msg;
  document.getElementById('dot').className='dot'+(state?' '+state:'');
}

async function startScan(){
  setStatus('Meminta izin kamera...','scanning');
  try{
    stream=await navigator.mediaDevices.getUserMedia({
      video:{facingMode:'environment',width:{ideal:1280},height:{ideal:720}}});
    const v=document.getElementById('video');
    v.srcObject=stream;
    await v.play();
    track=stream.getVideoTracks()[0];
    document.getElementById('btn-start').style.display='none';
    document.getElementById('btn-stop').style.display='flex';

    // Try BarcodeDetector (native Chrome Android)
    if('BarcodeDetector' in window){
      const formats=await BarcodeDetector.getSupportedFormats();
      detector=new BarcodeDetector({formats});
      setStatus('Scanner aktif (BarcodeDetector)','ready');
    } else {
      setStatus('Scanner aktif','ready');
    }
    scanLoop();
  } catch(e){
    setStatus('Gagal: '+e.message,'error');
  }
}

async function scanLoop(){
  if(!stream) return;
  try{
    if(detector){
      const barcodes=await detector.detect(document.getElementById('video'));
      for(const b of barcodes){
        const code=b.rawValue;
        const now=Date.now();
        if(code!==lastCode || now-lastCodeTime>3000){
          lastCode=code; lastCodeTime=now;
          sendCode(code);
        }
      }
    }
  } catch(e){}
  raf=requestAnimationFrame(scanLoop);
}

function stopScan(){
  if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;track=null;}
  if(raf){cancelAnimationFrame(raf);raf=null;}
  document.getElementById('btn-start').style.display='flex';
  document.getElementById('btn-stop').style.display='none';
  setStatus('Scanner dihentikan','');
}

async function toggleTorch(){
  if(!track) return;
  try{
    torchOn=!torchOn;
    await track.applyConstraints({advanced:[{torch:torchOn}]});
    document.getElementById('btn-torch').textContent=torchOn?'Senter OFF':'Senter';
  }catch(e){setStatus('Senter tidak didukung','error');}
}

async function sendCode(code){
  setStatus('Mengirim: '+code.substring(0,30)+'...','scanning');
  addLog(code,'','...');
  try{
    const r=await fetch('/scan',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({code})});
    const data=await r.json();
    updateLastLog(code, data.ok, data.message||'');
    setStatus(data.ok?('OK: '+data.message):'Tidak cocok: '+code,'ready');
  } catch(e){
    updateLastLog(code,false,'Koneksi gagal');
    setStatus('Gagal kirim','error');
  }
}

function addLog(code, ok, msg){
  document.getElementById('empty-msg')?.remove();
  const d=document.getElementById('log');
  const now=new Date().toLocaleTimeString('id');
  const el=document.createElement('div');
  el.className='log-item pending';
  el.id='ll-'+Date.now();
  el.innerHTML=`<span class="time">${now}</span><div class="code">${code}</div><div class="msg">${msg}</div>`;
  d.prepend(el);
  window._lastLogId=el.id;
}

function updateLastLog(code,ok,msg){
  const el=document.getElementById(window._lastLogId);
  if(!el) return;
  el.className='log-item '+(ok?'ok':'err');
  el.querySelector('.msg').textContent=msg;
}

// Fetch server info
fetch('/ping').then(r=>r.json()).then(d=>{
  document.getElementById('server-label').textContent=
    'Terhubung  |  '+d.recordings_count+' rekaman tersedia';
}).catch(()=>{
  document.getElementById('server-label').textContent='Synthex offline';
});
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    """Minimal HTTP handler — routes requests to the BarcodeServer instance."""

    def log_message(self, fmt, *args):
        # Suppress default console output; use our logger
        logger.debug("HTTP %s", fmt % args)

    def _send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        srv = self.server._barcode_server  # BarcodeServer instance

        if self.path == "/" or self.path == "/index.html":
            self._send_html(_SCANNER_HTML)

        elif self.path == "/ping":
            recs = srv.get_recordings_list()
            self._send_json(200, {
                "status":           "ready",
                "recordings_count": len(recs),
                "recordings":       recs,
            })

        elif self.path == "/list":
            self._send_json(200, {"recordings": srv.get_recordings_list()})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        srv = self.server._barcode_server

        if self.path == "/scan":
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                code    = str(payload.get("code", "")).strip()
            except Exception:
                self._send_json(400, {"ok": False, "message": "Bad JSON"})
                return

            if not code:
                self._send_json(400, {"ok": False, "message": "Kode kosong"})
                return

            logger.info("Barcode scan received: %r", code)
            result = srv._handle_scan(code)
            self._send_json(200, result)
        else:
            self.send_response(404)
            self.end_headers()


class BarcodeServer:
    """
    Manages the barcode HTTP server lifecycle.

    Parameters
    ----------
    port : int
        Port to listen on (default 7788).
    on_scan : callable(code: str) -> dict | None
        Called on the server thread when a barcode arrives.
        Should return {"ok": bool, "message": str} or None.
    get_recordings : callable() -> list[dict]
        Returns current recordings list for /ping and /list.
    """

    def __init__(self, port=7788, on_scan=None, get_recordings=None):
        self._port          = port
        self._on_scan       = on_scan
        self._get_recordings = get_recordings
        self._server        = None
        self._thread        = None
        self.running        = False

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        if self.running:
            return
        self._server = HTTPServer(("0.0.0.0", self._port), _Handler)
        self._server._barcode_server = self          # back-reference for handler
        self._server.timeout         = 1.0           # allows periodic stop check
        self._thread = threading.Thread(
            target=self._serve_loop, daemon=True, name="BarcodeServer")
        self._thread.start()
        self.running = True
        logger.info("BarcodeServer started on port %d", self._port)

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self._server:
            self._server.shutdown()
            self._server = None
        logger.info("BarcodeServer stopped.")

    def get_local_url(self):
        """Return http://<LAN-IP>:<port> string."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = socket.gethostbyname(socket.gethostname())
        return "http://{}:{}".format(ip, self._port)

    def get_recordings_list(self):
        if callable(self._get_recordings):
            try:
                return self._get_recordings()
            except Exception:
                pass
        return []

    # ── Internal ──────────────────────────────────────────────────────────────

    def _serve_loop(self):
        while self.running:
            try:
                self._server.handle_request()
            except Exception as e:
                if self.running:
                    logger.warning("BarcodeServer error: %s", e)

    def _handle_scan(self, code: str) -> dict:
        """
        Try the user callback first; fall back to name-matching
        against the recordings list.
        """
        if callable(self._on_scan):
            try:
                result = self._on_scan(code)
                if isinstance(result, dict):
                    return result
            except Exception as e:
                logger.error("on_scan callback error: %s", e)
                return {"ok": False, "message": "Error: {}".format(e)}

        # Default: match code against recording names (case-insensitive)
        recs = self.get_recordings_list()
        code_lower = code.lower()
        matched = None
        for r in recs:
            if r.get("name", "").lower() == code_lower:
                matched = r
                break
        # Partial match fallback
        if not matched:
            for r in recs:
                if code_lower in r.get("name", "").lower():
                    matched = r
                    break

        if matched:
            return {"ok": True, "message": "Memutar: {}".format(matched["name"]),
                    "name": matched["name"]}
        return {"ok": False,
                "message": "Rekaman '{}' tidak ditemukan".format(code[:40])}
