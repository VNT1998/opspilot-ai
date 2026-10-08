import io
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

    async def save_file(self, content: bytes, filename: str, tenant_id: str) -> str:
        ext = Path(filename).suffix
        safe_key = f"{tenant_id}/{uuid.uuid4().hex[:16]}_{Path(filename).stem[:30]}{ext}"

        # If aioboto3 or boto3 is available and AWS credentials configured, upload to S3/MinIO
        try:
            import boto3
            s3_client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
            )
            s3_client.put_object(
                Bucket=self.bucket_name,
                Key=safe_key,
                Body=content,
            )
            return f"s3://{self.bucket_name}/{safe_key}"
        except Exception as e:
            # Fallback to local storage replica if S3 connection is unconfigured
            fallback_path = Path(settings.LOCAL_STORAGE_PATH) / safe_key
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback_path, "wb") as f:
                f.write(content)
            return str(fallback_path)

    async def get_file(self, storage_path: str) -> bytes:
        if storage_path.startswith("s3://"):
            parts = storage_path[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1]
            try:
                import boto3
                s3_client = boto3.client(
                    "s3",
                    region_name=self.region,
                    endpoint_url=self.endpoint_url,
                )
                response = s3_client.get_object(Bucket=bucket, Key=key)
                return response["Body"].read()
            except Exception as e:
                raise StorageError(f"Failed to retrieve object from S3 ({storage_path}): {str(e)}")

        # Fallback local path
        p = Path(storage_path)
        if not p.exists():
            raise StorageError(f"Storage object at '{storage_path}' not found.")
        with open(p, "rb") as f:
            return f.read()

    async def delete_file(self, storage_path: str) -> None:
        if storage_path.startswith("s3://"):
            parts = storage_path[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1]
            try:
                import boto3
                s3_client = boto3.client(
                    "s3",
                    region_name=self.region,
                    endpoint_url=self.endpoint_url,
                )
                s3_client.delete_object(Bucket=bucket, Key=key)
                return
            except Exception as e:
                raise StorageError(f"Failed to delete object from S3 ({storage_path}): {str(e)}")

        p = Path(storage_path)
        if p.exists():
            os.remove(p)
