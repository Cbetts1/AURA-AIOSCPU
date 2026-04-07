# AURA-AIOSCPU — Build & Tooling

> **Purpose:** Define how the OS is built, tested, packaged, deployed,
> updated, and what developer/debug/introspection/AI/hardware tools are
> required. Answers here drive the build pipeline, CI layout, and the
> developer-experience layer.

---

### Q1 — How should the OS be built?

*What is the build process from raw source to a runnable image?*

**Answer:**

> Build using a rootfs builder that copies source → SD card.

---

### Q2 — How should the OS be tested?

*What testing strategy ensures correctness at every layer?*

**Answer:**

> Test using a full unit + integration test suite.

---

### Q3 — How should the OS be packaged?

*What is the distributable artifact?*

**Answer:**

> Package as a portable rootfs image.

---

### Q4 — How should the OS be deployed?

*How does the image get onto a target device?*

**Answer:**

> Deploy by copying to SD card or host filesystem.

---

### Q5 — How should the OS update itself?

*What triggers an update and what is the atomic unit of change?*

**Answer:**

> Update by rebuilding rootfs.

---

### Q6 — What tools are needed for development?

*List the tools a developer needs to build, load, and profile the OS.*

**Answer:**

> Dev tools: module loader, test runner, profiler.

---

### Q7 — What tools are needed for debugging?

*List the tools needed to diagnose failures at runtime.*

**Answer:**

> Debug tools: logs, trace, service status.

---

### Q8 — What tools are needed for introspection?

*List the tools needed to inspect the live state of the system.*

**Answer:**

> Introspection tools: sys-info, net-info, fs-info.

---

### Q9 — What tools are needed for AI integration?

*List the tools AURA and developers need to manage models and AI context.*

**Answer:**

> AI tools: model manager, AURA tools, context tools.

---

### Q10 — What tools are needed for hardware projection?

*List the tools needed to query and drive the hardware projection layer.*

**Answer:**

> Hardware tools: capability scanner, projection controller.

---

## Build & Tooling Design Principles

| # | Principle | Source |
|---|-----------|--------|
| B-01 | Build = **rootfs builder** that assembles source into a deployable image | Q1 |
| B-02 | Every layer has **unit tests**; cross-layer interactions have **integration tests** | Q2 |
| B-03 | The distributable artifact is always a **portable rootfs image** | Q3 |
| B-04 | Deployment = **file copy** to SD card or host filesystem — no installer | Q4 |
| B-05 | Updates = **full rootfs rebuild** — no in-place patching of a live image | Q5 |
| B-06 | Dev toolchain ships with: **module loader · test runner · profiler** | Q6 |
| B-07 | Debug toolchain ships with: **log viewer · trace tool · service status** | Q7 |
| B-08 | Introspection toolchain ships with: **sys-info · net-info · fs-info** | Q8 |
| B-09 | AI toolchain ships with: **model manager · AURA tools · context tools** | Q9 |
| B-10 | Hardware toolchain ships with: **capability scanner · projection controller** | Q10 |

---

## Tool Directory Layout (derived)

```
/usr/bin/                    ← installed into rootfs
├── aura-module-loader       ← dev: load/unload kernel modules
├── aura-test-runner         ← dev: run unit + integration tests
├── aura-profiler            ← dev: CPU/memory/event profiling
├── aura-logs                ← debug: structured log viewer
├── aura-trace               ← debug: kernel + service call tracer
├── aura-service-status      ← debug: list and inspect running services
├── aura-sys-info            ← introspection: system topology snapshot
├── aura-net-info            ← introspection: network state snapshot
├── aura-fs-info             ← introspection: filesystem state snapshot
├── aura-model-manager       ← AI: install / update / activate models
├── aura-tools               ← AI: AURA CLI for direct assistant interaction
├── aura-context-tools       ← AI: inspect and manage AURA context state
├── aura-capability-scanner  ← hardware: detect available hardware surfaces
└── aura-projection-ctrl     ← hardware: drive the hardware projection layer
```

---

## What Happens Next

With build & tooling locked in, the project moves to:

1. **OS features interview** — process model, memory, devices, networking,
   identity, permissions, shell, and host-bridge (see `OS_FEATURES.md`).
2. **Rootfs builder specification** — exact build steps, directory assembly
   order, and image format.
3. **CI pipeline design** — how tests are run automatically on every commit.
