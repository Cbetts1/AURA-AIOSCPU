# AURA-AIOSCPU — Installation Guide

## Quick Install (Android / Termux)

```bash
# 1. Install Termux from F-Droid (NOT Google Play)
# 2. Open Termux and run:
pkg install git python
git clone https://github.com/Cbetts1/AURA-AIOSCPU
cd AURA-AIOSCPU
bash install_termux.sh
```

The installer handles everything automatically:
- Updates Termux packages
- Installs Python 3 and Git
- Installs the `termux-api` companion app
- Installs Python dependencies
- Runs the compatibility checker
- Builds the AURA rootfs
- Optionally launches AURA immediately

---

## System Requirements

| Requirement | Minimum |
|-------------|---------|
| Android | 7.0+ |
| Termux | Latest (F-Droid) |
| Python | 3.10+ |
| Storage | 100 MB free |
| RAM | 1 GB (512 MB minimum) |

### Optional (enhanced features)

```bash
# Enhanced CPU/memory/battery metrics
pip install psutil

# On-device AI inference (ARM64 optimised)
pip install llama-cpp-python
```

---

## Desktop / Server Install

```bash
git clone https://github.com/Cbetts1/AURA-AIOSCPU
cd AURA-AIOSCPU
pip install -e .
python launch/launcher.py
```

Or with all extras:

```bash
pip install -e ".[all]"
```

---

## Docker Install

```bash
docker build -t aura-aioscpu .
docker run -it -p 7331:7331 -p 7332:7332 aura-aioscpu
```

Web terminal: `http://localhost:7331`
Command channel: `http://localhost:7332`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AURA_MODE` | `universal` | Kernel surface mode (`universal`/`internal`/`hardware`) |
| `CC_URL` | _(none)_ | Command Center base URL (e.g. `http://192.168.1.10:8080`) |
| `CC_API_KEY` | _(none)_ | Shared secret for Command Center authentication |
| `CC_HEARTBEAT_S` | `30` | Heartbeat interval in seconds |
| `CC_CHANNEL_HOST` | `127.0.0.1` | Command channel bind address |
| `CC_CHANNEL_PORT` | `7332` | Command channel bind port |

---

## Verify Installation

```bash
python tools/validate_system.py
python tools/check_requirements.py
python tools/aura_sys_info.py
```

---

## Run Tests

```bash
python -m pytest tests/
python -m pytest tests/ -v --tb=short
python -m pytest tests/conformance/   # conformance suite
```

---

## Build from Source

```bash
python build.py              # full build
python build.py --test       # run tests first
python build.py --clean      # wipe dist/ then build
python build.py --verify     # verify existing build
```

---

## Uninstall

```bash
# Remove the AURA directory
rm -rf ~/AURA-AIOSCPU

# Remove the pip package (if installed with -e)
pip uninstall aura-aioscpu
```

---

## Troubleshooting

### "Python not found"
```bash
pkg install python   # Termux
```

### "Module not found"
```bash
pip install -e .
# or
pip install -r requirements.txt
```

### Port already in use
Change the port via environment variable:
```bash
CC_CHANNEL_PORT=7340 python launch/launcher.py
```

### ARM64 llama-cpp-python install fails
This requires a C compiler. Install clang first:
```bash
pkg install clang
pip install llama-cpp-python
```

---

## Paths (Termux)

| Path | Description |
|------|-------------|
| `~/AURA-AIOSCPU/` | Repository root |
| `~/AURA-AIOSCPU/logs/aura.log` | Main log file |
| `~/AURA-AIOSCPU/config/` | Configuration directory |
| `~/AURA-AIOSCPU/config/node_identity.json` | Virtual node identity |
| `~/AURA-AIOSCPU/config/peers.json` | Known peer nodes |
| `~/AURA-AIOSCPU/dist/` | Built rootfs image |
| `~/AURA-AIOSCPU/rootfs/` | Virtual filesystem |
