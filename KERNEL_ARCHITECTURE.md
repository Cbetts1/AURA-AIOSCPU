# AURA-AIOSCPU — Kernel Architecture Interview

> **Purpose:** Define the kernel's internal structure before any code is
> written. Answers here feed directly into the kernel module layout,
> scheduler design, AURA integration points, and the Hardware Abstraction
> Layer (HAL).
>
> Fill in each **Answer** block and open a PR.

---

### Q1 — Describe the three kernel modes.

*The kernel has three operational modes. Give each one a name, a one-sentence
description, and its primary responsibility.*

**Answer:**

> The kernel has three surfaces: Universal, Internal, Hardware Projection.

---

### Q2 — How should Universal Mode behave?

*Universal Mode is presumably the most portable, host-agnostic mode.
Describe what the kernel does in this mode: which subsystems are active,
what resources it manages, and how it presents itself to user-space or
to AURA.*

**Answer:**

> Universal Mode runs on top of any OS using a host-bridge.

---

### Q3 — How should Internal Mode behave?

*Internal Mode likely refers to the kernel operating inside another OS
(the "mirrored" / host-bridge scenario). Describe its behaviour: how it
co-exists with the host, which host resources it borrows, and what it
owns exclusively.*

**Answer:**

> Internal Mode runs inside an OS with elevated permissions.

---

### Q4 — How should Hardware Mode behave?

*Hardware Mode is presumably bare-metal or near-bare-metal operation on
physical or virtual hardware. Describe how the kernel takes full control,
what it initialises first, and how it differs from the other two modes.*

**Answer:**

> Hardware Mode projects a runtime into external hardware when allowed.

---

### Q5 — What permissions does each mode require?

*List the permission level or privilege ring each mode needs, and any
capabilities that must be granted or denied.*

| Mode | Privilege level | Key capabilities granted | Key capabilities denied |
|------|-----------------|--------------------------|-------------------------|
| Universal | No root required | Host-bridge IPC, user-space scheduling | Direct hardware access, root syscalls |
| Internal | User-granted permissions | Elevated host permissions, shared memory | Kernel ring-0, hardware DMA |
| Hardware | Explicit user consent | Full HAL access, hardware projection | Anything not explicitly consented |

**Answer:**

> Universal = no root, Internal = user-granted permissions, Hardware = explicit consent.

---

### Q6 — How does AURA interact with the kernel?

*AURA is integrated into the kernel (Q8 from the founding interview).
Describe the exact interface: does AURA run as a kernel thread, a
privileged daemon, a set of kernel hooks/callbacks, a co-routine in the
kernel loop, or something else?*

**Answer:**

> AURA is part of the kernel personality layer and sees all system state.

---

### Q7 — What is the kernel loop responsible for?

*The kernel loop is the heartbeat of the system. List every responsibility
it must handle on each tick or iteration: scheduling, event dispatch,
watchdog, AURA pulse, hardware polling, etc.*

**Answer:**

> Kernel loop = heartbeat, events, scheduling, system state.

---

### Q8 — What is the scheduler responsible for?

*Describe the scheduler's role: what it schedules (threads, coroutines,
AI tasks, I/O callbacks?), what algorithm it uses (round-robin, priority
queue, AI-directed, work-stealing?), and how AURA can influence it.*

**Answer:**

> Scheduler = tasks, services, background jobs.

---

### Q9 — What is the event bus responsible for?

*The event bus carries messages between kernel components and AURA. Define
its responsibilities: what events flow through it, who can publish, who
can subscribe, how priority or ordering is enforced, and how events cross
the kernel/AURA boundary.*

**Answer:**

> Event bus = communication between kernel, services, shell, AURA.

---

### Q10 — What is the HAL responsible for?

*The Hardware Abstraction Layer sits between the kernel and the virtual or
physical devices (vCPU, vMemory, vDevices, vBus — from Q9 of the founding
interview). Define every class of hardware the HAL must abstract and the
contract it must expose upward to the kernel.*

**Answer:**

> HAL = virtual devices, hardware abstraction, future hardware projection.

---

## Kernel Design Principles Derived from These Answers

| # | Principle | Source |
|---|-----------|--------|
| K-01 | Three kernel surfaces: **Universal**, **Internal**, **Hardware Projection** | Q1 |
| K-02 | Universal Mode uses a **host-bridge** — zero root required | Q2, Q5 |
| K-03 | Internal Mode borrows elevated **user-granted** host permissions | Q3, Q5 |
| K-04 | Hardware Mode requires **explicit user consent** before projecting into hardware | Q4, Q5 |
| K-05 | AURA lives in the **kernel personality layer** with full system-state visibility | Q6 |
| K-06 | The kernel loop owns: **heartbeat · events · scheduling · system state** | Q7 |
| K-07 | The scheduler manages: **tasks · services · background jobs** | Q8 |
| K-08 | The event bus is the sole communication channel for: **kernel · services · shell · AURA** | Q9 |
| K-09 | The HAL abstracts: **virtual devices · hardware interfaces · hardware projection** | Q10 |
