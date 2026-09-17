from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    model_name: str

    async def invoke(self, prompt: str, payload: dict) -> str: ...
    async def structured(self, task: str, schema: type[T], payload: dict) -> T: ...
