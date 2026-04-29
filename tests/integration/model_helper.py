import os
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel

def get_openrouter_model(model_name: str = None) -> OpenAIChatCompletionsModel:
    """
    Creates an OpenAIChatCompletionsModel configured for OpenRouter.
    
    If model_name is not provided, it defaults to the DEFAULT_MODEL environment variable
    or 'google/gemini-2.0-flash-001'.
    """
    if model_name is None:
        model_name = os.environ.get("DEFAULT_MODEL", "google/gemini-2.0-flash-001")
    
    # Strip 'openrouter/' prefix if it exists to maintain backwards compatibility
    if model_name.startswith("openrouter/"):
        model_name = model_name[len("openrouter/"):]
        
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        # Fallback for testing if key is not strictly required at initialization time
        # but usually it should be present.
        api_key = "sk-or-v1-placeholder"
        
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    return OpenAIChatCompletionsModel(model=model_name, openai_client=client)
