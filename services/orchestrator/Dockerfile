# syntax=docker/dockerfile:1@sha256:2780b5c3bab67f1f76c781860de469442999ed1a0d7992a5efdf2cffc0e3d769
# =============================================================================
# Multi-Tenant MCP Orchestrator — Production Dockerfile
# Architecture: multi-stage build (uv builder, Python slim runtime)
# Runtime user: orchestrator (UID 10001)
# Security: runs as non-root, read-only rootfs ready, stripped privileges
# =============================================================================

# Global ARG: single source of truth for the base image (reused from Sandbox)
ARG BASE_IMAGE=python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727

# --- Stage 1: uv binary ---
FROM ghcr.io/astral-sh/uv:0.11.14@sha256:1025398289b62de8269e70c45b91ffa37c373f38118d7da036fb8bb8efc85d97 AS uv_bin

# --- Stage 2: Builder ---
FROM ${BASE_IMAGE} AS builder

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

COPY --from=uv_bin /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy manifests
COPY pyproject.toml uv.lock ./

# Pre-install dependencies to cache layers
RUN --mount=type=cache,target=/tmp/uv-cache \
    UV_CACHE_DIR=/tmp/uv-cache uv sync --frozen --no-install-project --no-dev

# Copy source code and build virtualenv
COPY README.md ./
COPY src/ ./src/
RUN --mount=type=cache,target=/tmp/uv-cache \
    UV_CACHE_DIR=/tmp/uv-cache uv sync --frozen --no-dev

# --- Stage 3: Runtime ---
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

# CIS Docker Benchmark 4.8: Remove setuid/setgid permissions in the image
# This prevents privilege escalation vulnerabilities from system binaries
RUN find / -xdev \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} + || true

# Create a non-root group and user with distinct ID
ARG UID=10001
ARG GID=10001
RUN groupadd -g "${GID}" orchestrator && \
    useradd -l -u "${UID}" -g "${GID}" -m -d /home/orchestrator orchestrator

WORKDIR /app

# Copy virtual environment and source code from builder stage
COPY --from=builder --chown=root:root /app/.venv /app/.venv
COPY --from=builder --chown=root:root /app/src /app/src

# Ensure paths are set to prioritize virtualenv binaries
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose FastAPI port
EXPOSE 8000

# Switch to the non-root user
USER orchestrator

# Healthcheck to verify the gateway is up and responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]

CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
