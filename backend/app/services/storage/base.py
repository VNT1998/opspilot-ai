from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageProvider(Protocol):
    async def save_file(self, content: bytes, filename: str, tenant_id: str) -> str:
        """Saves file bytes and returns the stored relative or absolute path."""
        ...

    async def get_file(self, storage_path: str) -> bytes:
        """Retrieves file bytes from storage."""
        ...

    async def delete_file(self, storage_path: str) -> None:
        """Deletes file from storage."""
        ...
