# syntax=docker/dockerfile:1@sha256:2780b5c3bab67f1f76c781860de469442999ed1a0d7992a5efdf2cffc0e3d769
# =============================================================================
# Agent Workspace MCP — Production Dockerfile
# Architecture: three-stage build (rtk binary, uv binary, Python slim runtime)
# Transport:    stdio (JSON-RPC over stdin/stdout)
# Runtime user: mcpuser (UID 1000 by default)
# =============================================================================

# Global ARG: single source of truth for the base image (used by Renovate + LABEL)
ARG BASE_IMAGE=python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727

# --- Stage 1: rtk binary ---
FROM alpine:3.23@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11 AS rtk_bin
RUN apk add --no-cache curl tar
# renovate: datasource=github-releases depName=rtk-ai/rtk
ARG RTK_VERSION="0.38.0"
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        RTK_URL="rtk-x86_64-unknown-linux-musl.tar.gz"; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        RTK_URL="rtk-aarch64-unknown-linux-gnu.tar.gz"; \
    else \
        echo "Unsupported architecture: $TARGETARCH" && exit 1; \
    fi && \
    curl -fsSL "https://github.com/rtk-ai/rtk/releases/download/v${RTK_VERSION}/${RTK_URL}" | tar -xz -C /usr/local/bin rtk

# --- Stage 2: uv binary ---
FROM ghcr.io/astral-sh/uv:0.11.13@sha256:841c8e6fe30a8b07b4478d12d0c608cba6de66102d29d65d1cc423af86051563 AS uv_bin

# --- Stage 3: Runtime ---
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

COPY --from=uv_bin /uv /uvx /bin/

# Install minimal system utilities required by the agentic workspace
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    patch \
    tree \
    fd-find \
    ripgrep \
    zip \
    unzip \
  && ln -s /usr/bin/fdfind /usr/local/bin/fd

# Configure git security defaults for the workspace
RUN git config --system safe.directory /workspace \
 && git config --system credential.helper '' \
 && git config --system core.autocrlf input

COPY --link --from=rtk_bin /usr/local/bin/rtk /usr/local/bin/rtk

# CIS Docker Benchmark 4.8: Remove setuid/setgid permissions in the image
# This prevents privilege escalation vulnerabilities from system binaries like `su` or `passwd`
RUN find / -xdev \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} + || true

# Create a non-root user with configurable UID/GID for host-mount compatibility
ARG UID=1000
ARG GID=1000
RUN groupadd -g "${GID}" mcpuser && useradd -l -u "${UID}" -g "${GID}" -m mcpuser

# --- Application install ---
# /app stays root-owned (immutable at runtime); /workspace is owned by mcpuser
RUN mkdir -p /app /workspace && chown mcpuser:mcpuser /workspace

WORKDIR /app

# UV_COMPILE_BYTECODE=1 speeds up startup
# UV_LINK_MODE=copy ensures compatibility across Docker layers
# PYTHONDONTWRITEBYTECODE=1 prevents stray .pyc files outside of uv's compilation
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy dependency manifests first to maximize layer cache hits
COPY pyproject.toml uv.lock ./

# Install dependencies (without the project itself)
RUN --mount=type=cache,target=/tmp/uv-cache \
    UV_CACHE_DIR=/tmp/uv-cache uv sync --frozen --no-install-project --no-dev

# Copy application source
COPY README.md ./
COPY src/ ./src/

# Install the project server itself into the venv
RUN --mount=type=cache,target=/tmp/uv-cache \
    UV_CACHE_DIR=/tmp/uv-cache uv sync --frozen --no-dev

# Make /app world-readable while keeping root ownership (immutable for mcpuser)
RUN chmod -R a+rX /app

# --- Workspace setup ---
USER mcpuser
WORKDIR /workspace

# Isolate agent-installed packages from the server venv into a workspace-local venv
ENV UV_PROJECT_ENVIRONMENT=/workspace/.venv_container \
    PATH="/app/.venv/bin:$PATH"

STOPSIGNAL SIGTERM

# Recommended runtime flags:
#   --tmpfs /tmp:rw,noexec,nosuid,size=256m
#   --read-only (if /workspace is bind-mounted)

# OCI & MCP metadata
ARG VERSION="0.0.0-local"
ARG REVISION="local"
ARG CREATED="unknown"
# Persist version for runtime retrieval without patching pyproject.toml
ENV MCP_SERVER_VERSION=${VERSION}
# Re-declare the global ARG within this stage to make it available for LABEL
ARG BASE_IMAGE

LABEL org.opencontainers.image.title="Agent Workspace MCP" \
      org.opencontainers.image.description="Sandboxed agentic workspace MCP server for LLMs" \
      org.opencontainers.image.url="https://github.com/HrRodan/agent-workspace-mcp" \
      org.opencontainers.image.source="https://github.com/HrRodan/agent-workspace-mcp" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${CREATED}" \
      org.opencontainers.image.base.name="${BASE_IMAGE}" \
      io.modelcontextprotocol.server.name="io.github.HrRodan/agent-workspace-mcp"

# Verify the venv is intact and the server module is importable
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import agent_workspace_mcp" || exit 1

# Server venv is activated via PATH above; run the MCP server module
ENTRYPOINT ["python", "-m", "agent_workspace_mcp.server"]
