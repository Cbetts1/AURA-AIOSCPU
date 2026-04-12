"""
AURA-AIOSCPU Command Channel Service
=======================================
Exposes a secure REST API that the Command Center (and authorized
operators) can use to manage this AURA node remotely.

Listens on 127.0.0.1:7332 by default.  Bind address/port are
configurable via CC_CHANNEL_HOST / CC_CHANNEL_PORT env vars.

Endpoint Reference
------------------
GET  /api/node/identity        — static node identity JSON
GET  /api/node/status          — live status snapshot
GET  /api/node/capabilities    — capability list
GET  /api/node/metrics         — CPU, memory, uptime metrics
GET  /api/peers                — known peer list from PeerRegistry
POST /api/node/announce        — peer registration (from a sibling)
POST /api/cmd                  — execute a kernel/shell command
POST /api/service/start        — {"name": "..."} start a service
POST /api/service/stop         — {"name": "..."} stop a service
GET  /api/services             — all service states
GET  /api/health               — health report from HealthMonitor
GET  /api/mesh/status          — VirtualMesh status
POST /api/mesh/sync            — trigger immediate peer state sync
POST /api/build/trigger        — trigger a rootfs rebuild
GET  /api/logs                 — last N log lines
GET  /api/version              — software version string

Authentication
--------------
Every request must include the ``X-AURA-Key`` header matching the
value of ``CC_API_KEY`` env var.  If the env var is not set the API
runs unauthenticated (suitable for local/dev use only).

All responses are JSON.  Errors return:
  {"error": "<message>", "code": <http_status>}
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import socket
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

_DEFAULT_HOST    = "127.0.0.1"
_DEFAULT_PORT    = 7332
_VERSION         = "0.1.0"
_ENV_HOST        = "CC_CHANNEL_HOST"
_ENV_PORT        = "CC_CHANNEL_PORT"
_ENV_API_KEY     = "CC_API_KEY"


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class _CommandHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the Command Channel."""

    def log_message(self, fmt, *args):  # suppress access log
        logger.debug("CommandChannel: " + fmt, *args)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _check_auth(self) -> bool:
        required = self.server.api_key
        if not required:
            return True
        provided = self.headers.get("X-AURA-Key", "")
        return provided == required

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self):
        if not self._check_auth():
            return self._send_json({"error": "Forbidden"}, 403)

        path = self.path.split("?")[0].rstrip("/")
        routes = {
            "/api/node/identity":   self._handle_identity,
            "/api/node/status":     self._handle_status,
            "/api/node/capabilities": self._handle_capabilities,
            "/api/node/metrics":    self._handle_metrics,
            "/api/peers":           self._handle_peers,
            "/api/services":        self._handle_services,
            "/api/health":          self._handle_health,
            "/api/mesh/status":     self._handle_mesh_status,
            "/api/logs":            self._handle_logs,
            "/api/version":         self._handle_version,
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            self._send_json({"error": "Not found", "code": 404}, 404)

    def do_POST(self):
        if not self._check_auth():
            return self._send_json({"error": "Forbidden"}, 403)

        path = self.path.split("?")[0].rstrip("/")
        body = self._read_body()
        routes = {
            "/api/node/announce":  lambda: self._handle_announce(body),
            "/api/cmd":            lambda: self._handle_cmd(body),
            "/api/service/start":  lambda: self._handle_service_start(body),
            "/api/service/stop":   lambda: self._handle_service_stop(body),
            "/api/mesh/sync":      self._handle_mesh_sync,
            "/api/build/trigger":  self._handle_build_trigger,
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            self._send_json({"error": "Not found", "code": 404}, 404)

    # ------------------------------------------------------------------
    # GET handlers
    # ------------------------------------------------------------------

    def _handle_identity(self):
        srv = self.server
        self._send_json(srv.identity.to_dict())

    def _handle_status(self):
        srv = self.server
        data = {
            "node_id":   srv.identity.node_id,
            "alias":     srv.identity.alias,
            "version":   _VERSION,
            "status":    "running",
            "uptime_s":  round(time.time() - srv.start_time, 1),
            "ts":        time.time(),
        }
        if srv.kernel_api:
            try:
                data["services"] = srv.kernel_api.list_services()
            except Exception:
                pass
        self._send_json(data)

    def _handle_capabilities(self):
        srv = self.server
        self._send_json({
            "node_id":      srv.identity.node_id,
            "capabilities": srv.identity.capability_summary(),
        })

    def _handle_metrics(self):
        self._send_json(_collect_metrics())

    def _handle_peers(self):
        srv = self.server
        if srv.peer_registry:
            self._send_json({"peers": srv.peer_registry.to_list()})
        else:
            self._send_json({"peers": []})

    def _handle_services(self):
        srv = self.server
        if srv.kernel_api:
            try:
                self._send_json({"services": srv.kernel_api.list_services()})
                return
            except Exception:
                pass
        self._send_json({"services": {}})

    def _handle_health(self):
        srv = self.server
        if srv.health_monitor:
            try:
                self._send_json(srv.health_monitor.health_report())
                return
            except Exception:
                pass
        self._send_json({"status": "unknown"})

    def _handle_mesh_status(self):
        srv = self.server
        if srv.mesh:
            self._send_json(srv.mesh.status())
        else:
            self._send_json({"mesh": "not configured"})

    def _handle_logs(self):
        srv = self.server
        lines = srv.log_buffer[-200:]
        self._send_json({"lines": lines, "count": len(lines)})

    def _handle_version(self):
        self._send_json({"version": _VERSION, "node_id": self.server.identity.node_id})

    # ------------------------------------------------------------------
    # POST handlers
    # ------------------------------------------------------------------

    def _handle_announce(self, body: dict):
        srv = self.server
        node_id = body.get("node_id")
        if not node_id:
            return self._send_json({"error": "node_id required"}, 400)
        if srv.peer_registry:
            srv.peer_registry.add_or_update(
                node_id,
                alias=body.get("alias", "unknown"),
                host=body.get("host", ""),
                port=int(body.get("port", 0)),
                capabilities=body.get("capabilities", []),
                status=body.get("status", "unknown"),
                version=body.get("version", ""),
            )
        self._send_json({"status": "ok", "node_id": srv.identity.node_id})

    def _handle_cmd(self, body: dict):
        srv = self.server
        cmd = body.get("cmd", "").strip()
        if not cmd:
            return self._send_json({"error": "cmd required"}, 400)
        dispatch = srv.dispatch_fn
        if dispatch is None:
            return self._send_json({"error": "no dispatch function configured"}, 503)
        try:
            output = dispatch(cmd)
            self._send_json({"output": str(output or ""), "ts": time.time()})
        except Exception as exc:
            self._send_json({"error": str(exc), "ts": time.time()}, 500)

    def _handle_service_start(self, body: dict):
        srv = self.server
        name = body.get("name", "").strip()
        if not name:
            return self._send_json({"error": "name required"}, 400)
        if srv.kernel_api:
            try:
                ok = srv.kernel_api.start_service(name)
                self._send_json({"status": "ok" if ok else "failed", "service": name})
                return
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 500)
        self._send_json({"error": "kernel_api not configured"}, 503)

    def _handle_service_stop(self, body: dict):
        srv = self.server
        name = body.get("name", "").strip()
        if not name:
            return self._send_json({"error": "name required"}, 400)
        if srv.kernel_api:
            try:
                ok = srv.kernel_api.stop_service(name)
                self._send_json({"status": "ok" if ok else "failed", "service": name})
                return
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 500)
        self._send_json({"error": "kernel_api not configured"}, 503)

    def _handle_mesh_sync(self):
        srv = self.server
        if srv.mesh:
            result = srv.mesh.sync_state()
            self._send_json(result)
        else:
            self._send_json({"error": "mesh not configured"}, 503)

    def _handle_build_trigger(self):
        srv = self.server
        if srv.kernel_api:
            try:
                srv.kernel_api.publish(
                    "BUILD_TRIGGER",
                    {"source": "command_channel"},
                    priority="normal",
                )
                self._send_json({"status": "triggered"})
                return
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 500)
        self._send_json({"error": "kernel_api not configured"}, 503)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            return {}

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Node-ID", self.server.identity.node_id)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# HTTP server wrapper
# ---------------------------------------------------------------------------

