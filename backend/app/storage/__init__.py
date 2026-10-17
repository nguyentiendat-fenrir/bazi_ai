"""Blob storage: content-addressed ObjectStore adapters (local volume, S3-compatible)."""
from __future__ import annotations

from ..core.config import Settings
from ..core.health import CheckResult, ReadinessCheck
from .base import ObjectStore


def build_store(settings: Settings) -> ObjectStore:
    if settings.storage_backend == 's3':
        import boto3

        from .s3 import S3ObjectStore
        secret = settings.s3_secret_access_key
        client = boto3.client(
            's3', endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=secret.get_secret_value() if secret else None)
        return S3ObjectStore(client, settings.s3_bucket, settings.max_upload_bytes)
    from .local import LocalObjectStore
    return LocalObjectStore(settings.storage_root, settings.max_upload_bytes)


def storage_check(store: ObjectStore) -> ReadinessCheck:
    async def run() -> CheckResult:
        from starlette.concurrency import run_in_threadpool
        # Listing proves the bucket/root is reachable without writing anything.
        await run_in_threadpool(lambda: next(iter(store.list_manifest()), None))
        return CheckResult('ok', 'REACHABLE')
    return ReadinessCheck('object_storage', essential=True, run=run)
