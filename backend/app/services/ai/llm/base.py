from __future__ import annotations
from abc import ABC, abstractmethod
from app.services.ai.llm.types import Capabilities, LLMRequest, LLMResponse


class LLMProvider(ABC):
    """Provider-agnostic LLM interface. Implementations normalize one SDK."""

    name: str = "base"
    capabilities: Capabilities = Capabilities()

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Run a unary completion and return a normalized response.

        Raises a subclass of LLMError on failure.
        """
        raise NotImplementedError