class _CommandChannelServer(http.server.HTTPServer):
    """HTTPServer subclass that carries shared service state."""

    def __init__(self, addr, handler, identity, api_key):
        super().__init__(addr, handler)
        self.identity:        object = identity
        self.api_key:         str    = api_key
        self.start_time:      float  = time.time()
        self.kernel_api:      object = None
        self.peer_registry:   object = None
        self.mesh:            object = None
        self.health_monitor:  object = None
        self.dispatch_fn:     Callable | None = None
        self.log_buffer:      list   = []


# ---------------------------------------------------------------------------
# Public service class
# ---------------------------------------------------------------------------

class CommandChannelService:
    """
    AURA Command Channel — remote REST API for Command Center integration.

    Parameters
    ----------
    identity : NodeIdentity
        The node's stable identity.
    host : str
        Bind address.  Defaults to ``CC_CHANNEL_HOST`` env var or 127.0.0.1.
    port : int
        Bind port.  Defaults to ``CC_CHANNEL_PORT`` env var or 7332.
    api_key : str | None
        Authentication key.  Defaults to ``CC_API_KEY`` env var.
    dispatch_fn : Callable[[str], str] | None
        Shell/kernel command dispatcher.  Used by POST /api/cmd.
    kernel_api : KernelAPI | None
        Live kernel API handle.
    peer_registry : PeerRegistry | None
        Shared peer registry.
    mesh : VirtualMesh | None
        Virtual mesh handle.
    health_monitor : HealthMonitorService | None
        Health monitor handle.
    """

    def __init__(
        self,
        identity,
        host: str | None = None,
        port: int | None = None,
        api_key: str | None = None,
        dispatch_fn: Callable[[str], str] | None = None,
        kernel_api=None,
        peer_registry=None,
        mesh=None,
        health_monitor=None,
    ):
        self._host   = host or os.environ.get(_ENV_HOST, _DEFAULT_HOST)
        self._port   = port or int(os.environ.get(_ENV_PORT, _DEFAULT_PORT))
        self._apikey = api_key or os.environ.get(_ENV_API_KEY, "")

        self._server: _CommandChannelServer | None = None
        self._thread: threading.Thread | None      = None
        self._running = False

        self._identity       = identity
        self._dispatch_fn    = dispatch_fn
        self._kernel_api     = kernel_api
        self._peer_registry  = peer_registry
        self._mesh           = mesh
        self._health_monitor = health_monitor

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Bind the server socket and start the listener thread."""
        if self._running:
            return

        try:
            server = _CommandChannelServer(
                (self._host, self._port),
                _CommandHandler,
                identity=self._identity,
                api_key=self._apikey,
            )
        except OSError as exc:
            logger.error("CommandChannel: cannot bind %s:%d — %s", self._host, self._port, exc)
            return

        server.kernel_api     = self._kernel_api
        server.peer_registry  = self._peer_registry
        server.mesh           = self._mesh
        server.health_monitor = self._health_monitor
        server.dispatch_fn    = self._dispatch_fn

        self._server  = server
        self._running = True
        self._thread  = threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="cmd-channel",
        )
        self._thread.start()
        logger.info(
            "CommandChannel: listening on http://%s:%d/ (auth=%s)",
            self._host, self._port, bool(self._apikey),
        )

    def stop(self) -> None:
        """Shut down the HTTP server."""
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server = None
        logger.info("CommandChannel: stopped")

    # ------------------------------------------------------------------
    # Dynamic wiring (allow post-init injection)
    # ------------------------------------------------------------------

    def set_kernel_api(self, kernel_api) -> None:
        self._kernel_api = kernel_api
        if self._server:
            self._server.kernel_api = kernel_api

    def set_peer_registry(self, registry) -> None:
        self._peer_registry = registry
        if self._server:
            self._server.peer_registry = registry

    def set_mesh(self, mesh) -> None:
        self._mesh = mesh
        if self._server:
            self._server.mesh = mesh

    def set_health_monitor(self, hm) -> None:
        self._health_monitor = hm
        if self._server:
            self._server.health_monitor = hm

    def set_dispatch_fn(self, fn: Callable[[str], str]) -> None:
        self._dispatch_fn = fn
        if self._server:
            self._server.dispatch_fn = fn

    def append_log(self, line: str) -> None:
        """Append a log line to the server's ring buffer (for /api/logs)."""
        if self._server:
            buf = self._server.log_buffer
            buf.append(line)
            if len(buf) > 500:
                del buf[:-400]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bind_address(self) -> str:
        return f"{self._host}:{self._port}"

    def status(self) -> dict:
        return {
            "running":  self._running,
            "host":     self._host,
            "port":     self._port,
            "auth":     bool(self._apikey),
            "node_id":  self._identity.node_id,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_metrics() -> dict:
    """Return lightweight system metrics using only stdlib."""
    metrics: dict = {"ts": time.time()}

    # uptime from /proc/uptime (Linux/Android)
    try:
        with open("/proc/uptime") as fh:
            metrics["system_uptime_s"] = float(fh.read().split()[0])
    except Exception:
        pass

    # memory from /proc/meminfo
    try:
        mem: dict = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(":")] = int(parts[1])
        if "MemTotal" in mem and "MemAvailable" in mem:
            total  = mem["MemTotal"]
            avail  = mem["MemAvailable"]
            used   = total - avail
            metrics["mem_total_mb"]  = total  // 1024
            metrics["mem_used_mb"]   = used   // 1024
            metrics["mem_avail_mb"]  = avail  // 1024
            metrics["mem_pct"]       = round(used / total * 100, 1)
    except Exception:
        pass

    # CPU load average
    try:
        metrics["load_avg"] = list(os.getloadavg())
    except Exception:
        pass

    # Python process stats via psutil if available
    try:
        import psutil  # type: ignore
        proc = psutil.Process(os.getpid())
        metrics["process_rss_mb"]   = round(proc.memory_info().rss / (1024 * 1024), 1)
        metrics["process_cpu_pct"]  = proc.cpu_percent(interval=None)
        metrics["process_threads"]  = proc.num_threads()
    except ImportError:
        pass

    return metrics
