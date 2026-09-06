"""Mechanical interface protocol definitions for demo."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple


@dataclass(frozen=True)
class DemoPayload:
    """Demo payload data container."""
    payload_id: str
    """Unique payload identifier."""
    content: str = ''
    """Payload content."""


class DemoProcessorProtocol(Protocol):
    """Demo processor interface protocol."""

    def process(self, payload: DemoPayload) -> bool:
        """Process the demo payload."""
        raise NotImplementedError("Protocol method must be implemented by concrete engine.")

    def reset(self) -> None:
        """Reset processor state."""
        raise NotImplementedError("Protocol method must be implemented by concrete engine.")
