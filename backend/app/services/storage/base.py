from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class StoredFileMetadata:
    storage_path: str
    filename: str
    tenant_id: str
    size_bytes: int
    content_type: Optional[str] = None


@runtime_checkable
class StorageProvider(Protocol):
    async def save_file(
        self,
        content: bytes,
        filename: str,
        tenant_id: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Saves file bytes and returns the stored path or URI."""
        ...

    async def get_file(self, storage_path: str) -> bytes:
        """Retrieves file bytes from storage."""
        ...

    async def delete_file(self, storage_path: str) -> None:
        """Deletes file from storage."""
        ...
