from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.client import BaseClient

from core.settings import Settings


@dataclass(frozen=True)
class ObjectStat:
    key: str
    size: int
    etag: str | None


class R2Client:
    def __init__(self, settings: Settings, client: BaseClient | None = None) -> None:
        self.settings = settings
        self.bucket = settings.r2_bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return False
        return True

    def read_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"].read()
        return bytes(body)

    def write_bytes(self, key: str, body: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return keys


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def read_bytes(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def write_bytes(
        self,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def list_keys(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        return [str(path.relative_to(self.root)) for path in base.rglob("*") if path.is_file()]


def gzip_body(body: bytes) -> bytes:
    return gzip.compress(body, mtime=0)


def gunzip_body(body: bytes) -> bytes:
    return gzip.decompress(body)


def sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
