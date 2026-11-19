"""MinIO object storage with two buckets and different access models:

- media (s3_bucket_media): public-read photos and documentation files,
  served by nginx at `/media/`.
- documents (s3_bucket_documents): private customer documents. Readable only
  through short-lived presigned URLs minted after an authorization check.
  nginx proxies them via `/sosnet-documents/` with the internal Host header
  so the signature still validates (see server-migration-guide.md §8).
"""

import mimetypes
import uuid

import boto3
from botocore.exceptions import ClientError

from app.foundation.config import get_settings

settings = get_settings()

ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

# Documentation/news attachments are non-sensitive, admin-authored material,
# so they live in the public bucket too, with PDFs allowed and a larger cap.
ALLOWED_DOCUMENTATION_CONTENT_TYPES = ALLOWED_IMAGE_CONTENT_TYPES | {"application/pdf"}
MAX_DOCUMENTATION_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

# Magic-byte signatures for every accepted content type. The client-sent
# Content-Type is spoofable, so uploads to any bucket are rejected unless
# their first bytes match the declared format. This is a structural check,
# not a malware scan (see security-model.md §Documents).
_MAGIC_BYTE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),  # bytes 8-12 must also be b"WEBP", checked below
}


def _verify_magic_bytes(*, file_bytes: bytes, content_type: str) -> None:
    signatures = _MAGIC_BYTE_SIGNATURES.get(content_type)
    if signatures is None:
        return  # no known signature for this type
    if not any(file_bytes.startswith(sig) for sig in signatures):
        raise UploadValidationError(
            f"Il contenuto del file non corrisponde al tipo dichiarato ({content_type})."
        )
    if content_type == "image/webp" and file_bytes[8:12] != b"WEBP":
        raise UploadValidationError(
            f"Il contenuto del file non corrisponde al tipo dichiarato ({content_type})."
        )


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
    return _client


class UploadValidationError(Exception):
    pass


def ensure_media_bucket() -> None:
    """Idempotently create the public bucket and its anonymous-read policy.
    Runs at API startup, since MinIO does not auto-create buckets."""
    client = _get_client()
    bucket = settings.s3_bucket_media
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)

    policy = f"""{{
        "Version": "2012-10-17",
        "Statement": [
            {{
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": ["arn:aws:s3:::{bucket}/*"]
            }}
        ]
    }}"""
    client.put_bucket_policy(Bucket=bucket, Policy=policy)


def upload_media(*, file_bytes: bytes, content_type: str, key_prefix: str) -> str:
    """Upload to the public bucket under a fresh random key and return the
    public `/media/` URL. Replaced objects are left orphaned; they are small
    enough not to warrant cleanup."""
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise UploadValidationError(f"Unsupported content type: {content_type}")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("File too large (max 5 MB)")
    _verify_magic_bytes(file_bytes=file_bytes, content_type=content_type)

    extension = mimetypes.guess_extension(content_type) or ".bin"
    key = f"{key_prefix}/{uuid.uuid4().hex}{extension}"

    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket_media, Key=key, Body=file_bytes, ContentType=content_type,
    )
    return f"{settings.public_app_base_url}/media/{key}"


def upload_documentation_attachment(
    *, file_bytes: bytes, content_type: str, key_prefix: str, allowed_content_types: set[str] | None = None
) -> str:
    """Like upload_media() but accepts images or PDF with a larger size cap.

    allowed_content_types lets a caller narrow the set (e.g. an image slot
    rejecting PDFs); it defaults to images plus PDF."""
    allowed = allowed_content_types if allowed_content_types is not None else ALLOWED_DOCUMENTATION_CONTENT_TYPES
    if content_type not in allowed:
        raise UploadValidationError(f"Unsupported content type: {content_type}")
    if len(file_bytes) > MAX_DOCUMENTATION_UPLOAD_BYTES:
        raise UploadValidationError("File too large (max 20 MB)")
    _verify_magic_bytes(file_bytes=file_bytes, content_type=content_type)

    extension = mimetypes.guess_extension(content_type) or ".bin"
    key = f"{key_prefix}/{uuid.uuid4().hex}{extension}"

    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket_media, Key=key, Body=file_bytes, ContentType=content_type,
    )
    return f"{settings.public_app_base_url}/media/{key}"


def ensure_documents_bucket() -> None:
    """Idempotently create the private documents bucket. Deliberately sets no
    policy: MinIO buckets are private until a policy grants access."""
    client = _get_client()
    bucket = settings.s3_bucket_documents
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def upload_document(*, file_bytes: bytes, content_type: str, key_prefix: str) -> str:
    """Upload to the private bucket and return the storage key, never a URL.
    Callers store the key and use generate_presigned_document_url() on demand."""
    from app.modules.documents.models import ALLOWED_DOCUMENT_CONTENT_TYPES, MAX_DOCUMENT_BYTES

    if content_type not in ALLOWED_DOCUMENT_CONTENT_TYPES:
        raise UploadValidationError(f"Unsupported content type: {content_type}")
    if len(file_bytes) > MAX_DOCUMENT_BYTES:
        raise UploadValidationError("File too large (max 15 MB)")
    _verify_magic_bytes(file_bytes=file_bytes, content_type=content_type)

    extension = mimetypes.guess_extension(content_type) or ".bin"
    key = f"{key_prefix}/{uuid.uuid4().hex}{extension}"

    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket_documents, Key=key, Body=file_bytes, ContentType=content_type,
    )
    return key


def download_document(*, storage_key: str) -> bytes:
    """Read a private object server-side, without a presigned URL.

    For content that never reaches a browser (e.g. packed into a zip or sent
    to an external service from this process). Authorization is the
    caller's responsibility."""
    client = _get_client()
    response = client.get_object(Bucket=settings.s3_bucket_documents, Key=storage_key)
    return response["Body"].read()


def generate_presigned_document_url(*, storage_key: str, expires_in_seconds: int = 300) -> str:
    """Signed URL for one private object, valid for `expires_in_seconds`.

    The signature is computed against the internal endpoint (minio:9000),
    and nginx forwards with that Host header, so only the scheme and host
    are rewritten to the public domain; path and query stay untouched."""
    client = _get_client()
    internal_url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_documents, "Key": storage_key},
        ExpiresIn=expires_in_seconds,
    )
    return internal_url.replace(settings.s3_endpoint_url, settings.public_app_base_url, 1)
