# AURA-AIOSCPU — Complete User Manual

> **File:** `MANUAL.md`  
> **System:** AURA-AIOSCPU — AI-Driven Universal OS  
> **Covers:** Installation · Boot · Shell · AI Models · Configuration ·
> Services · Developer Tools · Copilot Bridge · Troubleshooting

---

## Table of Contents

1. [What Is AURA-AIOSCPU?](#1-what-is-aura-aioscpu)
2. [How It Works — Architecture Overview](#2-how-it-works--architecture-overview)
3. [Requirements](#3-requirements)
4. [Installation](#4-installation)
   - 4.1 [Android / Termux (Phone)](#41-android--termux-phone)
   - 4.2 [Desktop / Server (Linux, macOS, Windows)](#42-desktop--server-linux-macos-windows)
   - 4.3 [Docker Container](#43-docker-container)
   - 4.4 [Cloud Deploy (Railway / Render)](#44-cloud-deploy-railway--render)
5. [First Boot](#5-first-boot)
6. [The AURA Shell — Complete Command Reference](#6-the-aura-shell--complete-command-reference)
7. [AI Models — Setup and Use](#7-ai-models--setup-and-use)
   - 7.1 [Stub Mode (default, no setup needed)](#71-stub-mode-default-no-setup-needed)
   - 7.2 [Ollama (recommended)](#72-ollama-recommended)
   - 7.3 [OpenAI / Groq / Together API](#73-openai--groq--together-api)
   - 7.4 [Local GGUF File](#74-local-gguf-file)
   - 7.5 [ONNX Model](#75-onnx-model)
8. [Configuration Reference](#8-configuration-reference)
9. [Kernel Modes](#9-kernel-modes)
10. [Services Reference](#10-services-reference)
11. [Hardware Abstraction Layer (HAL)](#11-hardware-abstraction-layer-hal)
12. [Developer Tools](#12-developer-tools)
13. [Copilot Bridge — AI-Assisted Upgrade Advisor](#13-copilot-bridge--ai-assisted-upgrade-advisor)
14. [Running the Test Suite](#14-running-the-test-suite)
15. [Building a Distribution Image](#15-building-a-distribution-image)
16. [Logs](#16-logs)
17. [Troubleshooting](#17-troubleshooting)
18. [Project File Structure](#18-project-file-structure)
19. [Glossary](#19-glossary)

---

## 1. What Is AURA-AIOSCPU?

**AURA-AIOSCPU** is an AI-first operating system kernel written entirely in
Python.  It is designed to run on *any* device — from a budget Android phone
running Termux to a cloud server — without needing native compilation or
privileged access.

Key properties at a glance:

| Property | Description |
|----------|-------------|
| **Runs anywhere Python runs** | Android, Linux, macOS, Windows, ARM64, x86_64 |
| **Self-healing** | A watchdog daemon restarts crashed services automatically |
| **Self-building** | The running OS can rebuild its own rootfs from source |
| **AI assistant built in** | AURA personality layer answers questions and monitors the system |
| **Zero required dependencies** | Only Python 3.10+ stdlib needed to boot |
| **SQLite virtual storage** | No filesystem partitions needed; all data in a single SQLite file |
| **Battery-aware** | Adaptive tick rate slows the kernel to 1 s/tick when idle |

---

## 2. How It Works — Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   User / Shell                      │  ← text interface,
│               (you type commands here)              │    permission prompts
├─────────────────────────────────────────────────────┤
│                     AURA                            │  ← AI personality,
│              (Model Manager + Stub)                 │    pulsed every tick
├──────────────┬──────────────┬──────────────────────┤
│  Scheduler   │  EventBus    │  Service Manager      │  ← tasks, events,
│              │              │                       │    long-lived services
├──────────────┴──────────────┴──────────────────────┤
│              Kernel Loop  (Adaptive Tick)           │  ← 16 ms desktop /
│                                                     │    100 ms mobile
├─────────────────────────────────────────────────────┤
│  KernelWatchdog  │  BuildService  │  Config          │  ← self-repair /
│                  │                │                 │    self-build / tuning
├─────────────────────────────────────────────────────┤
│           Hardware Abstraction Layer (HAL)          │
│    vCPU  │  vMemory  │  vBus  │  VStorageDevice     │  ← SQLite-backed,
│                                                     │    mobile-safe
├─────────────────────────────────────────────────────┤
│              Host Bridge                            │  ← Android / Linux /
│    (auto-detects Termux, routes syscalls)           │    macOS / Windows
└─────────────────────────────────────────────────────┘
```

### Layer-by-layer explanation

**Shell** — The text interface you interact with.  Accepts built-in commands
and free-text questions.  Free-text is forwarded to the AURA AI layer.

**AURA** — The AI personality layer.  Every kernel tick, AURA receives a
"pulse" containing the current system state (running services, recent events,
tick number).  When you ask a question, AURA uses this live context plus the
active AI model to generate a reply.  If no model is configured, a built-in
stub responds with useful context-aware messages.

**Scheduler + EventBus + Service Manager** — The scheduler queues tasks with
priorities and executes them each tick.  The EventBus is a publish/subscribe
system that decouples components.  The Service Manager starts, stops, and
monitors long-lived background services.

**Kernel Loop** — The heartbeat.  Fires every 16 ms on desktop (62 Hz) and
every 100 ms on phones (10 Hz).  Goes as slow as 1 000 ms when idle to save
battery.  Each tick: processes the event bus, runs the scheduler, pulses AURA,
checks the watchdog.

**KernelWatchdog** — A daemon thread that checks all services every 5 seconds.
If a service has crashed, it restarts it with exponential back-off (up to a
configurable maximum number of attempts).

**BuildService** — Lets the *running* OS rebuild its own rootfs, run the test
suite, and verify SHA-256 file integrity — all from the `build` shell command.

**HAL (Hardware Abstraction Layer)** — Virtualises CPU, memory, bus, and
storage.  The storage backend is a SQLite database (`rootfs/var/aura.db`) that
lives entirely in a single file, making it easy to copy to an SD card or back
up.

**Host Bridge** — Detects the host OS (Android/Termux, Linux, macOS, Windows)
and routes platform-specific calls (filesystem paths, process management,
network access) through the appropriate adapter.

---

## 3. Requirements

### Minimum

| Item | Minimum |
|------|---------|
| Python | 3.10 |
| RAM | 256 MB |
| Disk | 100 MB |
| Architecture | Any Python-supported arch |

### Recommended

| Item | Recommended |
|------|-------------|
| Python | 3.12 LTS |
| RAM | 1 GB+ |
| Disk | 500 MB+ |
| Architecture | ARM64 or x86_64 |

### Optional Python packages

These are *never* required — AURA boots without them — but they enable
additional features:

| Package | Feature | Install |
|---------|---------|---------|
| `psutil` | Accurate CPU / memory / disk metrics | `pip install psutil` |
| `llama-cpp-python` | On-device GGUF AI inference (ARM64) | `pip install llama-cpp-python` |
| `onnxruntime` | ONNX AI model inference | `pip install onnxruntime` |
| `uvicorn` + `fastapi` | Production ASGI server for web terminal | `pip install uvicorn fastapi` |
| `cryptography` | Encrypted storage + signed build manifests | `pip install cryptography` |

---

## 4. Installation

### 4.1 Android / Termux (Phone)

> **Requires:** Termux from [F-Droid](https://f-droid.org/packages/com.termux/)
> (NOT Google Play — the Play version is outdated).

```bash
# 1. Open Termux
# 2. Run:
pkg install git python
git clone https://github.com/Cbetts1/AURA-AIOSCPU
cd AURA-AIOSCPU
bash install_termux.sh
```

`install_termux.sh` does everything automatically:
- Installs Python dependencies
- Builds the rootfs
- Runs a compatibility check
- Launches AURA

**Check compatibility before installing:**
```bash
python tools/check_requirements.py
```

### 4.2 Desktop / Server (Linux, macOS, Windows)

```bash
git clone https://github.com/Cbetts1/AURA-AIOSCPU
cd AURA-AIOSCPU
pip install -e .          # installs deps and the `aura` CLI
python launch/launcher.py
```

After `pip install -e .` the `aura` command is on your PATH:

```bash
aura status     # kernel + service state
aura doctor     # deep system + environment validation
aura build      # build rootfs from source
aura test       # run test suite
aura logs       # show system logs
```

### 4.3 Docker Container

```bash
docker build -t aura-aioscpu .
docker run -it -p 7331:7331 aura-aioscpu
```

Open **http://localhost:7331** for the browser-based web terminal.

For persistent memory across container restarts:
```bash
docker run -it -p 7331:7331 -v aura_data:/app/rootfs/aura aura-aioscpu
```

### 4.4 Cloud Deploy (Railway / Render)

**Railway:**
```bash
railway login && railway up
```

**Render:**  
Import the repo in the Render dashboard — `render.yaml` is auto-detected.

Both platforms expose the AURA web terminal at a public HTTPS URL.

---

## 5. First Boot

When AURA boots you will see a banner followed by the shell prompt:

```
[INFO] launcher: config loaded
[INFO] launcher: device profile arch=x86_64 mobile=False mem=8192MB cpus=8
[INFO] launcher: detected mode=universal
[INFO] launcher: rootfs OK at '.../rootfs'
[INFO] kernel: starting in universal mode
[INFO] kernel: services started: health_monitor, logging, network, storage, build
aura>
```

### What happens during boot

1. **Logging** — `logs/aura.log` is opened (rotating, 10 MB × 3).
2. **Config** — `config/default.json` is loaded, then `config/user.json` if it
   exists, then any `AURA_CFG_*` environment variables.
3. **Device profile** — Architecture, CPU count, RAM, and mobile detection run.
   If on Android/Termux, the mobile profile (100 ms tick, 256 MB RAM cap) is
   applied automatically.
4. **Mode detection** — Defaults to `universal`.  Runs as `internal` if root.
   Override with `AURA_MODE=hardware|internal|universal`.
5. **rootfs mount** — Checks that `rootfs/{bin,etc,usr,var,tmp,home}` exist.
6. **Kernel + services** — Kernel loop starts; services autostart.

---

## 6. The AURA Shell — Complete Command Reference

Type any command at the `aura>` prompt.  Anything that is not a built-in
command is passed to the AURA AI layer as a question.

### Built-in commands

| Command | Description |
|---------|-------------|
| `help` | Show all built-in commands |
| `status` | Kernel state snapshot (tick, mode, uptime, services) |
| `services` | List registered services and their current state |
| `sysinfo` | Full JSON system snapshot (kernel + HAL + services + AI) |
| `device` | Hardware profile: architecture, CPU count, RAM, mobile flag |
| `model list` | Show registered AI models |
| `model load <name>` | Activate a model by name |
| `model scan` | Auto-discover new `.gguf` files in the `models/` directory |
| `model ollama <name>` | Switch to an Ollama-hosted model |
| `model openai <name>` | Switch to an OpenAI-compatible API model |
| `build` | Rebuild AURA rootfs from source (self-build) |
| `repair` | Verify file integrity; show what has changed since last build |
| `test` | Run the unit test suite from inside the live OS |
| `logs [N]` | Show last N log lines (default 20) |
| `exit` / `quit` | Graceful shutdown |

### Asking AURA questions

Any text that is not a known command is forwarded to the AI:

```
aura> What services are running and do any need attention?
aura> How much memory is the HAL using?
aura> Why is the tick rate 100 ms?
aura> What does the watchdog do?
```

AURA always includes the live system state in its context window, so answers
are specific to *your* running instance.

---

## 7. AI Models — Setup and Use

### 7.1 Stub Mode (default, no setup needed)

Out of the box AURA uses a built-in stub that generates context-aware replies
from the live system state without any AI model.  Every question gets a
meaningful response.  You do not need to configure anything to get started.

### 7.2 Ollama (recommended)

[Ollama](https://ollama.ai/) runs models locally with zero compilation.

**Desktop / Server:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull phi3        # or llama3, mistral, gemma, etc.
```

**Android / Termux:**
```bash
pkg install ollama
ollama pull phi3
```

**Activate inside AURA:**
```
aura> model ollama phi3
```

Or set it permanently in `config/user.json`:
```json
{
  "aura": {
    "backend": "ollama",
    "model":   "phi3"
  }
}
```

### 7.3 OpenAI / Groq / Together API

Add to `config/user.json`:
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

Or via environment variable (no file needed):
```bash
OPENAI_API_KEY=sk-... python launch/launcher.py
```

Then inside AURA:
```
aura> model openai gpt-4o-mini
```

Compatible with: **OpenAI**, **Groq** (`api_base: https://api.groq.com/openai/v1`),
**Together AI**, **Ollama's OpenAI endpoint**, any OpenAI-compatible server.

### 7.4 Local GGUF File

```bash
# Copy any GGUF model file into the models/ directory:
cp ~/Downloads/phi-2.Q4_K_M.gguf models/

# Install the inference engine (compile for your arch):
pip install llama-cpp-python

# Inside AURA:
aura> model scan          # auto-registers the file
aura> model list          # confirm it appears
aura> model load phi-2    # activate
```

Supported architectures: ARM64, x86_64, Apple Silicon (Metal), CUDA.

### 7.5 ONNX Model

```bash
pip install onnxruntime

# Copy .onnx file to models/
cp ~/Downloads/model.onnx models/

aura> model scan
aura> model load model
```

---

## 8. Configuration Reference

AURA loads configuration in this order (later sources win):

1. Built-in defaults (hardcoded)
2. `config/default.json`
3. `config/user.json` *(create this file for your personal settings)*
4. Environment variables: `AURA_CFG_<SECTION>_<KEY>=value`

### config/default.json — full annotated listing

```jsonc
{
  "kernel": {
    "tick_interval_ms":   16,     // Desktop: 16 ms (62 Hz). Auto-overridden on mobile.
    "max_task_queue":     1000,   // Maximum pending tasks before new ones are dropped.
    "adaptive_tick":      true,   // Slow kernel to 1 s when idle (saves battery).
    "idle_backoff_factor": 2,     // Multiply tick interval by this when idle.
    "max_tick_interval_ms": 1000  // Slowest tick allowed (1 second).
  },
  "aura": {
    "model_dir":          "models",  // Directory scanned for AI model files.
    "active_model":       null,      // Name of model to load on boot (null = stub).
    "context_window":     4096,      // Tokens of context sent to the model.
    "max_response_tokens": 512,      // Maximum tokens in an AI response.
    "response_cache_size": 128       // LRU cache for repeated identical queries.
  },
  "services": {
    "autostart":          true,   // Start all registered services on boot.
    "max_services":       32,     // Maximum number of registered services.
    "restart_backoff_ms": 5000,   // Initial delay before restarting a crashed service.
    "max_restart_attempts": 5     // Give up restarting after this many attempts.
  },
  "hal": {
    "storage_path": "rootfs/var/aura.db",  // SQLite database file path.
    "max_memory_mb": 512,                  // Virtual memory cap (MB).
    "storage_backend": "sqlite"            // Only sqlite is supported currently.
  },
  "logging": {
    "level":          "INFO",   // DEBUG / INFO / WARNING / ERROR / CRITICAL
    "log_dir":        "logs",   // Directory for log files.
    "max_log_size_mb": 10,      // Each log file max size before rotation.
    "rotation_count":  3,       // Keep this many rotated log files.
    "structured":      true     // Include timestamps and log level in output.
  },
  "mobile": {
    "power_save":         false, // Extra power saving (reduces service polling).
    "tick_interval_ms":   100,   // 10 Hz — applied automatically on Android.
    "max_memory_mb":      256,   // Lower RAM cap on phones.
    "max_task_queue":     256    // Smaller task queue on phones.
  },
  "watchdog": {
    "enabled":           true,   // Enable automatic crash recovery.
    "check_interval_ms": 5000,   // Check all services every 5 seconds.
    "max_failures":      3,      // Flag a service as dead after this many crashes.
    "auto_restart":      true    // Restart crashed services automatically.
  },
  "build": {
    "output_dir": "dist",        // Where `build` writes the distribution image.
    "rootfs_dir": "rootfs",      // Source rootfs directory.
    "packages": [                // Python packages included in the build.
      "kernel", "hal", "aura", "services", "shell",
      "host_bridge", "models", "tools", "config", "launch"
    ]
  }
}
```

### Environment variable overrides

Any config value can be set without editing files:

```bash
# Set tick rate to 50 ms:
AURA_CFG_KERNEL_TICK_INTERVAL_MS=50 python launch/launcher.py

# Switch to DEBUG logging:
AURA_CFG_LOGGING_LEVEL=DEBUG python launch/launcher.py

# Disable adaptive tick:
AURA_CFG_KERNEL_ADAPTIVE_TICK=false python launch/launcher.py

# Force mobile profile:
AURA_MODE=universal AURA_CFG_KERNEL_TICK_INTERVAL_MS=100 python launch/launcher.py
```

---

## 9. Kernel Modes

The kernel boots in one of three modes, selected automatically or overridden
with `AURA_MODE=<mode>`.

| Mode | When used | Description |
|------|-----------|-------------|
| `universal` | Default for non-root users | Most portable.  Runs on top of any host OS using the host bridge.  All subsystems active. |
| `internal` | Root / privileged user | Runs with elevated permissions, borrows host OS resources more deeply. |
| `hardware` | Bare-metal / VM | Projects a runtime directly into hardware when allowed. |

**Override:**
```bash
AURA_MODE=hardware python launch/launcher.py
```

---

## 10. Services Reference

Services are long-lived background processes managed by the Service Manager.
All services autostart on boot (unless `services.autostart` is `false`).

| Service | File | Description |
|---------|------|-------------|
| **Health Monitor** | `services/health_monitor.py` | Polls kernel health metrics every 10 s and publishes `HEALTH_UPDATE` events. |
| **Logging Service** | `services/logging_service.py` | Consumes `LOG` events from the EventBus and writes them to `logs/aura.log`. |
| **Network Service** | `services/network_service.py` | Probes host connectivity; publishes `NETWORK_STATUS` events. |
| **Storage Service** | `services/storage_service.py` | Manages the VStorageDevice lifecycle; handles `STORAGE_READ` / `STORAGE_WRITE` events. |
| **Build Service** | `services/build_service.py` | Exposes `build` and `repair` shell commands; verifies rootfs SHA-256 integrity. |
| **Job Queue** | `services/job_queue.py` | Priority-ordered background job runner. |
| **Registry** | `services/registry.py` | Service discovery and registration. |
| **Package Manager** | `services/package_manager.py` | Tracks installed AURA packages in `rootfs/var/packages.json`. |
| **Web Terminal** | `services/web_terminal.py` | Serves the browser-based terminal at `http://localhost:7331`. |

### Managing services from the shell

```
aura> services              # list all services and their state
aura> status                # includes service summary
```

---

## 11. Hardware Abstraction Layer (HAL)

The HAL virtualises four hardware classes so AURA can run without physical
hardware or kernel privileges.

| Virtual Device | Class | Description |
|---------------|-------|-------------|
| **vCPU** | `hal/devices/cpu.py` | Virtual processor — executes HAL tasks, reports load. |
| **vMemory** | `hal/devices/memory.py` | Virtual memory — allocates and tracks regions up to `max_memory_mb`. |
| **vBus** | `hal/devices/bus.py` | Virtual bus — routes device-to-device messages. |
| **VStorageDevice** | `hal/devices/storage.py` | SQLite-backed file + key/value store.  Single `.db` file. |

### VStorageDevice — how to use from code

```python
from hal.devices.storage import VStorageDevice

dev = VStorageDevice("rootfs/var/myapp.db")
dev.start()

# Key-value store (namespace, key, value)
dev.kv_set("settings", "theme", "dark")
theme = dev.kv_get("settings", "theme")   # → "dark"

# File store (virtual path, bytes)
dev.file_write("/data/config.json", b'{"version": 1}')
raw = dev.file_read("/data/config.json")

dev.stop()
```

---

## 12. Developer Tools

All tools live in the `tools/` directory and are runnable from the repo root.

| Tool | Command | Description |
|------|---------|-------------|
| **System Validation** | `python tools/validate_system.py` | End-to-end check of the full OS stack.  Use `--json` for CI. |
| **Copilot Bridge** | `python tools/copilot_bridge.py` | Runs all checks + generates a Markdown upgrade report. See [Section 13](#13-copilot-bridge--ai-assisted-upgrade-advisor). |
| **Requirements Check** | `python tools/check_requirements.py` | Pre-flight compatibility check (Python version, platform, optional deps). |
| **System Info** | `python tools/aura_sys_info.py` | Hardware profile + full compatibility report. |
| **Logs Viewer** | `python tools/aura_logs.py` | View or follow `logs/aura.log` live. |
| **Service Status** | `python tools/aura_service_status.py` | Inspect systemd-style `.service` unit files. |
| **CLI** | `python tools/aura_cli.py` | Programmatic command interface (used by `aura` entry point). |
| **Portability** | `python tools/portability.py` | Cross-platform compatibility tests. |
| **Manifest** | `python tools/manifest.py` | Generate / verify the build manifest (SHA-256 hashes). |

### validate_system.py flags

```bash
python tools/validate_system.py              # human-readable report
python tools/validate_system.py --strict     # exit 1 on warnings too
python tools/validate_system.py --json       # machine-readable JSON (for CI)
```

---

## 13. Copilot Bridge — AI-Assisted Upgrade Advisor

### What is the Copilot Bridge?

`tools/copilot_bridge.py` is a diagnostic script that acts as a **bridge**
between AURA-AIOSCPU and GitHub Copilot (or any AI assistant).

It automatically:

1. **Runs the system validation suite** — checks Python version, all imports,
   kernel, HAL, storage, shell, services, and rootfs layout.
2. **Runs the full test suite** — captures pytest output and highlights any
   failures.
3. **Audits dependencies** — identifies optional packages that are not
   installed but would improve performance or enable new features.
4. **Reviews configuration** — checks for sub-optimal settings and suggests
   improvements.
5. **Checks upgrade opportunities** — looks for missing CI workflows, missing
   documentation, absent type annotations, and other code-level improvements.
6. **Writes `copilot_report.md`** — a self-contained Markdown file that
   Copilot can read and use to explain each recommendation in plain English.

### How to run it

```bash
# Full run (validation + tests + all checks):
python tools/copilot_bridge.py

# Skip the (slow) pytest run for a faster check:
python tools/copilot_bridge.py --no-tests

# Save report to a custom path:
python tools/copilot_bridge.py --output my_report.md

# Machine-readable JSON (for CI pipelines):
python tools/copilot_bridge.py --no-tests --json
```

### How to use the report with GitHub Copilot

After running the bridge, open `copilot_report.md` in VS Code.  Then:

1. Open **Copilot Chat** (Ctrl+I or the chat icon in the sidebar).
2. Type: *"Read copilot_report.md and explain the upgrade recommendations in
   plain language.  What should I do first?"*
3. Copilot reads the structured report and explains each `🔧 Upgrade
   Recommendation` — what it does, why it helps, and how to apply it.
4. Ask follow-up questions:
   - *"Apply the psutil recommendation for me."*
   - *"Show me how to add the Copilot instructions file."*
   - *"What would happen if I enabled the cryptography package?"*

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All checks pass, no upgrades needed |
| `1` | One or more hard failures detected |
| `2` | No failures, but upgrade recommendations exist |

### How the bridge connects to the system

```
tools/copilot_bridge.py
        │
        ├── tools/validate_system.py   (imported directly — no subprocess)
        │       └── checks Python, imports, kernel, HAL,
        │           storage, shell, services, rootfs …
        │
        ├── pytest tests/              (subprocess, captures output)
        │
        ├── dependency audit           (importlib.util.find_spec)
        │
        ├── config review              (kernel.config.Config)
        │
        └── upgrade hints              (static file-system checks)
                │
                └──► copilot_report.md  (open this with Copilot Chat)
```

---

## 14. Running the Test Suite

```bash
# Full suite (all 572+ tests across 30 modules):
python -m pytest tests/ -v

# Quiet summary only:
python -m pytest tests/ -q

# Single module:
python -m pytest tests/test_kernel_loop.py -v

# With coverage report:
pip install pytest-cov
python -m pytest tests/ --cov=. --cov-report=term-missing
```

### What is tested

| Area | Test file(s) |
|------|-------------|
| Kernel loop | `test_kernel_loop.py` |
| Scheduler | `test_scheduler.py` |
| EventBus | `test_event_bus.py` |
| Kernel modes | `test_kernel_modes.py` |
| Kernel API | `test_kernel_api.py` |
| Config system | `test_config.py` |
| Device profile | `test_device_profile.py` |
| HAL | `test_hal.py` |
| VStorageDevice | `test_storage.py`, `test_storage_service.py` |
| KernelWatchdog | `test_watchdog.py`, `test_watchdog_integrity.py` |
| BuildService | `test_build_service.py`, `test_build_snapshot.py` |
| ModelManager | `test_model_manager.py`, `test_ai_engines.py` |
| AURA personality | `test_aura.py`, `test_personality.py`, `test_context_builder.py` |
| Shell | `test_shell.py` |
| Services | `test_services.py`, `test_health_monitor.py`, `test_logging_service.py`, `test_network_service.py`, `test_job_queue.py`, `test_registry.py`, `test_package_manager.py` |
| Web Terminal | `test_web_terminal.py`, `test_web_terminal_rest.py` |
| Host Bridge | `test_bridge.py`, `test_bridge_contract.py` |
| Permissions | `test_permissions.py`, `test_privilege.py` |
| Memory | `test_memory.py`, `test_memory_persistence.py` |
| Portability | `test_portability.py` |
| System Validation | `test_validate_system.py` |
| **Copilot Bridge** | **`test_copilot_bridge.py`** |

---

## 15. Building a Distribution Image

```bash
# Build the dist/ image (does not run tests):
python build.py

# Run tests first, then build:
python build.py --test

# Launch the built image directly:
python dist/aura
```

The build process:
1. Copies all source packages to `dist/`.
2. Packages the rootfs.
3. Computes SHA-256 hashes for all files (written to `dist/manifest.json`).
4. The `repair` shell command later compares live files against this manifest.

---

## 16. Logs

Logs are written to `logs/aura.log` with automatic rotation (10 MB × 3 files).

```bash
# Follow live:
python tools/aura_logs.py --follow

# Show last 50 lines:
python tools/aura_logs.py -n 50

# From inside the AURA shell:
aura> logs 50
```

Log format:
```
2024-01-15 12:34:56,789 [INFO] kernel.loop: tick 42 — 5 tasks executed
2024-01-15 12:34:56,801 [INFO] services.watchdog: all 5 services healthy
```

---

## 17. Troubleshooting

### "rootfs is not ready — Cannot boot"

The `rootfs/` directory is missing required subdirectories.  Fix:
```bash
python build.py        # rebuilds the rootfs
# or manually:
mkdir -p rootfs/{bin,etc,usr,var,tmp,home}
```

### "Module 'X' not found"

```bash
pip install -e .       # reinstalls all Python packages
```

### Tests fail with "rootfs/mnt partition missing"

```bash
mkdir -p rootfs/mnt
touch rootfs/mnt/.gitkeep
```

### "Port 7331 already in use" (web terminal)

```bash
# Find and stop the process using the port:
lsof -ti:7331 | xargs kill -9

# Or configure a different port in config/user.json:
{
  "web_terminal": { "port": 7332 }
}
```

### AURA is responding slowly

1. Check if an AI model is loaded: `aura> model list`
2. If using a large GGUF model, reduce the context window:
   ```json
   { "aura": { "context_window": 2048 } }
   ```
3. Enable adaptive tick if disabled:
   ```json
   { "kernel": { "adaptive_tick": true } }
   ```

### Services keep crashing

Check the logs for the specific error:
```bash
python tools/aura_logs.py -n 200 | grep ERROR
```

Then run the watchdog repair:
```
aura> repair
```

### "Python X.Y — need ≥ 3.10"

Install Python 3.10 or newer.  On Android:
```bash
pkg install python
```
On Ubuntu/Debian:
```bash
sudo apt install python3.12
```

### Copilot Bridge reports failures

Run without tests for faster diagnosis:
```bash
python tools/copilot_bridge.py --no-tests
```
Then open `copilot_report.md` and look at the **❌ Failures** section.

---

## 18. Project File Structure

```
AURA-AIOSCPU/
│
├── launch/                 Boot sequence
│   ├── launcher.py         Entry point — boot, config, kernel start
│   └── boot.py             Low-level boot helpers
│
├── kernel/                 Core OS kernel
│   ├── __init__.py         Kernel class
│   ├── loop.py             Adaptive tick loop
│   ├── scheduler.py        Priority task queue
│   ├── event_bus.py        Publish-subscribe event system
│   ├── config.py           Config load/merge/env-override
│   ├── device_profile.py   Hardware detection + tick recommendations
│   ├── watchdog.py         Auto-restart crashed services
│   ├── permissions.py      Permission model
│   ├── privilege.py        Privilege escalation
│   ├── override.py         Runtime setting overrides
│   ├── mirror.py           Kernel state mirroring
│   ├── debug.py            Debug helpers
│   ├── api.py              Public kernel API
│   └── modes/              Kernel mode implementations
│       ├── universal.py    Universal mode (default)
│       ├── internal.py     Internal / privileged mode
│       └── hardware.py     Hardware projection mode
│
├── aura/                   AI personality layer
│   ├── __init__.py         AURA class (pulse + query)
│   ├── personality.py      Response style + persona
│   ├── context_builder.py  Build system-state context for AI
│   ├── memory.py           Conversation history
│   └── introspection.py    Self-inspection helpers
│
├── hal/                    Hardware Abstraction Layer
│   ├── __init__.py         HAL class
│   └── devices/
│       ├── cpu.py          Virtual CPU
│       ├── memory.py       Virtual memory
│       ├── bus.py          Virtual bus
│       └── storage.py      VStorageDevice (SQLite)
│
├── services/               Long-lived background services
│   ├── health_monitor.py   System health poller
│   ├── logging_service.py  EventBus → log file
│   ├── network_service.py  Connectivity probe
│   ├── storage_service.py  VStorageDevice manager
│   ├── build_service.py    Self-build + integrity verify
│   ├── job_queue.py        Background job runner
│   ├── registry.py         Service discovery
│   ├── package_manager.py  Package tracking
│   └── web_terminal.py     Browser-based terminal (port 7331)
│
├── shell/                  Interactive shell
│   ├── __init__.py         Shell class + command dispatch
│   ├── plugin_loader.py    Load shell command plugins
│   └── plugins/            Extensible command plugins
│
├── host_bridge/            Host OS adapters
│   ├── __init__.py         Auto-detects host and returns adapter
│   ├── base.py             Base adapter interface
│   ├── android.py          Android / Termux adapter
│   ├── linux.py            Linux adapter
│   ├── macos.py            macOS adapter
│   └── windows.py          Windows adapter
│
├── models/                 AI model manager
│   ├── __init__.py
│   └── model_manager.py    Register / load / unload / scan / stub
│
├── tools/                  Developer CLI tools
│   ├── validate_system.py  End-to-end system check
│   ├── copilot_bridge.py   ← Copilot upgrade advisor (NEW)
│   ├── check_requirements.py  Pre-flight checker
│   ├── aura_sys_info.py    Hardware profile report
│   ├── aura_logs.py        Log viewer
│   ├── aura_service_status.py  Service unit inspector
│   ├── aura_cli.py         CLI entry point
│   ├── manifest.py         SHA-256 manifest generator
│   └── portability.py      Cross-platform tests
│
├── config/
│   ├── default.json        Built-in defaults (do not edit)
│   └── user.json           Your overrides (gitignored, create this)
│
├── rootfs/                 Minimal root filesystem
│   ├── bin/                Executable stubs
│   ├── etc/                Config files
│   ├── usr/                User programs
│   ├── var/                Runtime data (aura.db lives here)
│   ├── tmp/                Temporary files
│   └── home/               User home directory
│
├── tests/                  Test suite (572+ tests, 30+ modules)
│
├── logs/                   Rotating log files (auto-created)
│
├── deploy/                 Cloud deployment configs
│   ├── railway.json
│   └── render.yaml
│
├── build.py                Build script → dist/
├── pyproject.toml          Package metadata + `aura` CLI entry point
├── Dockerfile              Minimal Docker image
├── install_termux.sh       One-command Android installer
├── requirements.txt        Python dependencies
├── README.md               Quick-start guide
└── MANUAL.md               ← This file
```

---

## 19. Glossary

| Term | Definition |
|------|-----------|
| **Adaptive tick** | Kernel feature that automatically slows the tick rate when the system is idle, saving battery and CPU. |
| **AURA** | The AI personality layer.  Receives a system "pulse" every tick and answers user questions. |
| **EventBus** | Publish-subscribe message system that decouples kernel components.  Services publish events; listeners react. |
| **HAL** | Hardware Abstraction Layer.  Virtualises CPU, memory, bus, and storage so AURA can run without real hardware access. |
| **Host Bridge** | Platform adapter that detects the host OS (Android, Linux, macOS, Windows) and routes calls appropriately. |
| **Internal Mode** | Kernel mode for root/privileged operation.  Has deeper access to host OS resources. |
| **rootfs** | Root filesystem — the directory tree (`bin/`, `etc/`, `var/`, etc.) that AURA boots into. |
| **Scheduler** | Priority-ordered task queue.  Tasks are submitted with a priority integer and executed each tick. |
| **Stub mode** | AURA's fallback AI mode when no model is configured.  Generates context-aware replies from live system state. |
| **Universal Mode** | The default kernel mode.  Runs on any host OS using the host bridge.  Most portable. |
| **VStorageDevice** | Virtual storage device backed by a SQLite database.  Provides a key-value store and a virtual file store. |
| **Watchdog** | Daemon thread that monitors all services every 5 s and restarts any that have crashed. |
| **GGUF** | A compact AI model format supported by `llama-cpp-python`.  Used for on-device inference. |
| **Copilot Bridge** | `tools/copilot_bridge.py` — runs all diagnostics and produces a report for GitHub Copilot to analyse. |

---

<div align="center">

**AURA-AIOSCPU** — *Built to run everywhere. Designed to think. Made to last.*

</div>
