"""
AURA-AIOSCPU Web Terminal Service
==================================
Serves a full HTML5 terminal UI from a lightweight stdlib HTTP server so
AURA can be driven from any browser — including Chrome on your Samsung
Galaxy S21.

Default URL:  http://127.0.0.1:7331/

Endpoint map
------------
GET  /              → HTML5 terminal page (mobile-optimised dark UI)
POST /api/cmd       → {"cmd": "..."} → {"output": "...", "ts": epoch}
GET  /api/status    → {"running": true, "version": "...", "uptime_s": float}
GET  /api/events    → last N system events as JSON array

No external dependencies — pure Python stdlib (http.server, json, threading).
The server runs in a daemon thread and shuts down gracefully when stop() is
called or the process exits.
"""

import http.server
import json
import logging
import os
import socket
import threading
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_VERSION     = "0.1.0"
_MAX_EVENTS  = 50     # ring buffer size for system event log

# ---------------------------------------------------------------------------
# Embedded HTML/CSS/JS terminal (no static files required)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <meta name="theme-color" content="#0a0e1a">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <title>AURA-AIOSCPU Terminal</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg:      #0a0e1a;
      --bg2:     #111827;
      --border:  #1e3a2f;
      --green:   #4ade80;
      --green2:  #34d399;
      --text:    #c0e8d0;
      --muted:   #6b7280;
      --red:     #f87171;
      --blue:    #60a5fa;
      --yellow:  #fbbf24;
    }
    html, body { height: 100%; overflow: hidden; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace;
      font-size: 13px;
      display: flex;
      flex-direction: column;
      height: 100vh;
    }
    /* ── Header ── */
    #header {
      background: var(--bg2);
      padding: 7px 14px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }
    #header .brand { color: var(--green); font-weight: 700; font-size: 12px; letter-spacing: .04em; }
    #header .meta  { color: var(--muted); font-size: 11px; display: flex; gap: 12px; }
    #status-dot    { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--muted); margin-right: 4px; vertical-align: middle; }
    #status-dot.ok { background: var(--green); box-shadow: 0 0 6px var(--green); }
    /* ── Output pane ── */
    #output {
      flex: 1;
      overflow-y: auto;
      padding: 10px 14px;
      line-height: 1.55;
      -webkit-overflow-scrolling: touch;
    }
    .row { display: flex; white-space: pre-wrap; word-break: break-all; }
    .row-cmd  { color: var(--green2); }
    .row-out  { color: var(--text); }
    .row-err  { color: var(--red); }
    .row-info { color: var(--blue); }
    .row-warn { color: var(--yellow); }
    .prompt   { color: var(--green); margin-right: 6px; flex-shrink: 0; }
    /* ── Input row ── */
    #input-area {
      background: var(--bg2);
      border-top: 1px solid var(--border);
      padding: 7px 10px;
      display: flex;
      align-items: center;
      flex-shrink: 0;
      gap: 6px;
    }
    #ps1 { color: var(--green); white-space: nowrap; font-size: 13px; }
    #cmd {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: var(--text);
      font-family: inherit;
      font-size: 13px;
      caret-color: var(--green);
      min-width: 0;
    }
    #btn-send {
      background: #1e3a2f;
      color: var(--green);
      border: 1px solid var(--border);
      border-radius: 5px;
      padding: 5px 14px;
      font-family: inherit;
      font-size: 12px;
      cursor: pointer;
      touch-action: manipulation;
      flex-shrink: 0;
    }
    #btn-send:active { background: #2d5c45; }
    /* ── Quick-command toolbar ── */
    #toolbar {
      background: var(--bg2);
      border-top: 1px solid var(--border);
      display: flex;
      gap: 5px;
      padding: 5px 10px;
      overflow-x: auto;
      flex-shrink: 0;
      -webkit-overflow-scrolling: touch;
    }
    #toolbar button {
      background: #1a2540;
      color: var(--blue);
      border: 1px solid #2a3a5a;
      border-radius: 4px;
      padding: 4px 10px;
      font-family: inherit;
      font-size: 11px;
      cursor: pointer;
      white-space: nowrap;
      touch-action: manipulation;
    }
    #toolbar button:active { background: #263050; }
    /* scrollbar */
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: var(--bg); }
    ::-webkit-scrollbar-thumb { background: #2d4a3e; border-radius: 3px; }
  </style>
</head>
<body>
  <div id="header">
    <span class="brand">⬡ AURA-AIOSCPU</span>
    <span class="meta">
      <span><span id="status-dot"></span><span id="status-txt">connecting…</span></span>
      <span id="uptime-txt"></span>
    </span>
  </div>
  <div id="output"></div>
  <div id="toolbar">
    <button onclick="quick('help')">help</button>
    <button onclick="quick('status')">status</button>
    <button onclick="quick('device')">device</button>
    <button onclick="quick('services')">services</button>
    <button onclick="quick('ps')">ps</button>
    <button onclick="quick('ls')">ls</button>
    <button onclick="quick('net')">net</button>
    <button onclick="quick('sysinfo')">sysinfo</button>
    <button onclick="quick('model list')">models</button>
    <button onclick="quick('repair')">repair</button>
    <button onclick="quick('logs 20')">logs</button>
    <button onclick="quick('version')">version</button>
    <button onclick="clearOutput()">clear</button>
  </div>
  <div id="input-area">
    <span id="ps1">aura&gt;</span>
    <input id="cmd" type="text" autocomplete="off" autocorrect="off"
           autocapitalize="off" spellcheck="false"
           placeholder="type a command or ask AURA…">
    <button id="btn-send">↵ Send</button>
  </div>

<script>
/* ── DOM refs ── */
const outEl  = document.getElementById('output');
const cmdEl  = document.getElementById('cmd');
const dotEl  = document.getElementById('status-dot');
const stEl   = document.getElementById('status-txt');
const upEl   = document.getElementById('uptime-txt');

/* ── State ── */
let hist = [], hIdx = -1, busy = false, startTs = Date.now();

/* ── Output helpers ── */
function appendRow(text, cls) {
  const d = document.createElement('div');
  d.className = 'row row-' + cls;
  d.textContent = text;
  outEl.appendChild(d);
  outEl.scrollTop = outEl.scrollHeight;
}
function appendCmd(text) {
  const d = document.createElement('div');
  d.className = 'row row-cmd';
  const p = document.createElement('span');
  p.className = 'prompt'; p.textContent = 'aura> ';
  d.appendChild(p);
  const t = document.createTextNode(text);
  d.appendChild(t);
  outEl.appendChild(d);
  outEl.scrollTop = outEl.scrollHeight;
}
function clearOutput() { outEl.innerHTML = ''; }

/* ── Send command ── */
async function send(cmdStr) {
  cmdStr = (cmdStr || cmdEl.value).trim();
  if (!cmdStr || busy) return;
  hist.unshift(cmdStr); if (hist.length > 200) hist.pop();
  hIdx = -1; cmdEl.value = '';
  appendCmd(cmdStr);
  busy = true;
  try {
    const r = await fetch('/api/cmd', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cmd: cmdStr})
    });
    const d = await r.json();
    if (d.output) appendRow(d.output, 'out');
  } catch (e) {
    appendRow('Connection error: ' + e.message, 'err');
  }
  busy = false;
  cmdEl.focus();
}
function quick(c) { send(c); }

