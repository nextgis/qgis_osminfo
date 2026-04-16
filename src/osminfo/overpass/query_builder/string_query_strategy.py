from abc import ABC, abstractmethod
from typing import List, Optional


class StringQueryStrategy(ABC):
    """Define the interface for building queries from text input."""

    NAME = ""

    @abstractmethod
    def build(self, search_string: str) -> List[str]:
        pass

    def repair_search(self, search_string: str) -> Optional[str]:
        return None
