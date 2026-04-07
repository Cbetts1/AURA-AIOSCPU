# AURA-AIOSCPU

> **A real, portable, AI-driven operating system.**

AURA-AIOSCPU is built from scratch to run on any device — on your phone,
inside your phone, on top of any OS, or projected directly into hardware.
AURA is not an app. AURA is the kernel's intelligence.

## Project Status

| Phase | Status |
|-------|--------|
| 🔍 Vision & Requirements | ✅ Complete |
| 📐 Architecture Design | ✅ Complete |
| 🗂️ Skeleton repo | ✅ Complete |
| 🛠️ Kernel implementation | 🔜 Next |
| 💾 Storage subsystem | 🔜 Pending |
| 🤖 AURA integration | 🔜 Pending |
| 📱 Mobile / host-bridge | 🔜 Pending |
| 💿 SD-card boot image | 🔜 Pending |
| 🔌 Hardware projection | 🔜 Pending |

## Architecture at a Glance

```
SD Card / Host Filesystem
├── /launch/launcher.py       ← boot entry point
├── /services/                ← service unit files
├── /models/                  ← AURA AI model files
├── /config/                  ← runtime config overrides
├── /logs/                    ← persistent cross-boot logs
└── /rootfs/                  ← the OS root filesystem
    ├── bin/   etc/   home/
    ├── tmp/   usr/   var/

Source Layout
├── kernel/                   ← kernel core
│   ├── __init__.py           ← Kernel class (mode + subsystem init)
│   ├── loop.py               ← heartbeat: events → schedule → AURA pulse
│   ├── scheduler.py          ← tasks, services, background jobs
│   ├── event_bus.py          ← sole comms channel: kernel↔services↔shell↔AURA
│   └── modes/
│       ├── universal.py      ← runs on any OS via host-bridge (no root)
│       ├── internal.py       ← runs inside OS with user-granted permissions
│       └── hardware.py       ← projects runtime into hardware (explicit consent)
├── hal/                      ← Hardware Abstraction Layer
│   └── __init__.py           ← vCPU, vMemory, vDevices, vBus
├── aura/                     ← kernel personality layer
│   └── __init__.py           ← observes all state; advises; responds; acts
├── shell/                    ← text shell, AURA-integrated
│   └── __init__.py
├── host_bridge/              ← unified API for Android, Linux, etc.
│   └── __init__.py
├── services/                 ← service manager
│   └── __init__.py
├── launch/                   ← boot launcher (outside rootfs)
│   └── launcher.py
└── tests/                    ← unit + integration test suite
    ├── test_kernel_loop.py
    ├── test_scheduler.py
    ├── test_event_bus.py
    ├── test_hal.py
    ├── test_aura.py
    ├── test_shell.py
    ├── test_bridge.py
    └── test_services.py
```

## Design Documents

| Document | Contents |
|----------|----------|
| [FIRST_INTERVIEW.md](FIRST_INTERVIEW.md) | 10 founding questions + answers + design principles |
| [KERNEL_ARCHITECTURE.md](KERNEL_ARCHITECTURE.md) | Kernel modes, loop, scheduler, event bus, HAL, AURA |
| [STORAGE_ARCHITECTURE.md](STORAGE_ARCHITECTURE.md) | rootfs layout, partition map, boot sequence |
| [BUILD_AND_TOOLING.md](BUILD_AND_TOOLING.md) | Build, test, package, deploy, update pipeline |
| [OS_FEATURES.md](OS_FEATURES.md) | Process model, memory, devices, identity, permissions, shell, host-bridge |
| [OS_VISION_QUESTIONS.md](OS_VISION_QUESTIONS.md) | Full 65-question discovery reference |

## Quick Start (once implemented)

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run the test suite
pytest tests/

# Build the rootfs image
python build.py

# Deploy to SD card
cp rootfs.img /dev/sdX

# Or run in Universal Mode on top of your current OS
python launch/launcher.py
```

## Core Principles

| # | Principle |
|---|-----------|
| 1 | AURA is part of the **kernel**, not an app |
| 2 | The OS is **universally portable** — phone, any device, inside any OS |
| 3 | Three kernel surfaces: **Universal · Internal · Hardware Projection** |
| 4 | All hardware is **virtual by default** (vCPU, vMemory, vDevices, vBus) |
| 5 | Host-bridge = **one unified API** for Android, Linux, macOS, Windows |
| 6 | All elevated actions require **explicit user consent** |
| 7 | Every module is **modular, safe, and fully testable** |
| 8 | Updates = **full rootfs rebuild** — atomic and reproducible |

