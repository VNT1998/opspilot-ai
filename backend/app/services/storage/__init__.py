from app.core.config import get_settings
from app.services.storage.base import StorageProvider
from app.services.storage.local import LocalStorageProvider
from app.services.storage.s3 import S3StorageProvider

settings = get_settings()

_local_provider = LocalStorageProvider()
_s3_provider = S3StorageProvider()


def get_storage_provider() -> StorageProvider:
    if settings.STORAGE_TYPE == "s3":
        return _s3_provider
    return _local_provider


__all__ = [
    "StorageProvider",
    "LocalStorageProvider",
    "S3StorageProvider",
    "get_storage_provider",
]
