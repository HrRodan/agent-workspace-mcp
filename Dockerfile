# =============================================================================
# Agent Workspace MCP — Production Dockerfile
# Architecture: two-stage build (uv binary + Python slim runtime)
# Transport:    stdio (JSON-RPC over stdin/stdout)
# Runtime user: mcpuser (UID 1000 by default)
# =============================================================================

# Define the base image once as a global ARG
ARG BASE_IMAGE=python:3.14.4-slim-trixie@sha256:538a18f1db92b4210a0b71aca2d14c156a96dedbe8867465c8ff4dce04d2ec39

# --- Stage 1: uv binary ---
FROM ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a AS uv_bin

# --- Stage 2: Runtime ---
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
    procps \
    zip \
    unzip \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s /usr/bin/fdfind /usr/local/bin/fd

# Create a non-root user with configurable UID/GID for host-mount compatibility
ARG UID=1000
ARG GID=1000
RUN groupadd -g "${GID}" mcpuser && useradd -u "${UID}" -g "${GID}" -m mcpuser

# --- Application install ---
# Pre-create directories with correct ownership (still root)
RUN mkdir -p /app /workspace && chown mcpuser:mcpuser /app /workspace

# Switch to non-root before any file operations
USER mcpuser
WORKDIR /app

# UV_COMPILE_BYTECODE=1 speeds up startup
# UV_LINK_MODE=copy ensures compatibility across Docker layers
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Copy dependency manifests first to maximize layer cache hits
COPY --chown=mcpuser:mcpuser pyproject.toml uv.lock ./

# Install dependencies (without the project itself)
RUN --mount=type=cache,target=/home/mcpuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --no-install-project --no-dev

# Copy application source
COPY --chown=mcpuser:mcpuser README.md ./
COPY --chown=mcpuser:mcpuser src/ ./src/

# Install the project server itself into the venv
RUN --mount=type=cache,target=/home/mcpuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --no-dev

# --- Workspace setup ---
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
