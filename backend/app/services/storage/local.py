import os
import uuid
from pathlib import Path
from app.core.config import get_settings
from app.services.storage.base import StorageProvider

settings = get_settings()


class LocalStorageProvider(StorageProvider):
    def __init__(self, base_dir: str = settings.LOCAL_STORAGE_PATH):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_file(self, content: bytes, filename: str, tenant_id: str) -> str:
        tenant_dir = self.base_dir / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(filename).suffix
        safe_filename = f"{uuid.uuid4().hex[:16]}_{Path(filename).stem[:30]}{ext}"
        target_path = tenant_dir / safe_filename

        with open(target_path, "wb") as f:
            f.write(content)

        return str(target_path)

    async def get_file(self, storage_path: str) -> bytes:
        path = Path(storage_path)
        if not path.exists():
            raise FileNotFoundError(f"Storage path {storage_path} does not exist.")
        with open(path, "rb") as f:
            return f.read()

    async def delete_file(self, storage_path: str) -> None:
        path = Path(storage_path)
        if path.exists():
            os.remove(path)


_storage_instance = LocalStorageProvider()


def get_storage_provider() -> StorageProvider:
    return _storage_instance
