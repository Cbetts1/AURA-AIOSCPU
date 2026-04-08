<div align="center">

# AURA-AIOSCPU

**AI-Driven Universal OS — Runs on Anything. Repairs Itself. Thinks for You.**

[![Tests](https://img.shields.io/badge/tests-516%20passing-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Android%20%7C%20Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](#)
[![Architecture](https://img.shields.io/badge/arch-ARM64%20%7C%20x86__64%20%7C%20ARM-orange)](#)
[![License](https://img.shields.io/badge/license-MIT-green)](#)

*The operating system that runs on your phone, laptop, SD card, or cloud server —
with a built-in AI that watches your system, answers your questions, and fixes
itself if something breaks.*

</div>

---

## ✨ What Makes AURA Different

| Feature | AURA-AIOSCPU | Traditional OS |
|---------|-------------|----------------|
| **Runs on Android/Termux** | ✅ One command | ❌ Reflash required |
| **Self-repairs on crash** | ✅ Watchdog daemon | ❌ Manual restart |
| **Rebuilds itself from source** | ✅ `rebuild` in shell | ❌ External build system |
| **AI assistant built in** | ✅ Always live context | ❌ Add-on app |
| **Zero native dependencies** | ✅ Pure Python stdlib | ❌ Requires toolchain |
| **Mobile battery saving** | ✅ Adaptive tick rate | ❌ Fixed polling |
| **SQLite virtual storage** | ✅ No filesystem mount | ❌ Partition required |

---

## 📱 Run on Your Android Phone (60 seconds)

> **Requires:** Termux app from [F-Droid](https://f-droid.org/packages/com.termux/) + Python 3.10+

```bash
# 1. Install Termux from F-Droid (NOT Google Play)
# 2. Open Termux and run:

pkg install git python
git clone https://github.com/Cbetts1/AURA-AIOSCPU
cd AURA-AIOSCPU
bash install_termux.sh
```

That's it. `install_termux.sh` installs dependencies, builds the rootfs,
runs a compatibility check, and launches AURA — all automatically.

**Check your phone is compatible first:**
```bash
python tools/check_requirements.py
```

---

## 🖥️ Run on Desktop / Server

```bash
git clone https://github.com/Cbetts1/AURA-AIOSCPU
cd AURA-AIOSCPU
pip install -e .        # installs deps and the `aura` CLI command
python launch/launcher.py
```

Once installed, `aura` is on your PATH:

```bash
aura status             # kernel + services state
aura doctor             # deep system + environment validation
aura build              # build rootfs from source
aura test               # run test suite
aura logs               # show system logs
```

Or build first for a clean self-contained image:

```bash
python build.py --test     # run tests, then build
python dist/aura           # launch the built image
```

---

## 🧠 Add AI Intelligence

AURA ships in **stub mode** — it always works, even without a model file.

### Option A — Ollama (recommended, zero compilation)

```bash
# On desktop/server: https://ollama.ai/
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull phi3        # or llama3, mistral, etc.

# On Android/Termux: pkg install ollama
```

Then inside the AURA shell:
```
aura> model ollama phi3     # activate Ollama backend
aura> What services are running?
```

### Option B — OpenAI-compatible API (GPT-4, Groq, Together, etc.)

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

Or set `OPENAI_API_KEY` environment variable and run:
```
aura> model openai gpt-4o-mini
```

### Option C — Local GGUF file (llama-cpp-python)

```bash
cp ~/Downloads/phi-2.Q4_K_M.gguf models/

# Then inside AURA:
aura> model scan          # auto-register
aura> model load phi-2    # activate
aura> What services are running?
```

Supported formats: **GGUF** (llama-cpp-python), **ONNX** (onnxruntime), **Ollama**, **OpenAI-compatible API**.
All are optional — AURA falls back to a context-aware stub if none are configured.

---

## 🔧 Shell Commands

```
aura> help            show this list
aura> status          kernel state snapshot
aura> services        registered services and states
aura> sysinfo         full JSON system snapshot
aura> device          hardware profile + phone compatibility info
aura> model list      show registered AI models
aura> model load X    activate a model
aura> model scan      auto-discover new model files
aura> build           rebuild AURA rootfs from source (self-build)
aura> repair          verify file integrity, show what changed
aura> test            run unit tests from inside the live OS
aura> logs [N]        show last N log lines
aura> exit            shutdown
aura> <anything>      ask AURA directly
```

---

## 🏗️ Architecture

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

### Key Design Decisions

- **Adaptive tick rate** — the kernel loop slows from 16 ms to 1 second when idle, saving battery on phones without sacrificing responsiveness when busy.
- **SQLite virtual storage** — ships in Python stdlib, works on ARM64 without native compilation, single-file DB you can copy to an SD card.
- **Self-repair watchdog** — a daemon thread monitors all services every 5 seconds and restarts any that crash, with exponential backoff and a failure cap.
- **Self-build service** — the running OS can rebuild its own rootfs, run the test suite, and verify SHA-256 file integrity — all from a shell command.
- **Zero required dependencies** — only Python 3.10+ stdlib. AI inference, enhanced metrics, and ONNX are optional.

---

## 🔬 Developer Tools

```bash
python tools/aura_sys_info.py         # hardware profile + compatibility check
python tools/check_requirements.py    # pre-flight checker for any device
python tools/aura_logs.py             # view / follow live logs
python tools/aura_service_status.py   # inspect service unit files
```

---

## 🧪 Testing

```bash
python -m pytest tests/ -v    # 516+ tests across 26 modules
```

Test coverage:
- Kernel loop, scheduler, event bus, HAL, modes
- AURA personality, shell, host bridge, services
- **Config** — loading, merging, env overrides, mobile profile, persistence
- **Device profile** — architecture detection, tick recommendations
- **VStorageDevice** — KV store, file store, SQLite integrity, stats
- **KernelWatchdog** — failure tracking, auto-restart, backoff, event publishing
- **BuildService** — rootfs build, integrity verification, event lifecycle
- **ModelManager** — register, load/unload, scan, thread safety, stub fallback

---

## ⚙️ Configuration

Edit `config/default.json` or create `config/user.json` for overrides.
Environment variables: `AURA_CFG_<SECTION>_<KEY>=value`

```bash
# Force mobile mode on any device:
AURA_CFG_KERNEL_TICK_INTERVAL_MS=100 python launch/launcher.py

# Force a specific mode:
AURA_MODE=universal python launch/launcher.py
```

**Mobile profile** is applied automatically when running on Android/Termux:
- Tick rate: 100 ms (10 Hz) instead of 16 ms
- Max memory: 256 MB instead of 512 MB
- Task queue: 256 instead of 1 000

---

## 📋 Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.10 | 3.12+ |
| RAM | 256 MB | 1 GB+ |
| Storage | 100 MB | 500 MB+ |
| Architecture | Any Python-supported | ARM64 / x86_64 |

**Optional for AI inference:**
- `pip install llama-cpp-python` — GGUF models on ARM64/x86_64
- `pip install onnxruntime` — ONNX models
- `pip install psutil` — enhanced metrics

---

## 🗂️ Project Structure

```
AURA-AIOSCPU/
├── launch/         # Boot sequence (launcher.py)
├── kernel/         # Core: loop, scheduler, event bus, modes, watchdog, config
├── aura/           # AI personality layer
├── hal/            # Hardware abstraction: vCPU, vMemory, vBus, VStorageDevice
├── services/       # Service manager + BuildService (self-build/repair)
├── shell/          # Interactive shell with all built-in commands
├── host_bridge/    # Host OS adapter (Android/Termux, Linux, macOS, Windows)
├── models/         # AI model manager (GGUF, Ollama, OpenAI, stub)
├── tools/          # Developer CLI tools
├── config/         # default.json + user.json (gitignored)
├── rootfs/         # Minimal root filesystem layout
├── tests/          # 516+ tests across 26 modules
├── build.py        # Build script → dist/
├── pyproject.toml  # Package metadata + `aura` CLI entry point
├── Dockerfile      # Minimal Docker image
├── deploy/         # Railway + Render cloud deploy configs
└── install_termux.sh  # One-command Android/Termux installer
```

---

## 🐳 Docker

```bash
docker build -t aura-aioscpu .
docker run -it -p 7331:7331 aura-aioscpu
# Open http://localhost:7331 for the web terminal
```

For persistent memory across restarts:

```bash
docker run -it -p 7331:7331 -v aura_data:/app/rootfs/aura aura-aioscpu
```

---

## ☁️ One-Line Cloud Deploy

**Railway:**
```bash
# Fork the repo, then click "Deploy on Railway" or:
railway login && railway up
```

**Render:**
```bash
# Import the repo in Render dashboard — render.yaml is auto-detected
```

Both platforms serve the AURA web terminal at a public HTTPS URL.

---

## 🤝 Contributing

1. Fork → branch → code → `python -m pytest tests/` (all tests must pass)
2. Run `python build.py --test` to build and verify
3. Pull request

---

<div align="center">

**AURA-AIOSCPU** — *Built to run everywhere. Designed to think. Made to last.*

</div>
