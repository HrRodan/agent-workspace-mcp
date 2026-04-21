@./.agents/rules/use-uv.md

@./.agents/rules/architect.md

@./.agents/rules/information-retrival.md

# Testing

Do **not** run integration tests under `/tests/integration` by default. They execute real LLM calls and incur costs.

- **`uv run pytest`**: Run ONLY the fast unit tests (default).
- **`uv run pytest tests/integration`**: Run ONLY the slower integration tests.
- **`uv run pytest tests tests/integration`**: Run ALL tests.
