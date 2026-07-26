from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InferenceResult:
    flagged: bool
    category: str
    confidence: float
    rationale: str


class InferenceBackend(Protocol):
    model_name: str

    def classify(self, text: str) -> InferenceResult: ...
