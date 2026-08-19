from dataclasses import dataclass
from enum import Enum
from typing import Optional


class InteractionProvider(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"


@dataclass(frozen=True)
class InteractionResult:
    verdict: str
    option_index: Optional[int] = None

    def __post_init__(self) -> None:
        if self.verdict not in ("approve", "deny", "leave_it"):
            raise ValueError("unsupported verdict")
        if self.option_index is not None and self.option_index < 0:
            raise ValueError("negative option index")
