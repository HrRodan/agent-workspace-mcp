---
name: openai-agents-sdk
argument-hint: "[question or feature]"
description: OpenAI Agents SDK (Python) development. Use when building AI agents, multi-agent workflows, tool integrations, or streaming applications with the openai-agents package.
---

# OpenAI Agents SDK (Python)

Use this skill when developing AI agents using OpenAI Agents SDK (`openai-agents` package).

## Quick Reference

### Installation

```bash
uv add install openai-agents
```

### Environment Variables

```bash
# OpenAI (direct)
OPENROUTER_API_KEY=sk-or-v1-...
DEFAULT_MODEL=google/gemini-3-flash-preview # Use Openrouter provider directly via AsyncOpenAI base_url


### Basic Agent

```python
from agents import Agent, Runner

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
    model="gpt-5.2",  # or "gpt-5", "gpt-5.2-nano"
)

# Synchronous
result = Runner.run_sync(agent, "Tell me a joke")
print(result.final_output)

# Asynchronous
result = await Runner.run(agent, "Tell me a joke")
```

### Key Patterns

| Pattern | Purpose |
|---------|---------|
| Basic Agent | Simple Q&A with instructions |
| OpenRouter/Direct | Custom OpenAI base_url integration |
| AgentOutputSchema | Strict JSON validation with Pydantic |
| Function Tools | External actions (@function_tool) |
| Streaming | Real-time UI (Runner.run_streamed) |
| Handoffs | Specialized agents, delegation |
| Agents as Tools | Orchestration (agent.as_tool) |
| LLM as Judge | Iterative improvement loop |
| Guardrails | Input/output validation |
| Sessions | Automatic conversation history |
| Multi-Agent Pipeline | Multi-step workflows |

## Reference Documentation

For detailed information, see:

- [agents.md](references/agents.md) - Agent creation, Custom base_url (OpenRouter) integration
- [tools.md](references/tools.md) - Function tools, hosted tools, agents as tools
- [structured-output.md](references/structured-output.md) - Pydantic output, AgentOutputSchema
- [streaming.md](references/streaming.md) - Streaming patterns, SSE with FastAPI
- [handoffs.md](references/handoffs.md) - Agent delegation
- [guardrails.md](references/guardrails.md) - Input/output validation
- [sessions.md](references/sessions.md) - Sessions, conversation history
- [patterns.md](references/patterns.md) - Multi-agent workflows, LLM as judge, tracing

## Official Documentation

- **Docs:** https://openai.github.io/openai-agents-python/
- **Examples:** https://github.com/openai/openai-agents-python/tree/main/examples
