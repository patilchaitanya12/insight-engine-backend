from abc import ABC, abstractmethod
from typing import Dict, Any


class LLMProvider(ABC):

    @abstractmethod
    async def generate_structured(self, prompt: str) -> Dict[str, Any]:
        pass