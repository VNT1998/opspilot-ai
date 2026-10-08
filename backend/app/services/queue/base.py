from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseQueueBackend(ABC):
    """Abstract interface for OpsPilot asynchronous job queues."""

    @abstractmethod
    async def enqueue(self, job: Dict[str, Any]) -> None:
        """Enqueues a job payload."""
        pass

    @abstractmethod
    async def dequeue(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Dequeues the next job, waiting up to timeout seconds."""
        pass

    @abstractmethod
    async def enqueue_dlq(self, job: Dict[str, Any]) -> None:
        """Pushes a failed job to the Dead Letter Queue."""
        pass

    @abstractmethod
    async def get_depth(self) -> int:
        """Returns the current pending job queue depth."""
        pass

    @abstractmethod
    async def get_dlq_depth(self) -> int:
        """Returns the number of jobs in the Dead Letter Queue."""
        pass
