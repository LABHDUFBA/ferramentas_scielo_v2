"""Optional, failure-safe S3 upload support for scraped files."""

import logging
import os
from pathlib import Path


LOGGER = logging.getLogger("scielo")


class S3Uploader:
    """Uploads files using the normal boto3 credential provider chain."""

    def __init__(self, bucket, prefix="", endpoint_url=None, delete_local=False):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "S3 upload requires boto3. Install it with: pip install boto3"
            ) from exc

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.delete_local = delete_local
        self.client = boto3.client("s3", endpoint_url=endpoint_url)

    def upload(self, file_path, output_root):
        """Upload *file_path* relative to output_root and optionally remove it.

        A failed upload intentionally leaves the original local file untouched so
        a later run can retry it.
        """
        path = Path(file_path)
        try:
            relative_path = path.resolve().relative_to(Path(output_root).resolve())
        except ValueError:
            raise ValueError(f"File outside output directory: {path}")

        key_parts = [part for part in (self.prefix, relative_path.as_posix()) if part]
        key = "/".join(key_parts)
        try:
            self.client.upload_file(str(path), self.bucket, key)
        except Exception:
            LOGGER.exception(
                "S3 upload failed; retaining local file",
                extra={"event": "s3_upload_failed", "file_path": str(path), "s3_key": key},
            )
            return False

        LOGGER.info(
            "S3 upload completed",
            extra={"event": "s3_upload_completed", "file_path": str(path), "s3_key": key},
        )
        if self.delete_local:
            try:
                os.remove(path)
                LOGGER.info(
                    "Removed local file after S3 upload",
                    extra={"event": "local_file_deleted", "file_path": str(path), "s3_key": key},
                )
            except OSError:
                LOGGER.exception(
                    "S3 upload succeeded but local file could not be removed",
                    extra={"event": "local_file_delete_failed", "file_path": str(path), "s3_key": key},
                )
                return False
        return True
