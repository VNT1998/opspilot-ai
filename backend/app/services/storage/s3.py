import os
import uuid
from pathlib import Path
from typing import Optional
from app.core.config import get_settings
from app.core.errors import StorageError
from app.services.storage.base import StorageProvider

settings = get_settings()


class S3StorageProvider(StorageProvider):
    """
    S3 and MinIO compatible object storage provider.
    Supports multi-tenant key prefixes: {tenant_id}/{uuid}_{filename}
    Fails closed in production without silent local fallbacks.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        self.bucket_name = bucket_name or settings.S3_BUCKET_NAME
        self.region = region or settings.S3_REGION
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")

    def _get_client(self):
        try:
            import boto3
            from botocore.config import Config

            cfg = Config(s3={"addressing_style": settings.S3_ADDRESSING_STYLE})
            access_key = os.getenv("AWS_ACCESS_KEY_ID")
            secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            client_kwargs = {
                "region_name": self.region,
                "endpoint_url": self.endpoint_url,
                "config": cfg,
            }
            if access_key and secret_key:
                client_kwargs["aws_access_key_id"] = access_key
                client_kwargs["aws_secret_access_key"] = secret_key

            return boto3.client("s3", **client_kwargs)
        except Exception as e:
            raise StorageError(f"Failed to initialize S3 client: {e}")

    async def save_file(
        self,
        content: bytes,
        filename: str,
        tenant_id: str,
        content_type: Optional[str] = None,
    ) -> str:
        if not self.bucket_name and (settings.STORAGE_TYPE == "s3" or settings.ENVIRONMENT == "production"):
            raise StorageError("S3 bucket name is required for S3 storage.")

        ext = Path(filename).suffix
        safe_key = f"{tenant_id}/{uuid.uuid4().hex[:16]}_{Path(filename).stem[:30]}{ext}"

        try:
            client = self._get_client()
            put_kwargs = {
                "Bucket": self.bucket_name,
                "Key": safe_key,
                "Body": content,
                "Metadata": {"tenant_id": tenant_id},
            }
            if content_type:
                put_kwargs["ContentType"] = content_type

            client.put_object(**put_kwargs)
            return f"s3://{self.bucket_name}/{safe_key}"
        except Exception as e:
            # In production or when STORAGE_TYPE is explicitly s3, fail closed immediately
            if settings.ENVIRONMENT == "production" or settings.STORAGE_TYPE == "s3":
                raise StorageError(f"S3 upload failed for '{safe_key}': {e}") from e

            # Dev/test local fallback only when explicitly not configured for S3 and not production
            fallback_path = Path(settings.LOCAL_STORAGE_PATH) / safe_key
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback_path, "wb") as f:
                f.write(content)
            return str(fallback_path)

    async def get_file(self, storage_path: str) -> bytes:
        if storage_path.startswith("s3://"):
            parts = storage_path[5:].split("/", 1)
            if len(parts) < 2:
                raise StorageError(f"Malformed S3 storage URI: {storage_path}")
            bucket = parts[0]
            key = parts[1]
            try:
                client = self._get_client()
                response = client.get_object(Bucket=bucket, Key=key)
                return response["Body"].read()
            except Exception as e:
                raise StorageError(f"Failed to retrieve object from S3 ({storage_path}): {e}") from e

        if settings.ENVIRONMENT == "production" or settings.STORAGE_TYPE == "s3":
            raise StorageError(f"Invalid storage path scheme '{storage_path}' for S3 storage provider.")

        # Dev/test fallback local path
        p = Path(storage_path)
        if not p.exists():
            raise StorageError(f"Storage object at '{storage_path}' not found.")
        with open(p, "rb") as f:
            return f.read()

    async def delete_file(self, storage_path: str) -> None:
        if storage_path.startswith("s3://"):
            parts = storage_path[5:].split("/", 1)
            if len(parts) < 2:
                raise StorageError(f"Malformed S3 storage URI: {storage_path}")
            bucket = parts[0]
            key = parts[1]
            try:
                client = self._get_client()
                client.delete_object(Bucket=bucket, Key=key)
                return
            except Exception as e:
                raise StorageError(f"Failed to delete object from S3 ({storage_path}): {e}") from e

        if settings.ENVIRONMENT == "production" or settings.STORAGE_TYPE == "s3":
            raise StorageError(f"Invalid storage path scheme '{storage_path}' for S3 storage provider.")

        p = Path(storage_path)
        if p.exists():
            os.remove(p)
