from dataclasses import dataclass
from typing import Protocol

from app.ai.schemas import CandidateProfileData


class AIProviderError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class AIResult:
    profile: CandidateProfileData
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProvider(Protocol):
    name: str
    model: str

    async def parse_resume(self, text: str) -> AIResult: ...

    async def close(self) -> None: ...
