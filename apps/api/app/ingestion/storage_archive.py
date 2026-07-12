import boto3
from botocore.config import Config
from app.core.config import config

# Module-level singleton — built once on import, reused for every upload call.
# Avoids the overhead of creating a new boto3 client per font weight/image/zip.
_r2_client = None

def get_r2_client():
    global _r2_client
    if _r2_client is None:
        _r2_client = boto3.client(
            service_name="s3",
            endpoint_url=f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=config.R2_ACCESS_KEY_ID,
            aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )
    return _r2_client

def upload_to_r2(data: bytes, key: str, content_type: str, cache_control: str) -> str:
    """Uploads an object and returns its public URL."""
    client = get_r2_client()
    client.put_object(
        Bucket=config.R2_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl=cache_control
    )
    # R2_PUBLIC_BASE_URL should not end with a slash
    return f"{config.R2_PUBLIC_BASE_URL}/{key}"

def delete_r2_objects(keys: list[str]) -> int:
    """Delete known object keys from the configured bucket."""
    unique_keys = sorted(set(key for key in keys if key))
    if not unique_keys:
        return 0
    client = get_r2_client()
    for start in range(0, len(unique_keys), 1000):
        client.delete_objects(
            Bucket=config.R2_BUCKET_NAME,
            Delete={"Objects": [{"Key": key} for key in unique_keys[start:start + 1000]]},
        )
    return len(unique_keys)

def generate_presigned_snapshot_url(key: str, expiration: int = 300) -> str:
    """Generates a short-lived URL for the CF Pages deploy hook."""
    client = get_r2_client()
    url = client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": config.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expiration
    )
    return url
