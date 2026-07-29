"""
LLM Client Abstraction Layer

Provides a unified interface for different LLM providers (Groq, Anthropic, OpenAI).
Adapts Anthropic's API to match the OpenAI-compatible interface used throughout the app.
"""

import logging
from typing import Optional, Any, List, Dict, Union
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


__all__ = ['get_llm_client', 'get_active_model', 'get_max_tokens_param']

# Type definitions for the wrapper
class MessageContent:
    def __init__(self, content: str):
        self.content = content

class Choice:
    def __init__(self, content: str):
        self.message = MessageContent(content)

class ChatCompletionResponse:
    def __init__(self, content: str):
        self.choices = [Choice(content)]

class AnthropicAdapter:
    """
    Adapts Anthropic's Client to look like OpenAI's AsyncClient
    specifically for chat.completions.create calls.
    """
    def __init__(self, api_key: str):
        try:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=api_key)
        except ImportError:
            logger.error("Anthropic package not found. Please install 'anthropic'.")
            raise

    class Chat:
        def __init__(self, parent):
            self.parent = parent
            self.completions = self.Completions(parent)

        class Completions:
            def __init__(self, parent):
                self.parent = parent

            async def create(
                self,
                model: str,
                messages: List[Dict[str, str]],
                temperature: float = 0.7,
                max_tokens: int = 1024,
                response_format: Optional[Dict[str, str]] = None,
                **kwargs
            ) -> ChatCompletionResponse:
                """
                Translate OpenAI chat completion parameters to Anthropic messages API.
                """
                system_prompt = None
                filtered_messages = []
                
                # Extract system prompt and format messages
                for msg in messages:
                    if msg["role"] == "system":
                        system_prompt = msg["content"]
                    else:
                        filtered_messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                
                # Default max_tokens if not provided or flexible
                if max_tokens is None:
                    max_tokens = 4096
                
                # Call Anthropic API
                try:
                    # Note: response_format={"type": "json_object"} is handled natively 
                    # by prompts in this app, but we can enforce tool use or prefill 
                    # if needed. For now, we rely on the strong prompts.
                    
                    params = {
                        "model": model,
                        "messages": filtered_messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    }
                    
                    if system_prompt:
                        params["system"] = system_prompt
                        
                    response = await self.parent.client.messages.create(**params)
                    
                    return ChatCompletionResponse(response.content[0].text)
                    
                except Exception as e:
                    logger.error(f"Anthropic generation failed: {e}")
                    raise

    @property
    def chat(self):
        return self.Chat(self)


def get_llm_client() -> Union[AsyncOpenAI, AnthropicAdapter]:
    """
    Factory to get the appropriate LLM client based on configuration.
    """
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("LLM_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is not set.")
        return AnthropicAdapter(api_key=settings.ANTHROPIC_API_KEY)
        
    elif provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("LLM_PROVIDER is 'openai' but OPENAI_API_KEY is not set.")
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
    else:  # Default to Groq
        if not settings.GROQ_API_KEY:
             # Fallback check if it was somehow skipped, though config usually enforces it 
             # unless we made it optional.
             logger.warning("Groq API Key not found, checking settings...")
        
        return AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url=settings.GROQ_API_BASE
        )

def get_active_model() -> str:
    """Get the model string for the active provider."""
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "anthropic":
        return settings.ANTHROPIC_MODEL
    elif provider == "openai":
        return settings.OPENAI_MODEL
    else:
        return settings.GROQ_MODEL


def get_max_tokens_param(max_tokens: int = 1024) -> Dict[str, int]:
    """
    Get the appropriate max tokens parameter based on the provider and model.
    
    **OpenAI API Parameter Usage (verified from actual API errors):**
    - GPT-4 series (gpt-4o, gpt-4-turbo): use 'max_completion_tokens'
    - GPT-5 series (gpt-5.x, gpt-5.2, etc.): use 'max_completion_tokens' 
    - o1 series (o1-preview, o1-mini): use 'max_completion_tokens'
    - o3 series: use 'max_completion_tokens'
    - GPT-3.5 and older: use 'max_tokens'
    - Groq, Anthropic: always 'max_tokens'
    
    Args:
        max_tokens: The desired maximum number of tokens
        
    Returns:
        Dict with the appropriate parameter name and value
    """
    provider = settings.LLM_PROVIDER.lower()
    model = get_active_model()
    
    # OpenAI's newer models (GPT-4+, GPT-5+, o1, o3) use max_completion_tokens
    if provider == "openai" and settings.OPENAI_API_KEY:
        model_lower = model.lower()
        # These models use max_completion_tokens:
        # - gpt-4o variants (gpt-4o, gpt-4o-mini)
        # - gpt-4-turbo variants
        # - gpt-5 series (gpt-5, gpt-5.2, gpt-5.x, etc.)
        # - gpt-6+ (future proofing)
        # - o1 series (o1-preview, o1-mini)
        # - o3 series
        # 
        # Old models (gpt-3.5-turbo) still use max_tokens
        if any(m in model_lower for m in ["gpt-4o", "gpt-4-turbo", "o1-preview", "o1-mini", "o3"]) or \
           model_lower.startswith("gpt-5") or model_lower.startswith("gpt-6"):
            return {"max_completion_tokens": max_tokens}
    
    # All other cases: GPT-3.5, Groq, Anthropic
    return {"max_tokens": max_tokens}
