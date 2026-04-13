FROM ghcr.io/astral-sh/uv:python3.14-trixie

# Label for discoverability
LABEL io.modelcontextprotocol.server.name="io.github.HrRodan/agent-workspace-mcp"

# Install minimal system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    nano \
    patch \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group with an explicit UID for Linux compatibility
RUN groupadd -g 1000 mcpuser && useradd -u 1000 -g 1000 -m mcpuser

# Setup workspace and permissions
RUN mkdir -p /workspace && chown mcpuser:mcpuser /workspace
WORKDIR /workspace

# Set environments to avoid polluting host machine's .venv via mounts
ENV UV_PROJECT_ENVIRONMENT=/workspace/.venv_container

# Copy and install the server application via uv
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY src/ /app/src/

# Install the package system-wide
RUN uv pip install --system /app

# Switch to the non-root user before executing
USER mcpuser

# Execute the FastMCP server directly
ENTRYPOINT ["python", "-m", "agent_workspace_mcp.server"]
