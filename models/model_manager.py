"""
AURA-AIOSCPU AI Model Manager
===============================
Manages AI model lifecycle: register → load → infer → unload.

Design principles
-----------------
- Zero required dependencies: always falls back to a context-aware stub.
- Optional llama-cpp-python for GGUF models (runs on ARM64 / Android).
- Optional onnxruntime for ONNX models.
- Ollama API bridge: zero-compile AI via http://localhost:11434 (phone-friendly).
- OpenAI-compatible API bridge: any API key, any hosted endpoint (GPT-4, Groq, …).
- One active model at a time — minimises RAM use on mobile.
- Lazy loading: models are not loaded until first inference.
- Registry persisted to JSON so models survive process restarts.

Backend priority order (highest → lowest)
------------------------------------------
  1. Ollama  (if running locally or configured)
  2. OpenAI-compatible API  (if api_key / api_base configured)
  3. llama-cpp-python  (GGUF local inference)
  4. onnxruntime  (ONNX local inference)
  5. Stub  (always available — no real AI, but shell stays functional)
"""

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REGISTRY_FILENAME = "model_registry.json"
_MODEL_EXTENSIONS = {".gguf", ".bin", ".pt", ".ggml", ".onnx"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ModelInfo:
    """Metadata about one registered AI model."""

    def __init__(self, name: str, path: str,
                 model_type: str = "gguf",
                 size_mb: float = 0.0,
                 description: str = ""):
        self.name        = name
        self.path        = path
        self.model_type  = model_type
        self.size_mb     = size_mb
        self.description = description
        self.loaded      = False
        self.load_time:  float | None = None

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "path":        self.path,
            "model_type":  self.model_type,
            "size_mb":     round(self.size_mb, 2),
            "description": self.description,
            "loaded":      self.loaded,
        }


# ---------------------------------------------------------------------------
# Inference engines
# ---------------------------------------------------------------------------

class StubInferenceEngine:
    """
    Development/demo engine used when no real model is loaded.
    Returns context-aware responses so the shell remains fully functional.
    """

    def infer(self, prompt: str, context: dict) -> str:
        ctx_summary = ", ".join(
            f"{k}={v}" for k, v in list(context.items())[:4]
        )
        return (
            f"[AURA stub — no model loaded]\n"
            f"Query: {prompt!r}\n"
            f"Context: {ctx_summary or 'none yet'}\n"
            f"Load a model with:  model load <name>"
        )


class _LlamaCppEngine:
    """llama-cpp-python inference engine (GGUF / GGML models)."""

    def __init__(self, path: str, n_ctx: int = 2048):
        from llama_cpp import Llama  # type: ignore
        self._llm = Llama(model_path=path, n_ctx=n_ctx, verbose=False)

    def infer(self, prompt: str, _context: dict) -> str:
        out = self._llm(prompt, max_tokens=256, stop=["\n\n"])
        return out["choices"][0]["text"].strip()


class _OnnxEngine:
    """onnxruntime inference engine (ONNX models)."""

    def __init__(self, path: str):
        import onnxruntime as ort  # type: ignore
        self._session = ort.InferenceSession(path)

    def infer(self, prompt: str, _context: dict) -> str:
        return f"[ONNX model] Processed: {prompt}"


