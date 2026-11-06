"""Clips and thumbnails in S3-compatible object storage (RustFS locally, any S3 in production).

The calls are blocking (boto3); the recorder runs them in a worker thread.
"""

import json
import logging
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_MISSING = {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}
_ALREADY_THERE = {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}


class MediaStore(Protocol):
    description: str

    def ensure_bucket(self) -> None: ...
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> tuple[bytes, str] | None: ...


def public_read_policy(bucket: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }


class S3MediaStore:
    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        public_read: bool = False,
    ) -> None:
        self.bucket = bucket
        self.public_read = public_read
        self.description = f"{endpoint_url}/{bucket}"
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},  # RustFS / MinIO style: http://host:9000/<bucket>/<key>
                connect_timeout=2,
                read_timeout=15,
                retries={"max_attempts": 2, "mode": "standard"},
                # Newer boto3 adds CRC checksums to every upload; not every S3 clone accepts them.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def ensure_bucket(self) -> None:
        try:
            self._s3.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in _MISSING:
                raise
            try:
                self._s3.create_bucket(Bucket=self.bucket)
                logger.info("Created bucket %s", self.description)
            except ClientError as e:  # someone else created it in the meantime
                if e.response.get("Error", {}).get("Code") not in _ALREADY_THERE:
                    raise
        if self.public_read:
            try:
                self._s3.put_bucket_policy(Bucket=self.bucket, Policy=json.dumps(public_read_policy(self.bucket)))
            except ClientError as e:  # clips still work through GET /media
                logger.warning("Could not make bucket %s public: %s", self.description, e)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> tuple[bytes, str] | None:
        try:
            obj = self._s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in _MISSING:
                return None
            raise
        return obj["Body"].read(), obj.get("ContentType") or "application/octet-stream"


class MemoryMediaStore:
    """For tests."""

    description = "memory"

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def ensure_bucket(self) -> None:
        pass

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (bytes(data), content_type)

    def get(self, key: str) -> tuple[bytes, str] | None:
        return self.objects.get(key)
