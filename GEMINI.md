@./.agents/rules/use-uv.md

@./.agents/rules/architect.md

@./.agents/rules/information-retrival.md

# Testing

Do **not** run integration tests under `/tests/integration` by default. They execute real LLM calls and incur costs.  

- **`uv run pytest`**: Run ONLY the fast unit tests (default). Always run this first before running integration tests.

Before running integration tests the Docker container has to be rebuild with **default values** for all arguments.

- **`uv run pytest tests/integration`**: Run ONLY the slower integration tests.
- **`uv run pytest tests tests/integration`**: Run ALL tests.

# Updating the Skill

After succesfull implementation update the SKILL.md file under skills/agent-workspace-mcp/SKILL.md if the modifications imply changes on how to use the tools.
