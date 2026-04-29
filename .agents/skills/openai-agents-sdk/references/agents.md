# Agents

## Basic Agent Creation

```python
from agents import Agent, Runner

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
    model="gpt-5.2",  # or "gpt-5", "gpt-5.2-nano"
)

# Synchronous execution
result = Runner.run_sync(agent, "Tell me a joke")
print(result.final_output)

# Asynchronous execution
result = await Runner.run(agent, "Tell me a joke")
```

## OpenRouter / Custom Provider (Direct)

```python
import os
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel

MODEL = os.getenv("MODEL", "google/gemini-2.0-flash-001")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)
model = OpenAIChatCompletionsModel(model=MODEL, openai_client=client)

agent = Agent(
    name="Assistant",
    instructions="You are helpful.",
    model=model,
)
```

## Dynamic System Prompt

```python
from agents import Agent, Runner, RunContextWrapper

def dynamic_instructions(
    ctx: RunContextWrapper[dict], agent: Agent[dict]
) -> str:
    user_name = ctx.context.get("user_name", "User")
    return f"You are helping {user_name}. Be friendly and helpful."

agent = Agent(
    name="DynamicBot",
    instructions=dynamic_instructions,  # Function instead of string
    model="gpt-5.2",
)

result = await Runner.run(
    agent,
    "Hello!",
    context={"user_name": "Alice"},
)
```

## Loading Prompts from Files

```python
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"

def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")

agent = Agent(
    name="Planner",
    instructions=load_prompt("planner.md"),
    model="gpt-5.2",
)
```

## Agent Configuration Options

| Option | Description |
|--------|-------------|
| `name` | Agent identifier |
| `instructions` | System prompt (string or function) |
| `model` | Model name or LitellmModel instance |
| `tools` | List of tools the agent can use |
| `handoffs` | List of agents to delegate to |
| `output_type` | Pydantic model for structured output |
| `model_settings` | ModelSettings for fine-tuning |
| `input_guardrails` | Input validation functions |
| `output_guardrails` | Output validation functions |
