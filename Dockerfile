# =============================================================================
# Agent Workspace MCP — Production Dockerfile
# Architecture: two-stage build (uv binary + Python slim runtime)
# Transport:    stdio (JSON-RPC over stdin/stdout)
# Runtime user: mcpuser (UID 1000 by default)
# =============================================================================

# Define the base image once as a global ARG
ARG BASE_IMAGE=python:3.14.4-slim@sha256:c11aee3b3cae066f55d1e9318fc812673aa6557073b0db0d792b59491b262e0c

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
FROM ghcr.io/astral-sh/uv:0.11.10@sha256:bca7f6959666f3524e0c42129f9d8bbcfb0c180d847f5187846b98ff06125ead AS uv_bin

# --- Stage 3: Runtime ---
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

COPY --from=uv_bin /uv /uvx /bin/

# Install minimal system utilities required by the agentic workspace
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    patch \
    tree \
    fd-find \
    ripgrep \
    zip \
    unzip \
  && rm -rf /var/lib/apt/lists/* \
  && ln -s /usr/bin/fdfind /usr/local/bin/fd

COPY --from=rtk_bin /usr/local/bin/rtk /usr/local/bin/rtk

# CIS Docker Benchmark 4.8: Remove setuid/setgid permissions in the image
# This prevents privilege escalation vulnerabilities from system binaries like `su` or `passwd`
RUN find / -xdev \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} + || true

# Create a non-root user with configurable UID/GID for host-mount compatibility
ARG UID=1000
ARG GID=1000
RUN groupadd -g "${GID}" mcpuser && useradd -l -u "${UID}" -g "${GID}" -m mcpuser

# --- Application install ---
# Pre-create directories with correct ownership (still root)
RUN mkdir -p /app /workspace && chown mcpuser:mcpuser /workspace

WORKDIR /app

# UV_COMPILE_BYTECODE=1 speeds up startup
# UV_LINK_MODE=copy ensures compatibility across Docker layers
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

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

# Ensure /app is readable by mcpuser but owned by root
RUN chmod -R a+rX /app

# --- Workspace setup ---
USER mcpuser
WORKDIR /workspace

# UV_PROJECT_ENVIRONMENT ensures agent processes use a local environment
ENV UV_PROJECT_ENVIRONMENT=/workspace/.venv_container \
    PATH="/app/.venv/bin:$PATH"

STOPSIGNAL SIGTERM

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

# Execute the server using its dedicated virtual environment
ENTRYPOINT ["python", "-m", "agent_workspace_mcp.server"]
