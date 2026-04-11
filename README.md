<div align="center">

# AURA-AIOSCPU

**AI-native OS simulation layer. Pure Python. Runs on Android, Linux, macOS, Windows.**

[![Tests](https://img.shields.io/badge/tests-918%20passing-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Android%20%7C%20Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](#)
[![License](https://img.shields.io/badge/license-MIT-green)](#)

</div>

---

## What It Is

AURA-AIOSCPU is a kernel simulation written entirely in Python (3.10+ stdlib, zero required dependencies). It models a real OS stack — kernel loop, event bus, scheduler, service registry, hardware abstraction, virtual storage — with a built-in AI personality layer that observes system state and answers queries.

**Runs without root, without compilation, without a real OS partition.** Works on an Android phone via Termux or any Python 3.10+ environment.

---

## Quick Start

**Android / Termux:**
```bash
pkg install git python
git clone https://github.com/Cbetts1/AURA-AIOSCPU
cd AURA-AIOSCPU
bash install_termux.sh
```

**Desktop / Server:**
```bash
git clone https://github.com/Cbetts1/AURA-AIOSCPU
cd AURA-AIOSCPU
pip install -e .
python launch/launcher.py
```

**Docker:**
```bash
docker build -t aura-aioscpu .
docker run -it -p 7331:7331 aura-aioscpu
# Web terminal: http://localhost:7331
```

---

## CLI (`aura`)

After `pip install -e .`, the `aura` command is on your PATH:

```
aura status             kernel + services state
aura doctor             system + environment validation
aura build [--verify]   build rootfs from source
aura repair             verify integrity, rebuild if drift detected
aura verify             check rootfs against manifest
aura test [-k filter]   run unit tests
aura test --conformance run conformance suite
aura logs [--tail N]    show system logs
aura mirror             mirror/projection mode status
aura host               host-bridge capabilities
aura boot-log           last boot lifecycle
aura provenance         build time, commit, environment
aura override <action>  request a Command Override Layer (COL) override
```

Or from inside the running OS shell:

```
aura> status            kernel state snapshot
aura> services          registered service states
aura> sysinfo           full JSON system snapshot
aura> device            hardware profile + compatibility
aura> model list        registered AI models
aura> model load X      activate a model
aura> model scan        auto-discover model files
aura> build             rebuild rootfs from inside the live OS
aura> repair            verify file integrity
aura> test              run unit tests in-process
aura> logs [N]          show last N log lines
aura> exit              shutdown
aura> <anything>        ask AURA
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   User / Shell                      │  ← text interface, permission prompts
├─────────────────────────────────────────────────────┤
│                     AURA                            │  ← AI personality, pulsed every tick
│              (Model Manager + Stub)                 │
├──────────────┬──────────────┬──────────────────────┤
│  Scheduler   │  EventBus    │  Service Manager      │  ← tasks, events, long-lived services
├──────────────┴──────────────┴──────────────────────┤
│              Kernel Loop  (Adaptive Tick)           │  ← 16 ms desktop / 100 ms mobile
├─────────────────────────────────────────────────────┤
│  KernelWatchdog  │  BuildService  │  Config          │  ← self-repair / self-build / tuning
├─────────────────────────────────────────────────────┤
│           Hardware Abstraction Layer (HAL)          │
│    vCPU  │  vMemory  │  vBus  │  VStorageDevice     │  ← SQLite-backed, mobile-safe
├─────────────────────────────────────────────────────┤
│              Host Bridge                            │  ← Android / Linux / macOS / Windows
│    (auto-detects Termux, routes syscalls)           │
└─────────────────────────────────────────────────────┘
```

### Design Notes

- **Adaptive tick** — idle kernel slows from 16 ms to 1 s, saving battery without sacrificing responsiveness.
- **SQLite virtual storage** — stdlib, ARM64-safe, single-file DB; no partition mount needed.
- **Watchdog daemon** — monitors all services every 5 s, auto-restarts on crash with exponential backoff, disables after 3 failures.
- **Self-build** — `BuildService` rebuilds rootfs, runs tests, and verifies SHA-256 integrity from a single shell command.
- **Zero required dependencies** — everything uses Python 3.10+ stdlib. AI inference, metrics, and ONNX are optional.

---

## AI Models

AURA ships in **stub mode** — fully functional without any model file.

### Ollama (recommended)

```bash
# Desktop: https://ollama.ai/
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull phi3

# Android/Termux: pkg install ollama
```

```
aura> model ollama phi3
aura> What services are running?
```

### OpenAI-compatible API

`config/user.json`:
```json
{
  "aura": {
    "backend":  "openai",
    "api_key":  "sk-...",
    "api_base": "https://api.openai.com/v1",
    "model":    "gpt-4o-mini"
  }
}
```

Or `OPENAI_API_KEY=sk-... python launch/launcher.py`.

### Local GGUF (llama-cpp-python)

```bash
pip install -e ".[ai]"
cp ~/Downloads/phi-2.Q4_K_M.gguf models/
```

```
aura> model scan
aura> model load phi-2
```

Supported: **GGUF** (llama-cpp-python), **ONNX** (onnxruntime), **Ollama**, **OpenAI-compatible API**, **stub**.

---

## Configuration

`config/default.json` is the base config. Create `config/user.json` for overrides (gitignored).

Environment variable overrides: `AURA_CFG_<SECTION>_<KEY>=value`

```bash
AURA_CFG_KERNEL_TICK_INTERVAL_MS=100 python launch/launcher.py   # force mobile tick rate
AURA_MODE=universal python launch/launcher.py                     # force a specific mode
```

Mobile profile is applied automatically on Android/Termux:
- Tick: 100 ms (10 Hz) instead of 16 ms
- Max RAM: 256 MB instead of 512 MB
- Task queue: 256 instead of 1 000

---

## Testing

```bash
pip install -e ".[test]"
python -m pytest tests/ -q          # 918 tests across 51 modules
python -m pytest tests/conformance/ # AI layer, boot, bridge, rootfs, shell, services
```

---

## Requirements

| Requirement | Minimum |
|-------------|---------|
| Python | 3.10+ |
| RAM | 256 MB |
| Storage | 100 MB |

**Optional:**
- `pip install -e ".[metrics]"` — `psutil` for enhanced CPU/memory metrics
- `pip install -e ".[ai]"` — `llama-cpp-python` (GGUF) + `onnxruntime` (ONNX) for local inference
- `pip install -e ".[test]"` — `pytest` to run the test suite

---

## Project Structure

```
AURA-AIOSCPU/
├── launch/         boot sequence (launcher.py)
├── kernel/         loop, scheduler, event bus, modes, watchdog, config, permissions
├── aura/           AI personality layer (memory, introspection, context, personality)
├── hal/            hardware abstraction: vCPU, vMemory, vBus, VStorageDevice (SQLite)
├── services/       service registry + health monitor, storage, network, job queue,
│                   logging, build service, web terminal
├── shell/          interactive shell + plugin loader
├── host_bridge/    host OS adapter (Android/Termux, Linux, macOS, Windows)
├── bridge/         bridge interface + per-platform implementations
├── models/         AI model manager (Ollama, OpenAI, GGUF, ONNX, stub)
├── tools/          aura_cli.py, check_requirements.py, validate_system.py, manifest.py
├── config/         default.json; create user.json for local overrides (gitignored)
├── rootfs/         minimal root filesystem layout (bin, etc, var, tmp, home, mnt, …)
├── tests/          918 tests across 51 modules (unit + conformance)
├── build.py        builds dist/ image
├── pyproject.toml  package metadata + `aura` CLI entry point
├── Dockerfile      Python 3.12-slim image, non-root, exposes :7331
├── deploy/         Railway (railway.json) + Render (render.yaml) configs
└── install_termux.sh  Android/Termux one-command installer
```

---

## Cloud Deploy

**Railway:**
```bash
railway login && railway up
```

**Render:** Import the repo — `render.yaml` is auto-detected.

Both serve the AURA web terminal at a public HTTPS URL.

---

## Contributing

1. Fork → branch → `pip install -e ".[test]"` → code
2. `python -m pytest tests/` — all tests must pass
3. Pull request