/* ── Input events ── */
document.getElementById('btn-send').onclick = () => send();
cmdEl.addEventListener('keydown', e => {
  if (e.key === 'Enter') { send(); return; }
  if (e.key === 'ArrowUp') {
    if (hIdx < hist.length - 1) cmdEl.value = hist[++hIdx];
    e.preventDefault();
  }
  if (e.key === 'ArrowDown') {
    if (hIdx > 0) cmdEl.value = hist[--hIdx];
    else { hIdx = -1; cmdEl.value = ''; }
    e.preventDefault();
  }
});

/* ── Status polling ── */
async function checkStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    dotEl.className = 'ok';
    stEl.textContent = '● online';
    const s = Math.round(d.uptime_s || 0);
    upEl.textContent = 'up ' + (s < 60 ? s+'s' : Math.floor(s/60)+'m '+s%60+'s');
  } catch {
    dotEl.className = '';
    stEl.textContent = '○ offline';
  }
}
checkStatus();
setInterval(checkStatus, 8000);

/* ── Boot greeting ── */
appendRow('AURA-AIOSCPU Web Terminal  v__VERSION__', 'info');
appendRow('Tap a quick-command above or type below.', 'info');
appendRow('', 'out');
cmdEl.focus();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    """Routes GET / and POST /api/cmd.  dispatch_fn + event_log injected
    as class attributes by WebTerminalService before the server starts."""

    dispatch_fn  = None   # callable(cmd: str) -> str
    event_log    = None   # list of dicts
    start_time   = None   # float epoch

    def log_message(self, fmt, *args):  # silence default access log
        logger.debug("WebTerminal: " + fmt, *args)

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = _HTML_TEMPLATE.replace("__VERSION__", _VERSION).encode()
            self._respond(200, "text/html; charset=utf-8", body)

        elif path == "/api/status":
            uptime = time.time() - (self.__class__.start_time or time.time())
            body = json.dumps({
                "running":   True,
                "version":   _VERSION,
                "uptime_s":  round(uptime, 1),
            }).encode()
            self._respond(200, "application/json", body)

        elif path == "/api/events":
            log = list(self.__class__.event_log or [])
            self._respond(200, "application/json", json.dumps(log).encode())

        else:
            self._respond(404, "text/plain", b"Not found")

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/cmd":
            self._respond(404, "text/plain", b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length)
            data   = json.loads(raw)
            cmd    = str(data.get("cmd", "")).strip()
        except Exception:
            self._respond(400, "application/json",
                          json.dumps({"error": "bad request"}).encode())
            return

        output = ""
        if cmd and self.__class__.dispatch_fn:
            try:
                output = self.__class__.dispatch_fn(cmd) or ""
            except Exception as exc:
                output = f"Error: {exc}"

        resp = json.dumps({"output": output, "ts": time.time()})
        self._respond(200, "application/json", resp.encode())

    # ------------------------------------------------------------------
    def _respond(self, code: int, content_type: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type",   content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# WebTerminalService
# ---------------------------------------------------------------------------

class WebTerminalService:
    """
    Lightweight HTTP terminal server.

    Pass a shell ``dispatch_fn`` (e.g. ``shell.dispatch``) and optionally
    an event_bus so system events are forwarded to the web UI.

    Example
    -------
    ::

        svc = WebTerminalService(dispatch_fn=shell.dispatch)
        svc.start()                         # http://127.0.0.1:7331/
        ...
        svc.stop()
    """

    def __init__(self,
                 dispatch_fn=None,
                 event_bus=None,
                 host: str = "127.0.0.1",
                 port: int = 7331):
        self._dispatch_fn  = dispatch_fn
        self._event_bus    = event_bus
        self._host         = host
        self._port         = port
        self._server       = None
        self._thread       = None
        self._running      = False
        self._event_log    = []          # ring buffer
        self._start_time   = None

        if event_bus is not None:
            for ev in ("SERVICE_STARTED", "SERVICE_STOPPED", "SHUTDOWN",
                       "BUILD_COMPLETE", "INTEGRITY_ALERT", "NETWORK_STATUS",
                       "SERVICE_RESTARTING", "PKG_INSTALLED"):
                event_bus.subscribe(ev, self._on_system_event)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the HTTP server in a daemon thread.
        Returns True on success, False if the port is already in use."""
        if self._running:
            return True

        dispatch = self._dispatch_fn
        event_log = self._event_log
        start_time = time.time()

        class _H(_Handler):
            pass

        _H.dispatch_fn = dispatch
        _H.event_log   = event_log
        _H.start_time  = start_time

        try:
            self._server = http.server.HTTPServer((self._host, self._port), _H)
        except OSError as exc:
            logger.error(
                "WebTerminalService: cannot bind %s:%d — %s",
                self._host, self._port, exc,
            )
            return False

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="aura-web-terminal",
            daemon=True,
        )
        self._thread.start()
        self._running   = True
        self._start_time = start_time
        logger.info(
            "WebTerminalService: listening on http://%s:%d/",
            self._host, self._port,
        )
        return True

    def stop(self) -> None:
        """Shut down the HTTP server."""
        if self._server:
            self._server.shutdown()
        self._running = False
        logger.info("WebTerminalService: stopped")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}/"

    @property
    def port(self) -> int:
        return self._port

    # ------------------------------------------------------------------
    # Event log (shown in /api/events)
    # ------------------------------------------------------------------

    def _on_system_event(self, event) -> None:
        entry = {
            "type":    event.event_type,
            "payload": event.payload,
            "ts":      event.timestamp,
        }
        self._event_log.append(entry)
        if len(self._event_log) > _MAX_EVENTS:
            self._event_log.pop(0)

    def __repr__(self):
        state = f"running @ {self.url}" if self._running else "stopped"
        return f"WebTerminalService({state})"
