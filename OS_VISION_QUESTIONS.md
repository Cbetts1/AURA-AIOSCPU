# AURA-AIOSCPU — OS Vision & Purpose: Discovery Questions

> **Status:** Pre-design discovery phase — no code generated yet.
>
> Before any architecture or code is produced, the following questions must be
> answered. They are organised into the ten areas identified in the project
> brief. Fill in each section and commit the answers; the answers will drive
> every subsequent design decision.

---

## 1 — OS Identity & Purpose

1. What is the single-sentence mission of AURA-AIOSCPU? (e.g. "A universal,
   self-learning operating system that adapts entirely to its user.")
2. Who are the primary users? (general consumers, developers, enterprise,
   IoT operators, all of the above?)
3. What problem does this OS solve that existing operating systems do not?
4. What is the top-level branding philosophy — how should a user *feel* while
   using it? (invisible assistant, proactive partner, voice-first shell, etc.)
5. Is AURA-AIOSCPU intended to *replace* other OSes on a device, or to run
   *alongside* them (dual-boot / containerised / virtualised)?
6. What is the target maturity horizon — MVP in weeks, production-ready in
   months, or a multi-year platform?

---

## 2 — Functional Requirements

7. What is the **minimal viable feature set** for the first boot?
   (e.g. shell, file manager, AI chat, network, app launcher?)
8. Which categories of applications must the OS be able to run on day one?
   (native compiled apps, web apps, Android APKs, Linux binaries, all?)
9. What accessibility requirements must be met from the start?
   (screen reader, voice control, high-contrast, Braille display?)
10. What security and privacy guarantees must the OS provide?
    (local-only AI inference, end-to-end encrypted storage, zero telemetry?)
11. Are there regulatory or certification requirements?
    (FIPS 140-2, GDPR, DO-178C, HIPAA, etc.)
12. What networking protocols and connectivity must be supported at launch?
    (Wi-Fi, 5G/LTE, Bluetooth, NFC, USB-C, Ethernet?)

---

## 3 — Kernel Architecture

13. Should the kernel be **monolithic**, **microkernel**, or **hybrid**?
    (e.g. Linux monolithic, seL4 microkernel, macOS XNU hybrid)
14. Will the kernel be written from scratch, forked from Linux/BSD, or will it
    wrap an existing kernel (e.g. run atop the Linux kernel via a HAL)?
15. What CPU instruction-set architectures must the kernel target?
    (x86-64, ARM64/AArch64, RISC-V, MIPS, all of the above?)
16. What real-time or latency guarantees are needed?
    (best-effort, soft real-time for multimedia, hard real-time for robotics?)
17. How should the kernel handle **AI workload scheduling**?
    (dedicated AI scheduler, priority boost for inference threads,
    heterogeneous CPU+GPU+NPU task dispatch?)
18. What memory model is required?
    (virtual memory with paging, unified memory for mobile SoCs, capability-
    based memory safety?)
19. How will drivers be managed?
    (in-kernel modules, user-space drivers via IPC, eBPF-based drivers?)

---

## 4 — Storage Subsystem

20. What is the primary **filesystem**?
    (ext4, Btrfs, ZFS, F2FS for flash, a custom AI-indexed filesystem?)
21. Should storage be **content-addressed** (like Git objects or IPFS) so the
    AI can reference any version of any file by hash?
22. How will the OS handle **encrypted storage**?
    (full-disk encryption at rest, per-file encryption, hardware-backed keys
    via TEE/Secure Enclave?)
23. What is the strategy for **flash wear levelling** on SD-card or eMMC
    storage?
24. Will there be an **AI-aware storage tier** — e.g. hot/warm/cold storage
    managed automatically by the AI based on usage patterns?
25. How is **cloud or network storage** integrated?
    (transparent sync, FUSE overlay, explicit user action only?)
26. What is the **backup and snapshot** strategy?
    (incremental snapshots, rollback, disaster recovery?)

---

## 5 — AI Pipeline Architecture

27. Where does AI inference run — **on-device only**, cloud-offload, or a
    hybrid with fallback?
28. What AI model(s) will power AURA at launch?
    (a specific open-weight LLM, a custom fine-tuned model, multiple
    specialised models for different tasks?)
29. How is the AI pipeline structured?
    (single monolithic model, multi-agent pipeline, mixture-of-experts,
    retrieval-augmented generation with a local vector DB?)
30. What hardware accelerators must the pipeline support?
    (CPU-only, Mali/Adreno GPU via OpenCL/Vulkan, Apple Neural Engine,
    Qualcomm Hexagon DSP, NVIDIA CUDA, custom NPU?)
31. How is **model updating** handled without bricking the device?
    (OTA delta updates, A/B partitions for model slots, user-gated rollouts?)
32. What latency budget is acceptable for an AI response?
    (< 100 ms for interactive completions, < 500 ms for complex reasoning?)
33. How will the pipeline handle **multi-modal** inputs?
    (text, voice, image, sensor data, all together in one context?)

---

## 6 — AURA Integration

34. What exactly is **AURA**?
    (the AI assistant persona, the inference engine, the OS shell, or all
    three combined into one layer?)
35. How does AURA interact with the kernel?
    (privileged system calls, a user-space daemon, a ring-0 co-processor
    trusted execution environment?)
36. What **permissions model** controls what AURA can do autonomously vs. what
    requires explicit user approval?
37. How does AURA learn from the user over time?
    (on-device fine-tuning, preference vectors stored locally, federated
    learning, none?)
38. What is the **personality and tone** of AURA?
    (neutral assistant, friendly companion, expert advisor — configurable?)
39. How does AURA handle **multi-user** scenarios on the same device?
    (separate AURA instances per user profile, shared model with per-user
    context, no multi-user support?)
40. What happens when AURA makes a mistake or causes data loss — what is the
    recovery and accountability model?

---

## 7 — Mobile (Phone) Deployment

41. Which **mobile SoC families** are the initial targets?
    (Qualcomm Snapdragon, MediaTek Dimensity, Samsung Exynos, Apple A-series,
    Google Tensor?)
42. Will AURA-AIOSCPU replace Android/iOS entirely on the phone, or run in a
    container/VM on top of Android?
43. How will **telephony** be handled?
    (use the Android RIL/vendor modem stack, implement a custom RIL, or
    require a separate modem coprocessor with a standard AT-command interface?)
44. How will the OS manage the **battery and thermal** constraints unique to
    mobile? (AI workloads can be very power-hungry.)
45. What **mobile-specific hardware** must be supported at launch?
    (camera ISP, fingerprint reader, face unlock, GPS, accelerometer,
    gyroscope, NFC?)
46. What is the **display pipeline**? (SurfaceFlinger-equivalent, Wayland
    compositor, direct framebuffer, custom GPU compositor?)
47. How are **push notifications and background services** managed on mobile
    where battery life demands aggressive process suspension?

---

## 8 — Cross-Platform & Cross-Device Support

48. What is the **portability strategy**?
    (a Hardware Abstraction Layer, POSIX compatibility shim, platform-specific
    backends behind a unified API?)
49. Which **device classes** must the OS support beyond phones?
    (laptops/desktops, tablets, Raspberry Pi / SBCs, smart TVs, cars,
    industrial controllers, wearables?)
50. Will there be a **compatibility layer** for existing OS ecosystems?
    (Wine for Windows binaries, Anbox/Waydroid for Android apps, Rosetta-
    style translator, none?)
51. How is the **UI/UX adapted** across vastly different screen sizes and
    input modalities (touch, keyboard+mouse, voice, pen, controller)?
52. What is the **update and fleet management** story for many deployed
    devices? (OTA, MDM, AURA-managed self-update?)

---

## 9 — SD-Card Boot

53. What is the **SD-card boot workflow** from power-on to AURA shell?
    (bootloader → second-stage loader → kernel → init → AURA?)
54. Which **bootloaders** should be supported?
    (U-Boot, GRUB, Raspberry Pi firmware, custom EFI stub?)
55. Should the SD-card image be a **full system image** (kernel + rootfs +
    AI models), or a **netboot stub** that downloads the rest on first run?
56. What is the **partition layout** of the SD card?
    (boot partition FAT32, root ext4/Btrfs, data partition, swap, model
    partition, recovery partition?)
57. How large is the **minimum SD card** size and what capacity is
    recommended for full AI model loading?
58. Should the OS be able to **write back to the SD card** during runtime
    (e.g. save user data), or run entirely in RAM from a read-only image?
59. How will the SD-card image be **distributed and verified**?
    (signed image, GPG-verified download, reproducible builds?)

---

## 10 — Hardware Projection Layer

60. What does "**projects itself into hardware**" mean concretely?
    (dynamic driver loading, FPGA bitstream reconfiguration, hardware
    description generation, something else?)
61. Should the OS be able to **auto-detect and configure unknown hardware**
    purely from AI analysis of hardware registers and datasheets?
62. Is there a requirement to support **FPGA or reconfigurable logic**?
    (generate HDL/bitstreams on the fly, interface with off-the-shelf FPGA
    boards?)
63. How should the OS handle **hardware that has no driver**?
    (graceful degradation, AI-generated stub driver, community driver
    download, error and skip?)
64. What is the **driver security model**?
    (all drivers sandboxed in user space, kernel-mode with code signing,
    capability-based access to hardware peripherals?)
65. Should the **hardware projection layer** expose a high-level API to
    AURA so that the AI can query and reconfigure hardware topology at
    runtime? If so, what safety guards are required?

---

## Next Steps

Once you have answered the questions above, the design process will move to:

1. **Architecture Decision Records (ADRs)** — one ADR per major component
   decision.
2. **Component diagrams** — kernel, storage, AI pipeline, AURA daemon,
   HAL / hardware projection layer.
3. **Prototype spike** — boot a minimal kernel image on the target hardware
   and confirm the SD-card boot chain works.
4. **Iterative feature development** — implement each area in order of
   dependency (kernel → storage → HAL → AI pipeline → AURA shell → apps).

> **Rule:** No production code is written until the answers above are
> captured and reviewed. This document is the single source of truth for the
> OS vision.
