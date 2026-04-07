#!/usr/bin/env bash
# ======================================================================
# AURA-AIOSCPU — Android / Termux One-Command Installer
# ======================================================================
#
# Run this inside the Termux app on your Android phone:
#
#   bash install_termux.sh
#
# What it does
# ------------
#   1.  Updates Termux package index
#   2.  Installs Python 3 and Git (if not present)
#   3.  Installs the termux-api companion package (battery, Wi-Fi, etc.)
#   4.  Installs Python dependencies
#   5.  Runs the AURA compatibility checker
#   6.  Builds the AURA rootfs (dist/ folder)
#   7.  Offers to launch AURA immediately
#
# Minimum requirements
# --------------------
#   Android 7+  •  Termux (install from F-Droid, NOT Google Play)
#   Python 3.10+  •  100 MB free storage
#
# Optional extras for richer AI features
# ---------------------------------------
#   llama-cpp-python  — run GGUF models on-device (ARM64 optimised)
#   psutil            — enhanced CPU/memory/battery metrics
# ======================================================================

set -euo pipefail

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'  # no colour

ok()   { echo -e "  ${GREEN}✓${NC}  $*"; }
fail() { echo -e "  ${RED}✗${NC}  $*"; }
info() { echo -e "  ${YELLOW}→${NC}  $*"; }

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         AURA-AIOSCPU  ·  Android Installer           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# -----------------------------------------------------------------------
# Detect environment
# -----------------------------------------------------------------------
IS_TERMUX=0
if [[ -n "${TERMUX_VERSION:-}" ]] || [[ -d "/data/data/com.termux" ]]; then
    IS_TERMUX=1
    ok "Termux detected (version: ${TERMUX_VERSION:-unknown})"
else
    info "Not in Termux — proceeding with standard Python install"
fi

# -----------------------------------------------------------------------
# Install system packages (Termux)
# -----------------------------------------------------------------------
if [[ "$IS_TERMUX" == "1" ]]; then
    info "Updating Termux packages …"
    pkg update -y 2>/dev/null || true

    info "Installing Python …"
    pkg install -y python 2>/dev/null && ok "Python installed" || true

    info "Installing git …"
    pkg install -y git 2>/dev/null && ok "git installed" || true

    info "Installing termux-api (battery/wifi/notifications) …"
    pkg install -y termux-api 2>/dev/null && ok "termux-api installed" || true
fi

# -----------------------------------------------------------------------
# Verify Python
# -----------------------------------------------------------------------
echo ""
info "Checking Python version …"
PY_VER=$($PYTHON --version 2>&1)
ok "$PY_VER"

# -----------------------------------------------------------------------
# Python dependencies
# -----------------------------------------------------------------------
echo ""
info "Installing Python dependencies …"
$PYTHON -m pip install --upgrade pip --quiet 2>/dev/null || true
$PYTHON -m pip install -r "$AURA_DIR/requirements.txt" --quiet \
    && ok "Core dependencies installed" \
    || fail "Some dependencies failed — AURA may still work"

info "Installing optional psutil (enhanced metrics) …"
$PYTHON -m pip install psutil --quiet 2>/dev/null \
    && ok "psutil installed" \
    || info "psutil skipped (optional)"

# llama-cpp-python requires a C compiler; skip gracefully if unavailable
info "Attempting to install llama-cpp-python (ARM64 AI inference) …"
if $PYTHON -m pip install llama-cpp-python --quiet 2>/dev/null; then
    ok "llama-cpp-python installed — on-device AI is enabled!"
else
    info "llama-cpp-python skipped (no compiler / not needed for stub mode)"
fi

# -----------------------------------------------------------------------
# Compatibility check
# -----------------------------------------------------------------------
echo ""
info "Running compatibility check …"
$PYTHON "$AURA_DIR/tools/check_requirements.py" || true

# -----------------------------------------------------------------------
# Build rootfs
# -----------------------------------------------------------------------
echo ""
info "Building AURA-AIOSCPU rootfs …"
if $PYTHON "$AURA_DIR/build.py" --no-verify; then
    ok "Build complete → dist/"
else
    fail "Build failed — you can still run directly from source"
fi

# -----------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║          AURA-AIOSCPU is ready on your phone!        ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
echo "║  Start AURA:                                         ║"
echo "║    python launch/launcher.py                         ║"
echo "║                                                      ║"
echo "║  System info:                                        ║"
echo "║    python tools/aura_sys_info.py                     ║"
echo "║                                                      ║"
echo "║  Run tests:                                          ║"
echo "║    python -m pytest tests/                           ║"
echo "║                                                      ║"
echo "║  Build from source:                                  ║"
echo "║    python build.py --test                            ║"
echo "║                                                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

read -rp "  Launch AURA now? [Y/n]: " LAUNCH
LAUNCH="${LAUNCH:-Y}"
if [[ "${LAUNCH,,}" == "y" ]]; then
    echo ""
    AURA_MODE=universal $PYTHON "$AURA_DIR/launch/launcher.py"
fi
