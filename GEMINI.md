@./.agents/rules/use-uv.md

@./.agents/rules/architect.md

@./.agents/rules/information-retrival.md

# Testing

- **`uv run pytest`**: Run ONLY the fast unit tests (default). Always run this first before running integration tests.
- **`uv run pytest tests/container`**: Run container tests (requires `docker build -t agent-workspace-mcp .`).
- **`uv run pytest tests/integration`**: Run ONLY the slower integration tests (requires API keys + Docker).
- **`uv run pytest tests tests/container tests/integration`**: Run ALL tests.

Before running container or integration tests the Docker container has to be rebuild with **default values** for all arguments.

# Updating the Skill

After succesfull implementation update the SKILL.md file under skills/agent-workspace-mcp/SKILL.md if the modifications imply changes on how to use the tools.
