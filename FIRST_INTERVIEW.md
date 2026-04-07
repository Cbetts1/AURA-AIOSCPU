# AURA-AIOSCPU — First Interview: 10 Founding Questions

> This document captures the answers to the ten foundational questions asked
> before any architecture or code is produced.  Fill in each **Answer** block
> and open a PR — these answers become the binding source of truth for every
> design decision that follows.

---

### Q1 — What is the core purpose of the OS?

*What problem is this OS fundamentally solving? What should it achieve for
its user that no current OS does?*

**Answer:**

> *(your answer here)*

---

### Q2 — What makes this OS different from a normal OS?

*How does AURA-AIOSCPU stand apart from Windows, macOS, Linux, Android, or
iOS? What is the defining characteristic that makes it a new category?*

**Answer:**

> *(your answer here)*

---

### Q3 — What role does AI play in the OS?

*Is AI a feature layered on top, or is it woven into the core of how the OS
works? Does AI manage scheduling, storage, security, the UI — all of it?*

**Answer:**

> *(your answer here)*

---

### Q4 — What is the long-term vision for the system?

*Where do you see AURA-AIOSCPU in 5–10 years? Is the goal mass consumer
adoption, a developer platform, a research vehicle, or something else
entirely?*

**Answer:**

> *(your answer here)*

---

### Q5 — What devices must it run on?

*List every device class that must be supported — phone, laptop, desktop,
Raspberry Pi, smart TV, car, wearable, industrial hardware, etc. Which is
the primary target for the first release?*

**Answer:**

> *(your answer here)*

---

### Q6 — What constraints or rules must it follow?

*Are there hard rules the OS must never break? Examples: always-on
encryption, no cloud telemetry, must run offline, must fit in 4 GB RAM,
must be open-source, must not store biometric data on-device, etc.*

**Answer:**

> *(your answer here)*

---

### Q7 — What is the personality or identity of the OS?

*If the OS had a character, how would you describe it? Invisible and silent?
Proactively helpful? Voice-first? Warm and personal? Powerful and
professional? This shapes everything from UI tone to how AURA speaks.*

**Answer:**

> *(your answer here)*

---

### Q8 — What is the role of AURA inside the OS?

*Is AURA the name of the assistant, the AI engine, the OS shell, or the
entire OS itself? Does AURA have authority to act autonomously, or does it
always ask permission? Where does AURA live in the system stack?*

**Answer:**

> *(your answer here)*

---

### Q9 — What does "digital hardware" mean in this context?

*The project brief mentions the OS "projects itself into hardware." What does
"digital hardware" refer to — virtual/emulated hardware, FPGA reconfigurable
logic, AI-generated driver code, a software abstraction layer, or something
else?*

**Answer:**

> *(your answer here)*

---

### Q10 — What does "mirrored OS" mean for your design?

*What is meant by a "mirrored OS"? Is this about running an identical copy
on multiple devices in sync, mirroring a host OS (e.g. Android) underneath,
a redundant failover copy, or a reflection of the user's digital identity
across devices?*

**Answer:**

> *(your answer here)*

---

## What Happens Next

Once all ten answers are committed here, the project moves to:

1. **Architecture Decision Records** — one ADR per major component
   (kernel, storage, AI pipeline, AURA daemon, HAL).
2. **Component & data-flow diagrams** — visual map of how each layer
   connects.
3. **Dependency decisions** — which existing open-source foundations
   (Linux kernel, LLVM, ONNX Runtime, etc.) to build on vs. build from
   scratch.
4. **First prototype spike** — SD-card boot to a minimal shell on the
   primary target hardware.
