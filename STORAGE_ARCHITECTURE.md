# AURA-AIOSCPU — Storage Architecture

> **Purpose:** Define how the OS stores every class of data before any
> code is written. Answers here drive the partition layout, filesystem
> choice, boot sequence, config/log/model paths, and the update pipeline.

---

### Q1 — How should the OS store its files?

*Where does the OS live? Portable image, installed partition, cloud-synced
volume, or something else?*

**Answer:**

> The OS lives in a portable rootfs on SD card.

---

### Q2 — What is the rootfs layout?

*Describe the top-level directory structure inside the root filesystem.*

**Answer:**

> Rootfs layout follows Linux-style: `bin`, `etc`, `usr`, `var`, `tmp`, `home`.

---

### Q3 — What folders must exist inside rootfs?

*List every directory that must be present inside the rootfs at first boot.*

**Answer:**

> `/bin`, `/etc`, `/usr/lib`, `/usr/share`, `/var/log`, `/var/run`

---

### Q4 — What folders must exist outside rootfs?

*List every directory that lives on the SD card (or host filesystem) but
outside the rootfs mount point.*

**Answer:**

> `/services`, `/models`, `/launch`, `/config`, `/logs`

---

### Q5 — How should the OS boot from SD card?

*Describe the boot sequence from power-on to a running AURA shell.*

**Answer:**

> Boot from SD card using a launcher that mounts rootfs and starts the kernel.

---

### Q6 — How should configs be stored?

*Where do system and user configuration files live, and in what format?*

**Answer:**

> Configs live in `/etc` (inside rootfs) and `/config` (outside rootfs).

---

### Q7 — How should logs be stored?

*Where do runtime and persistent logs go?*

**Answer:**

> Logs live in `/var/log` (inside rootfs) and `/logs` (outside rootfs).

---

### Q8 — How should models be stored?

*Where do AI model files live, and how are they referenced by AURA?*

**Answer:**

> Models live in `/models` (outside rootfs).

---

### Q9 — How should services be stored?

*Where do OS services (daemons, background jobs) live on disk?*

**Answer:**

> Services live in `/services` (outside rootfs).

---

### Q10 — How should the OS update itself?

*Describe the update mechanism — what is rebuilt, how is it applied, and
how is rollback handled?*

**Answer:**

> Updates are applied by rebuilding rootfs from source.

---

## Storage Design Principles Derived from These Answers

| # | Principle | Source |
|---|-----------|--------|
| S-01 | The OS lives in a **portable rootfs** — no installation required | Q1 |
| S-02 | Rootfs follows **Linux filesystem hierarchy** (`bin`, `etc`, `usr`, `var`, `tmp`, `home`) | Q2 |
| S-03 | Core OS binaries and runtime state stay **inside rootfs** | Q3 |
| S-04 | Services, models, config, logs, and the launcher live **outside rootfs** — swappable without touching the OS image | Q4 |
| S-05 | Boot sequence: **launcher → mount rootfs → start kernel** | Q5 |
| S-06 | Config is **dual-homed**: `/etc` for OS defaults, `/config` for user/runtime overrides | Q6 |
| S-07 | Logs are **dual-homed**: `/var/log` for in-process logs, `/logs` for persistent cross-boot logs | Q7 |
| S-08 | AI models are **first-class storage citizens** at `/models`, decoupled from rootfs | Q8 |
| S-09 | Services are **self-contained units** at `/services`, loaded independently of rootfs | Q9 |
| S-10 | Updates = **full rootfs rebuild from source** — atomic, reproducible, rollback-friendly | Q10 |

---

## SD Card Partition Layout (derived)

```
SD Card
├── /launch          ← boot launcher (mounts rootfs, starts kernel)
├── /rootfs/         ← the OS root filesystem (mounted at /)
│   ├── bin/         ← core binaries
│   ├── etc/         ← OS default configs
│   ├── usr/
│   │   ├── lib/     ← shared libraries
│   │   └── share/   ← static data / assets
│   ├── var/
│   │   ├── log/     ← in-process logs
│   │   └── run/     ← runtime PIDs / sockets
│   ├── tmp/         ← ephemeral scratch space
│   └── home/        ← user home directories
├── /services/       ← OS and user service units
├── /models/         ← AURA AI model files
├── /config/         ← runtime / user config overrides
└── /logs/           ← persistent cross-boot logs
```

---

## What Happens Next

With storage locked in, the project moves to:

1. **Build & tooling interview** — how the rootfs is built, tested,
   packaged, and deployed (see `BUILD_AND_TOOLING.md`).
2. **Launcher specification** — exact boot sequence, rootfs mount flags,
   kernel startup arguments.
3. **Service format specification** — what a service unit file looks like
   inside `/services`.
