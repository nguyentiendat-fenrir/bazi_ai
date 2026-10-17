"""S3-compatible ObjectStore with the same contract as the local volume.

Bytes are streamed to a ``staging/`` key while hashing, then copied to their
content address and the staging key removed. Identical concurrent writers end
with identical bytes at the same address, so the race is harmless.
"""
from __future__ import annotations

from typing import BinaryIO, Iterator
import uuid

from botocore.exceptions import ClientError

from .base import (CHUNK, ChecksumMismatch, HashingReader, ObjectNotFound, ObjectStat,
                   StoredObject, object_key, validate_key)


def _missing(exc: ClientError) -> bool:
    return exc.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey', 'NotFound')


class S3ObjectStore:
    backend = 's3'

    def __init__(self, client, bucket: str, max_bytes: int | None = None):
        self.client = client
        self.bucket = bucket
        self.max_bytes = max_bytes

    def put_if_absent(self, stream: BinaryIO, expected_sha256: str | None = None,
                      namespace: str = 'objects') -> StoredObject:
        staging = f'staging/{uuid.uuid4().hex}'
        reader = HashingReader(stream, self.max_bytes)
        try:
            self.client.upload_fileobj(reader, self.bucket, staging)
            if expected_sha256 and reader.sha256 != expected_sha256:
                raise ChecksumMismatch('content does not match the expected SHA-256')
            key = object_key(reader.sha256, namespace)
            if self.stat(key) is not None:
                return StoredObject(key, reader.sha256, reader.size, created=False)
            self.client.copy_object(Bucket=self.bucket, Key=key,
                                    CopySource={'Bucket': self.bucket, 'Key': staging},
                                    MetadataDirective='REPLACE',
                                    Metadata={'sha256': reader.sha256})
            return StoredObject(key, reader.sha256, reader.size, created=True)
        finally:
            self.client.delete_object(Bucket=self.bucket, Key=staging)

    def get_stream(self, key: str, start: int | None = None,
                   end: int | None = None) -> Iterator[bytes]:
        validate_key(key)
        args = {'Bucket': self.bucket, 'Key': key}
        if start is not None or end is not None:
            if end is not None and end <= (start or 0):
                return iter(())
            args['Range'] = f'bytes={start or 0}-{"" if end is None else end - 1}'
        try:
            body = self.client.get_object(**args)['Body']
        except ClientError as exc:
            if _missing(exc):
                raise ObjectNotFound(key) from None
            raise
        return body.iter_chunks(CHUNK)

    def stat(self, key: str) -> ObjectStat | None:
        validate_key(key)
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _missing(exc):
                return None
            raise
        return ObjectStat(key, head['ContentLength'], head.get('Metadata', {}).get('sha256'),
                          head.get('LastModified'))

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=validate_key(key))

    def list_manifest(self, namespace: str = 'objects') -> Iterator[ObjectStat]:
        paginator = self.client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f'{namespace}/'):
            for item in page.get('Contents', []):
                key = item['Key']
                try:
                    validate_key(key)
                except Exception:
                    continue
                yield ObjectStat(key, item['Size'], key.rsplit('/', 1)[1],
                                 item.get('LastModified'))
