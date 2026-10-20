import uuid
from uuid import UUID

import boto3  # type: ignore[import-untyped]

from app.core.settings import get_settings


class FileService:
    def __init__(self) -> None:
        s = get_settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
        )
        self._bucket = s.s3_bucket

    def presigned_upload_key(self, tenant_id: UUID, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        return f"tenants/{tenant_id}/{uuid.uuid4()}.{ext}"

    def presigned_get_url(self, key: str, expires: int = 3600) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires,
        )
        return url
