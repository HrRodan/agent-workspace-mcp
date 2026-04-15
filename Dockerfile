# =============================================================================
# Agent Workspace MCP — Production Dockerfile
# Architecture: two-stage build (uv binary + Python slim runtime)
# Transport:    stdio (JSON-RPC over stdin/stdout)
# Runtime user: mcpuser (UID 1000 by default)
# =============================================================================

# --- Stage 1: uv binary ---
FROM ghcr.io/astral-sh/uv:0.11.2 AS uv_bin

# --- Stage 2: Runtime ---
FROM python:3.15.0a8-slim-trixie

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

COPY --from=uv_bin /uv /uvx /bin/

# OCI & MCP metadata
LABEL org.opencontainers.image.title="Agent Workspace MCP" \
      org.opencontainers.image.description="Sandboxed agentic workspace MCP server for LLMs" \
      org.opencontainers.image.url="https://github.com/HrRodan/agent-workspace-mcp" \
      org.opencontainers.image.source="https://github.com/HrRodan/agent-workspace-mcp" \
      org.opencontainers.image.licenses="MIT" \
      io.modelcontextprotocol.server.name="io.github.HrRodan/agent-workspace-mcp"

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
WORKDIR /app

# UV_COMPILE_BYTECODE=1 speeds up startup
# UV_LINK_MODE=copy ensures compatibility across Docker layers
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Copy dependency manifests first to maximize layer cache hits
# uv.lock is explicitly kept out of .dockerignore
COPY pyproject.toml uv.lock ./

# Install dependencies (without the project itself)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev \
 && chown -R mcpuser:mcpuser /app/.venv

# Copy application source
COPY README.md ./
COPY src/ ./src/

# Install the project server itself into the venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
 && chown -R mcpuser:mcpuser /app/.venv

# --- Workspace setup ---
# Pre-create the /workspace directory with correct user ownership
RUN mkdir -p /workspace && chown mcpuser:mcpuser /workspace
WORKDIR /workspace

# UV_PROJECT_ENVIRONMENT ensures agent processes use a local environment
ENV UV_PROJECT_ENVIRONMENT=/workspace/.venv_container \
    PATH="/app/.venv/bin:$PATH"

STOPSIGNAL SIGTERM

USER mcpuser

# Execute the server using its dedicated virtual environment
ENTRYPOINT ["python", "-m", "agent_workspace_mcp.server"]
