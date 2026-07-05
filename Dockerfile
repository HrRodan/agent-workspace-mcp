# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# =============================================================================
# Agent Workspace MCP — Production Dockerfile
# Architecture: three-stage build (rtk binary, uv binary, Python slim runtime)
# Transport:    stdio (JSON-RPC over stdin/stdout)
# Runtime user: mcpuser (UID 1000 by default)
# =============================================================================

# Global ARG: single source of truth for the base image (used by Renovate + LABEL)
ARG BASE_IMAGE=python:3.14.6-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1

# --- Stage 1: rtk binary ---
FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS rtk_bin
RUN apk add --no-cache curl tar
# renovate: datasource=github-releases depName=rtk-ai/rtk
ARG RTK_VERSION="0.42.4"
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        RTK_URL="rtk-x86_64-unknown-linux-musl.tar.gz"; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        RTK_URL="rtk-aarch64-unknown-linux-gnu.tar.gz"; \
    else \
        echo "Unsupported architecture: $TARGETARCH" && exit 1; \
    fi && \
    RTK_CLEAN_VERSION="${RTK_VERSION#v}" && \
    RTK_DOWNLOAD_URL="https://github.com/rtk-ai/rtk/releases/download/v${RTK_CLEAN_VERSION}/${RTK_URL}" && \
    echo "Downloading rtk v${RTK_CLEAN_VERSION} from ${RTK_DOWNLOAD_URL}" && \
    curl -fsSL --retry 3 --retry-delay 5 "${RTK_DOWNLOAD_URL}" -o /tmp/rtk.tar.gz && \
    tar -xzf /tmp/rtk.tar.gz -C /usr/local/bin rtk && \
    rm -f /tmp/rtk.tar.gz && \
    test -x /usr/local/bin/rtk && echo "rtk binary OK ($(wc -c < /usr/local/bin/rtk) bytes)"

# --- Stage 2: uv binary ---
FROM ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 AS uv_bin

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
