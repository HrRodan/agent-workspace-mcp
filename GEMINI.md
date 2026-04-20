@./.agents/rules/use-uv.md

@./.agents/rules/architect.md

## Information Retrival

Always use Context7 when I need library/API documentation, code generation, setup or configuration steps without me having to explicitly ask.

Use tavily_search for web search. Set the "search_depth" = "advanced" and "include_answer" = "advanced". Use tavily_extract to read websites, use "extract_depth" = "advanced" if detailed information are necessary.

## Testing

Do **not** run integration tests under `/tests/integration` by default. They execute real LLM calls and incur costs.

- **`uv run pytest`**: Run ONLY the fast unit tests (default).
- **`uv run pytest tests/integration`**: Run ONLY the slower integration tests.
- **`uv run pytest tests tests/integration`**: Run ALL tests.
