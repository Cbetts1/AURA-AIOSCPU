# AURA-AIOSCPU — OS Features Interview

> **Purpose:** Define the modern OS features the system must include before
> any code is written. Answers here drive the process model, memory system,
> virtual device layer, identity model, permission system, shell design, and
> the host-bridge API.

---

### Q1 — What modern OS features must be included?

*List every core OS feature that must be present from the first boot.*

**Answer:**

> Must include process management, memory model, devices, networking, logs.

---

### Q2 — How should networking work?

*Describe the networking model — how does the OS get onto a network?*

**Answer:**

> Networking via host-bridge adapters.

---

### Q3 — How should virtual memory work?

*Describe the virtual memory model — complexity, constraints, goals.*

**Answer:**

> Virtual memory = simple, expandable.

---

### Q4 — How should virtual devices work?

*Which virtual device classes must exist and what do they abstract?*

**Answer:**

> Virtual devices = network, display, storage.

---

### Q5 — How should identity work?

*Describe the identity model — who is the system, who is the user?*

**Answer:**

> Identity = system identity + user identity.

---

### Q6 — How should permissions work?

*Describe the permission model — who grants what, when, and how?*

**Answer:**

> Permissions = explicit user consent for elevated actions.

---

### Q7 — How should services communicate?

*What is the inter-service communication mechanism?*

**Answer:**

> Services communicate via event bus.

---

### Q8 — How should AURA access system state?

*What system information can AURA see, and through what interface?*

**Answer:**

> AURA sees system topology, state, logs, configs.

---

### Q9 — How should the shell work?

*Describe the shell model — input style, AURA integration, output.*

**Answer:**

> Shell = text-based, AURA-integrated.

---

### Q10 — How should the host-bridge work?

*What is the host-bridge API contract and which host OSes must it support?*

**Answer:**

> Host-bridge = unified API for Android, Linux, etc.

---

## OS Features Design Principles

| # | Principle | Source |
|---|-----------|--------|
| F-01 | Core feature set: **process management · memory model · devices · networking · logs** | Q1 |
| F-02 | All networking flows through **host-bridge adapters** — no raw socket access by default | Q2 |
| F-03 | Virtual memory is **simple and expandable** — start flat, add paging/segmentation as needed | Q3 |
| F-04 | Three mandatory virtual device classes: **network · display · storage** | Q4 |
| F-05 | Two identity scopes: **system identity** (the OS itself) and **user identity** (the person) | Q5 |
| F-06 | All elevated actions require **explicit user consent** — no silent privilege escalation | Q6 |
| F-07 | Services may only talk to each other via the **event bus** — no direct coupling | Q7 |
| F-08 | AURA has read access to: **topology · kernel state · logs · configs** at all times | Q8 |
| F-09 | The shell is **text-first** with AURA as a built-in first-class responder | Q9 |
| F-10 | The host-bridge exposes a **single unified API** regardless of underlying host OS | Q10 |

---

## What Happens Next

With OS features locked in, the project moves to:

1. **Skeleton repo generation** — directory layout, stub source files, and
   stub test files matching every design decision captured so far.
2. **Process model specification** — how tasks, services, and jobs map to
   the scheduler and event bus.
3. **Virtual device specification** — the interface contract each virtual
   device (network, display, storage) must implement.
