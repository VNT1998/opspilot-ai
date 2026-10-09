from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseQueueBackend(ABC):
    """Abstract interface for OpsPilot asynchronous job queues."""

    @abstractmethod
    async def enqueue(self, job: Dict[str, Any]) -> str:
        """Enqueues a job payload and returns its unique message ID."""
        pass

    @abstractmethod
    async def dequeue(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Dequeues the next job, waiting up to timeout seconds. Includes _message_id."""
        pass

    @abstractmethod
    async def ack(self, message_id: str) -> None:
        """Acknowledges successful processing and persistence of a message."""
        pass

    @abstractmethod
    async def reclaim_pending(self, min_idle_ms: int = 60000) -> List[Dict[str, Any]]:
        """Reclaims unacknowledged messages pending from dead or stalled workers."""
        pass

    @abstractmethod
    async def enqueue_dlq(self, job: Dict[str, Any], reason: Optional[str] = None) -> None:
        """Pushes a failed job to the Dead Letter Queue with failure reason."""
        pass

    @abstractmethod
    async def get_depth(self) -> int:
        """Returns the current pending job queue depth."""
        pass

    @abstractmethod
    async def get_dlq_depth(self) -> int:
        """Returns the number of jobs in the Dead Letter Queue."""
        pass
