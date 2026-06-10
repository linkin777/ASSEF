from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid


class CallerType(Enum):
    RED_TEAM = "red_team"
    BLUE_TEAM = "blue_team"
    CONSTITUTION_JUDGE = "constitution_judge"
    BLUE_SELF_ITER = "blue_self_iter"
    LLM_TEST = "llm_test"


@dataclass
class Metrics:
    useful: bool | None = None
    format_valid: bool | None = None
    format_rate: float = 1.0
    intent_guessing: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RecordEntry:
    timestamp: str
    caller: str
    backend: str
    model: str
    messages: str
    response: str
    duration_ms: float
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    round: int | None = None
    metrics: Metrics = field(default_factory=Metrics)

    def to_dict(self) -> dict:
        return asdict(self)
