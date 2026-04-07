# AURA-AIOSCPU

> **AI-Personalised, Universal Operating System**

AURA-AIOSCPU is a new universal, AI-driven operating system built from
scratch. It is designed to run on phones, desktops, single-board computers,
and any device — booting from an SD card and projecting itself intelligently
into whatever hardware it finds.

## Project Status

| Phase | Status |
|-------|--------|
| 🔍 Vision & Requirements Discovery | **In progress** |
| 📐 Architecture Decision Records | Not started |
| 🛠️ Kernel prototype | Not started |
| 💾 Storage subsystem | Not started |
| 🤖 AI pipeline / AURA integration | Not started |
| 📱 Mobile port | Not started |
| 💿 SD-card boot image | Not started |
| 🔌 Hardware projection layer | Not started |

## Getting Started

Before any code is written, the design questions in
[OS_VISION_QUESTIONS.md](OS_VISION_QUESTIONS.md) must be answered. That
document covers:

1. OS identity and purpose
2. Functional requirements
3. Kernel architecture
4. Storage subsystem
5. AI pipeline architecture
6. AURA integration
7. Mobile (phone) deployment
8. Cross-platform and cross-device support
9. SD-card boot
10. Hardware projection layer

Fill in your answers in that document and open a PR — the answers will
drive every subsequent architecture and implementation decision.

## Repository Layout (planned)

```
AURA-AIOSCPU/
├── docs/                  # ADRs, diagrams, specs
├── kernel/                # Kernel source
├── drivers/               # HAL and hardware projection layer
├── storage/               # Filesystem and storage subsystem
├── ai-pipeline/           # Inference engine and model management
├── aura/                  # AURA shell and assistant daemon
├── boot/                  # Bootloader configs and SD-card image scripts
└── compat/                # Compatibility layers (Linux, Android, etc.)
```

## Contributing

This project is in the discovery phase. The best contribution right now is
to read [OS_VISION_QUESTIONS.md](OS_VISION_QUESTIONS.md), answer the
questions relevant to your area of expertise, and open a discussion or PR.