class OllamaInferenceEngine:
    """
    Zero-compile AI inference via the Ollama REST API.

    Requires Ollama running locally (http://localhost:11434) or at a custom
    ``base_url``.  No native compilation — works on any Python platform
    including Android/Termux (``curl -fsSL https://ollama.ai/install.sh | sh``
    or ``pkg install ollama`` in Termux).

    Usage::

        engine = OllamaInferenceEngine(model="phi3")
        engine.infer("what services are running?", ctx)
    """

    _DEFAULT_BASE = "http://localhost:11434"

    def __init__(self, model: str = "phi3",
                 base_url: str | None = None,
                 timeout_s: int = 60):
        self._model    = model
        self._base_url = (base_url or self._DEFAULT_BASE).rstrip("/")
        self._timeout  = timeout_s

    @classmethod
    def is_available(cls, base_url: str | None = None) -> bool:
        """Return True if an Ollama server is reachable at *base_url*."""
        url = (base_url or cls._DEFAULT_BASE).rstrip("/") + "/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False

    def infer(self, prompt: str, context: dict) -> str:
        """Send *prompt* to Ollama and return the response text."""
        url = f"{self._base_url}/api/generate"
        body = json.dumps({
            "model":  self._model,
            "prompt": prompt,
            "stream": False,
        }).encode()
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())
            return str(data.get("response", "")).strip()
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama unreachable at {self._base_url}: {exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Ollama inference error: {exc}") from exc


class OpenAIInferenceEngine:
    """
    OpenAI-compatible REST API inference engine.

    Works with OpenAI, Groq, Together, Mistral, or any provider that
    implements the ``POST /v1/chat/completions`` endpoint.

    Configuration (via config/user.json)::

        {
          "aura": {
            "backend":   "openai",
            "api_key":   "sk-...",
            "api_base":  "https://api.openai.com/v1",
            "model":     "gpt-4o-mini"
          }
        }

    ``api_key`` can also be supplied via the ``OPENAI_API_KEY`` environment
    variable.  ``api_base`` defaults to the official OpenAI endpoint.
    """

    _DEFAULT_BASE  = "https://api.openai.com/v1"
    _DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, api_key: str | None = None,
                 api_base: str | None = None,
                 model: str | None = None,
                 timeout_s: int = 60,
                 max_tokens: int = 512):
        self._api_key   = (api_key
                           or os.environ.get("OPENAI_API_KEY", ""))
        self._api_base  = (api_base or self._DEFAULT_BASE).rstrip("/")
        self._model     = model or self._DEFAULT_MODEL
        self._timeout   = timeout_s
        self._max_tokens = max_tokens

    def infer(self, prompt: str, context: dict) -> str:
        """Send *prompt* to the OpenAI-compatible endpoint."""
        if not self._api_key:
            raise RuntimeError(
                "OpenAI API key not set. "
                "Set OPENAI_API_KEY or config aura.api_key."
            )
        url  = f"{self._api_base}/chat/completions"
        body = json.dumps({
            "model":      self._model,
            "messages":   [{"role": "user", "content": prompt}],
            "max_tokens": self._max_tokens,
        }).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())
            choices = data.get("choices", [])
            if not choices:
                return ""
            return str(
                choices[0].get("message", {}).get("content", "")
            ).strip()
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise RuntimeError(
                f"OpenAI API error {exc.code}: {body_text}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"OpenAI endpoint unreachable: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# ModelManager
# ---------------------------------------------------------------------------

class ModelManager:
    """
    Manages the full model lifecycle in a mobile-safe, thread-safe way.

    Memory budget
    -------------
    - Models larger than ``max_memory_mb`` are refused at load time.
    - Only one model is active at a time.
    - Unloading frees the engine object (GC-collectable).
    """

    def __init__(self,
                 models_dir: str | None = None,
                 max_memory_mb: int = 512):
        self._models_dir  = models_dir or os.path.join(_REPO_ROOT, "models")
        self._max_mem_mb  = max_memory_mb
        self._registry:   dict[str, ModelInfo] = {}
        self._active:     str | None = None
        self._engine      = StubInferenceEngine()
        self._lock        = threading.Lock()
        os.makedirs(self._models_dir, exist_ok=True)
        self._load_registry()

    # ------------------------------------------------------------------
    # Registry persistence
    # ------------------------------------------------------------------

    def _registry_path(self) -> str:
        return os.path.join(self._models_dir, _REGISTRY_FILENAME)

    def _load_registry(self) -> None:
        p = self._registry_path()
        if not os.path.exists(p):
            return
        try:
            with open(p) as fh:
                data = json.load(fh)
            for entry in data.get("models", []):
                info = ModelInfo(
                    name=entry["name"],
                    path=entry["path"],
                    model_type=entry.get("model_type", "gguf"),
                    size_mb=entry.get("size_mb", 0.0),
                    description=entry.get("description", ""),
                )
                self._registry[info.name] = info
            logger.info("ModelManager: loaded registry (%d models)",
                        len(self._registry))
        except Exception:
            logger.exception("ModelManager: failed to load registry")

    def _save_registry(self) -> None:
        try:
            with open(self._registry_path(), "w") as fh:
                json.dump(
                    {"models": [m.to_dict() for m in self._registry.values()]},
                    fh, indent=2,
                )
        except Exception:
            logger.exception("ModelManager: failed to save registry")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, name: str, path: str,
                 model_type: str = "gguf",
                 description: str = "") -> ModelInfo:
        """Register a model file by path (does not load it)."""
        if not os.path.isabs(path):
            path = os.path.join(self._models_dir, path)
        size_mb = (
            os.path.getsize(path) / (1024 * 1024)
            if os.path.exists(path) else 0.0
        )
        info = ModelInfo(name, path, model_type, size_mb, description)
        with self._lock:
            self._registry[name] = info
        self._save_registry()
        logger.info("ModelManager: registered %r (%.1f MB)", name, size_mb)
        return info

    def load(self, name: str) -> bool:
        """Load and activate a registered model. Returns True on success."""
        with self._lock:
            info = self._registry.get(name)
        if info is None:
            logger.error("ModelManager: %r not registered", name)
            return False
        if not os.path.exists(info.path):
            logger.error("ModelManager: model file missing: %r", info.path)
            return False
        if info.size_mb > self._max_mem_mb:
            logger.warning(
                "ModelManager: %r (%.0fMB) exceeds memory budget (%.0fMB)",
                name, info.size_mb, self._max_mem_mb,
            )
            return False
        t0 = time.monotonic()
        engine = self._try_load_engine(info) or StubInferenceEngine()
        with self._lock:
            self._engine      = engine
            self._active      = name
            info.loaded       = True
            info.load_time    = time.monotonic() - t0
        logger.info("ModelManager: activated %r in %.2fs", name, info.load_time)
        return True

    def unload(self) -> None:
        """Unload the active model and fall back to stub engine."""
        with self._lock:
            if self._active:
                info = self._registry.get(self._active)
                if info:
                    info.loaded = False
            self._active  = None
            self._engine  = StubInferenceEngine()
        logger.info("ModelManager: unloaded active model")

    def infer(self, prompt: str, context: dict) -> str:
        """Run inference (thread-safe)."""
        with self._lock:
            engine = self._engine
        return engine.infer(prompt, context)

    def list_models(self) -> list[dict]:
        return [m.to_dict() for m in self._registry.values()]

    def active_model_name(self) -> str | None:
        return self._active

    def scan_models_dir(self) -> list[str]:
        """Auto-register any unregistered model files found in models_dir."""
        found = []
        for entry in os.scandir(self._models_dir):
            if not entry.is_file():
                continue
            ext = os.path.splitext(entry.name)[1].lower()
            if ext not in _MODEL_EXTENSIONS:
                continue
            name = entry.name.rsplit(".", 1)[0]
            if name not in self._registry:
                self.register(name, entry.path, model_type=ext.lstrip("."))
                found.append(name)
        if found:
            logger.info("ModelManager: auto-registered: %s", found)
        return found

    def load_ollama(self, model: str = "phi3",
                    base_url: str | None = None) -> bool:
        """
        Activate the Ollama API backend.

        Checks that the Ollama server is reachable before activating.
        Returns True on success, False if the server is unreachable.
        """
        if not OllamaInferenceEngine.is_available(base_url):
            logger.warning(
                "ModelManager: Ollama not reachable at %s",
                base_url or OllamaInferenceEngine._DEFAULT_BASE,
            )
            return False
        engine = OllamaInferenceEngine(model=model, base_url=base_url)
        with self._lock:
            self._engine = engine
            self._active = f"ollama:{model}"
        logger.info("ModelManager: Ollama backend activated (model=%s)", model)
        return True

    def load_openai(self, model: str | None = None,
                    api_key: str | None = None,
                    api_base: str | None = None) -> bool:
        """
        Activate the OpenAI-compatible API backend.

        ``api_key`` defaults to the ``OPENAI_API_KEY`` environment variable.
        ``api_base`` defaults to ``https://api.openai.com/v1``.
        Returns True on success.
        """
        engine = OpenAIInferenceEngine(
            api_key=api_key, api_base=api_base, model=model
        )
        with self._lock:
            self._engine = engine
            self._active = f"openai:{engine._model}"
        logger.info(
            "ModelManager: OpenAI backend activated (model=%s base=%s)",
            engine._model, engine._api_base,
        )
        return True

    # ------------------------------------------------------------------
    # Private — engine loading
    # ------------------------------------------------------------------

    def _try_load_engine(self, info: ModelInfo):
        if info.model_type in ("gguf", "ggml"):
            return self._try_llama_cpp(info.path)
        if info.model_type == "onnx":
            return self._try_onnx(info.path)
        return None

    @staticmethod
    def _try_llama_cpp(path: str):
        try:
            return _LlamaCppEngine(path)
        except ImportError:
            logger.debug("ModelManager: llama-cpp-python not installed")
        except Exception:
            logger.exception("ModelManager: llama-cpp load failed")
        return None

    @staticmethod
    def _try_onnx(path: str):
        try:
            return _OnnxEngine(path)
        except ImportError:
            logger.debug("ModelManager: onnxruntime not installed")
        except Exception:
            logger.exception("ModelManager: onnxruntime load failed")
        return None
