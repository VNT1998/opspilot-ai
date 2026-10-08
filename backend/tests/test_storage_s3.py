from unittest.mock import MagicMock, patch
import pytest
from app.core.config import get_settings
from app.core.errors import StorageError
from app.services.storage.s3 import S3StorageProvider


@pytest.mark.asyncio
async def test_s3_missing_bucket_fails_in_production(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "STORAGE_TYPE", "s3")
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "")

    provider = S3StorageProvider(bucket_name="")
    with pytest.raises(StorageError, match="bucket name is required"):
        await provider.save_file(b"test content", "doc.pdf", "tenant-1")


@pytest.mark.asyncio
async def test_s3_upload_failure_fails_closed_in_production(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "STORAGE_TYPE", "s3")

    provider = S3StorageProvider(bucket_name="my-bucket")

    mock_client = MagicMock()
    mock_client.put_object.side_effect = RuntimeError("S3 connection timed out")

    with patch.object(provider, "_get_client", return_value=mock_client):
        with pytest.raises(StorageError, match="S3 upload failed"):
            await provider.save_file(b"content", "invoice.pdf", "tenant-1", content_type="application/pdf")


@pytest.mark.asyncio
async def test_s3_get_failure_raises_storage_error():
    provider = S3StorageProvider(bucket_name="my-bucket")
    mock_client = MagicMock()
    mock_client.get_object.side_effect = RuntimeError("Object not found in S3")

    with patch.object(provider, "_get_client", return_value=mock_client):
        with pytest.raises(StorageError, match="Failed to retrieve object"):
            await provider.get_file("s3://my-bucket/tenant-1/key.pdf")


@pytest.mark.asyncio
async def test_s3_delete_failure_raises_storage_error():
    provider = S3StorageProvider(bucket_name="my-bucket")
    mock_client = MagicMock()
    mock_client.delete_object.side_effect = RuntimeError("Access Denied")

    with patch.object(provider, "_get_client", return_value=mock_client):
        with pytest.raises(StorageError, match="Failed to delete object"):
            await provider.delete_file("s3://my-bucket/tenant-1/key.pdf")
