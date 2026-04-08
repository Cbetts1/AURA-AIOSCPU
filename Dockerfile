# AURA-AIOSCPU — Docker Image
# ============================
# Builds a minimal, self-contained AURA image using Python 3.12 slim.
#
# Quick start:
#   docker build -t aura-aioscpu .
#   docker run -it -p 7331:7331 aura-aioscpu
#
# Web terminal (after `web start` inside AURA):
#   http://localhost:7331
#
# For persistent memory across restarts mount a volume:
#   docker run -it -p 7331:7331 -v aura_data:/app/rootfs/aura aura-aioscpu
#
# Optional: add a GGUF model file and mount it:
#   docker run -it -p 7331:7331 -v /path/to/models:/app/models aura-aioscpu

FROM python:3.12-slim

# Non-root user for safety
RUN useradd --create-home --shell /bin/bash aura
WORKDIR /app

# Copy project files
COPY --chown=aura:aura . .

# Install AURA and optional metrics dependency (pure-Python only; skip
# compilation-heavy llama-cpp-python — mount GGUF via Ollama instead)
RUN pip install --no-cache-dir -e ".[metrics]" || \
    pip install --no-cache-dir -r requirements.txt

USER aura

# Expose web terminal port
EXPOSE 7331

# Default: universal mode (safest, no root required)
ENV AURA_MODE=universal

CMD ["python", "launch/launcher.py"]
