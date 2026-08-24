import hashlib


def hash_router_secret(secret: str) -> str:
    """Hash a high-entropy router bearer secret for persistence."""
    if not secret:
        raise ValueError("router secret must not be empty")
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()
