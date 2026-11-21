"""Base contract for all trading strategies."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseStrategy(ABC):
    id: str = "base"
    name: str = "Base Strategy"
    description: str = ""
    risk: str = "MEDIUM"

    @abstractmethod
    def analyze(
        self,
        candles: List[Dict[str, Any]],
        indicators: Dict[str, List[Optional[float]]],
    ) -> Optional[Dict[str, Any]]:
        """Return a signal dict or None when there is no setup."""
        raise NotImplementedError

    def info(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
        }
