"""
AURA-AIOSCPU Command Center Client
=====================================
Handles registration with a remote Command Center (CC) and maintains an
ongoing heartbeat so the CC can track this node's liveness.

The CC is contacted over plain HTTPS/HTTP using only stdlib ``urllib``
— no third-party dependencies required.

Protocol (all JSON over HTTP)
------------------------------
POST  <cc_url>/api/nodes/register
    → {"node_id": "...", "alias": "...", "capabilities": [...], ...}
    ← {"status": "ok", "assigned_id": "...", "peers": [...]}

POST  <cc_url>/api/nodes/<node_id>/heartbeat
    → {"ts": epoch, "status": "running", "metrics": {...}}
    ← {"status": "ok", "commands": [...]}   (optional pending commands)

POST  <cc_url>/api/nodes/<node_id>/deregister
    → {}
    ← {"status": "ok"}

Configuration (config/default.json → env vars)
-----------------------------------------------
  CC_URL              — full base URL of Command Center (e.g. http://192.168.1.10:8080)
  CC_API_KEY          — shared secret sent in X-AURA-Key header
  CC_HEARTBEAT_S      — heartbeat interval in seconds (default 30)
  CC_REGISTER_TIMEOUT — registration request timeout in seconds (default 10)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Callable

logger = logging.getLogger(__name__)

_ENV_CC_URL       = "CC_URL"
_ENV_CC_KEY       = "CC_API_KEY"
_DEFAULT_HB_S     = 30
_DEFAULT_TIMEOUT  = 10


class CommandCenterClient:
    """
    Client that registers this node with a Command Center and sends
    periodic heartbeats.

    Parameters
    ----------
    identity : NodeIdentity
        The node's stable identity object.
    cc_url : str | None
        Base URL of the Command Center.  Falls back to ``CC_URL`` env var.
    api_key : str | None
        Shared secret for X-AURA-Key header.  Falls back to ``CC_API_KEY``.
    heartbeat_interval_s : float
        How often to send a heartbeat (seconds).
    metrics_fn : Callable[[], dict] | None
        Optional callable that returns current metrics to include in heartbeat.
    command_handler : Callable[[dict], None] | None
        Optional callable invoked for each pending command returned by the CC.
    """

    def __init__(
        self,
        identity,
        cc_url: str | None = None,
        api_key: str | None = None,
        heartbeat_interval_s: float = _DEFAULT_HB_S,
        metrics_fn: Callable[[], dict] | None = None,
        command_handler: Callable[[dict], None] | None = None,
    ):
        self._identity        = identity
        self._cc_url          = (cc_url or os.environ.get(_ENV_CC_URL, "")).rstrip("/")
        self._api_key         = api_key or os.environ.get(_ENV_CC_KEY, "")
        self._hb_interval     = heartbeat_interval_s
        self._metrics_fn      = metrics_fn
        self._command_handler = command_handler

        self._registered   = False
        self._running      = False
        self._thread: threading.Thread | None = None
        self._lock         = threading.Lock()

        self._last_hb_ts   = 0.0
        self._hb_count     = 0
        self._error_count  = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """True if a CC URL has been provided."""
        return bool(self._cc_url)

    @property
    def is_registered(self) -> bool:
        return self._registered

    def start(self) -> None:
        """Register with CC and start the heartbeat daemon thread."""
        if not self.is_configured:
            logger.info("CommandCenterClient: no CC_URL set — operating standalone")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="cc-heartbeat"
        )
        self._thread.start()
        logger.info("CommandCenterClient: heartbeat thread started")

    def stop(self) -> None:
        """Stop the heartbeat thread and deregister from CC."""
        self._running = False
        if self.is_configured and self._registered:
            try:
                self._deregister()
            except Exception as exc:
                logger.debug("CommandCenterClient: deregister error: %s", exc)

    def register_now(self) -> bool:
        """
        Attempt an immediate registration.
        Returns True on success.
        """
        if not self.is_configured:
            return False
        return self._register()

    def send_heartbeat(self) -> bool:
        """
        Send a single heartbeat immediately.
        Returns True on success.
        """
        if not self.is_configured:
            return False
        return self._heartbeat()

    def status(self) -> dict:
        """Return client status for health/monitoring endpoints."""
        return {
            "configured":    self.is_configured,
            "registered":    self._registered,
            "running":       self._running,
            "cc_url":        self._cc_url or None,
            "hb_count":      self._hb_count,
            "error_count":   self._error_count,
            "last_hb_ts":    self._last_hb_ts or None,
        }

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        # Initial registration with back-off on failure
        backoff = 5.0
        while self._running and not self._registered:
            if self._register():
                break
            logger.warning(
                "CommandCenterClient: registration failed, retry in %.0fs", backoff
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)

        # Heartbeat loop
        while self._running:
            time.sleep(self._hb_interval)
            if not self._running:
                break
            self._heartbeat()

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _register(self) -> bool:
        url = f"{self._cc_url}/api/nodes/register"
        payload = self._identity.to_dict()
        payload["capabilities"] = list(self._identity.capabilities.keys())
        try:
            resp = self._post(url, payload)
            self._registered = True
            logger.info(
                "CommandCenterClient: registered with CC (assigned_id=%s peers=%d)",
                resp.get("assigned_id", "?"),
                len(resp.get("peers", [])),
            )
            return True
        except Exception as exc:
            self._error_count += 1
            logger.warning("CommandCenterClient: registration error: %s", exc)
            return False

    def _heartbeat(self) -> bool:
        node_id = self._identity.node_id
        url = f"{self._cc_url}/api/nodes/{node_id}/heartbeat"
        metrics = {}
        if self._metrics_fn:
            try:
                metrics = self._metrics_fn()
            except Exception:
                pass
        payload = {
            "ts":      time.time(),
            "status":  "running",
            "metrics": metrics,
        }
        try:
            resp = self._post(url, payload)
            self._last_hb_ts = time.time()
            self._hb_count += 1
            commands = resp.get("commands", [])
            if commands and self._command_handler:
                for cmd in commands:
                    try:
                        self._command_handler(cmd)
                    except Exception as exc:
                        logger.error(
                            "CommandCenterClient: command_handler error: %s", exc
                        )
            return True
        except Exception as exc:
            self._error_count += 1
            logger.debug("CommandCenterClient: heartbeat error: %s", exc)
            return False

    def _deregister(self) -> None:
        node_id = self._identity.node_id
        url = f"{self._cc_url}/api/nodes/{node_id}/deregister"
        self._post(url, {}, timeout=5)
        self._registered = False
        logger.info("CommandCenterClient: deregistered from CC")

    def _post(self, url: str, data: dict, timeout: int = _DEFAULT_TIMEOUT) -> dict:
        body = json.dumps(data).encode()
        req  = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type":  "application/json",
                "X-AURA-Key":    self._api_key,
                "X-Node-ID":     self._identity.node_id,
                "X-Node-Alias":  self._identity.alias,
                "User-Agent":    f"AURA-AIOSCPU/{self._identity.version}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
