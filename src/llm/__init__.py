"""Provider-agnostic LLM layer for DocMind.

    from src.llm.factory import get_client, build_vision_client, get_text_client
"""

from src.llm.base import LLMClient, LLMResult, VisionLLMClient, VisionResult
from src.llm.budget import BudgetExceededError, BudgetGuard
from src.llm.factory import build_vision_client, get_client, get_text_client

__all__ = [
    "LLMClient",
    "LLMResult",
    "VisionLLMClient",  # backwards-compatible alias
    "VisionResult",  # backwards-compatible alias
    "BudgetGuard",
    "BudgetExceededError",
    "build_vision_client",
    "get_client",
    "get_text_client",
]
