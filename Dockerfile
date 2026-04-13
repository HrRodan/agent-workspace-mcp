# Use a separate stage for uv binary
FROM ghcr.io/astral-sh/uv:latest AS uv_bin

# Final stage
FROM python:3.14-slim-trixie

# Copy uv binary from the distroless image
COPY --from=uv_bin /uv /uvx /bin/

# Label for discoverability
LABEL io.modelcontextprotocol.server.name="io.github.HrRodan/agent-workspace-mcp"

# Install minimal system utilities
# Added procps for process management logic often needed by agents.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    nano \
    patch \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group with an explicit UID for Linux compatibility
RUN groupadd -g 1000 mcpuser && useradd -u 1000 -g 1000 -m mcpuser

# Set up the server application directory
WORKDIR /app

# Enable byte compilation for faster startup
# ENV UV_LINK_MODE=copy ensures compatibility across Docker layers
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy the dependency files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install MCP server dependencies into a dedicated .venv in /app
# We use --frozen to ensure deterministic builds based on uv.lock
# We use --no-dev to exclude development dependencies (pytest, etc.)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy the rest of the server application code
COPY README.md ./
COPY src/ ./src/

# Install the server project itself into the .venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Setup dynamic execution workspace
RUN mkdir -p /workspace && chown mcpuser:mcpuser /workspace
WORKDIR /workspace

# Set environments to avoid polluting host machine's venvs via mounts
# This ensures any 'uv run' executed by agents inside /workspace gets a localized environment
ENV UV_PROJECT_ENVIRONMENT=/workspace/.venv_container

# Switch to the non-root user before executing
USER mcpuser

# Execute the server using its dedicated virtual environment
ENTRYPOINT ["/app/.venv/bin/python", "-m", "agent_workspace_mcp.server"]
