from dataclasses import dataclass
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Router, RouterCredential, Source
from app.security import hash_router_secret
from app.timeutils import utc_now


@dataclass(frozen=True)
class RouterProvisioningResult:
    router_id: str
    source_name: str
    secret: str


def generate_router_secret() -> str:
    """Generate a high-entropy one-time bearer secret for one RouterOS device."""
    return secrets.token_urlsafe(48)


def add_source(
    db: Session,
    *,
    router_id: str,
    name: str,
    services: list[str] | None = None,
    profiles: list[str] | None = None,
    interfaces: list[str] | None = None,
    enabled: bool = True,
) -> Source:
    router = db.get(Router, router_id)
    if router is None:
        raise ValueError("router not found")

    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("source name must not be empty")

    existing = db.scalar(
        select(Source).where(
            Source.router_id == router_id,
            Source.name == normalized_name,
        )
    )
    if existing is not None:
        raise ValueError("source name is already registered for this router")

    source = Source(
        router_id=router_id,
        name=normalized_name,
        services=list(services or ["ovpn"]),
        profiles=list(profiles or []),
        interfaces=list(interfaces or []),
        enabled=enabled,
    )
    db.add(source)
    db.commit()
    return source


def register_router(
    db: Session,
    *,
    name: str,
    source_name: str = "primary-ovpn",
    services: list[str] | None = None,
    profiles: list[str] | None = None,
    interfaces: list[str] | None = None,
) -> RouterProvisioningResult:
    normalized_name = name.strip()
    normalized_source = source_name.strip()
    if not normalized_name:
        raise ValueError("router name must not be empty")
    if not normalized_source:
        raise ValueError("source name must not be empty")

    existing = db.scalar(select(Router).where(Router.name == normalized_name))
    if existing is not None:
        raise ValueError("router name is already registered")

    secret = generate_router_secret()
    router = Router(name=normalized_name)
    db.add(router)
    db.flush()

    source = Source(
        router_id=router.id,
        name=normalized_source,
        services=list(services or ["ovpn"]),
        profiles=list(profiles or []),
        interfaces=list(interfaces or []),
        enabled=True,
    )
    credential = RouterCredential(
        router_id=router.id,
        token_hash=hash_router_secret(secret),
    )
    db.add_all([source, credential])
    db.commit()

    return RouterProvisioningResult(
        router_id=router.id,
        source_name=source.name,
        secret=secret,
    )


def rotate_router_secret(db: Session, *, router_id: str) -> str:
    router = db.get(Router, router_id)
    if router is None:
        raise ValueError("router not found")

    now = utc_now()
    active_credentials = db.scalars(
        select(RouterCredential).where(
            RouterCredential.router_id == router_id,
            RouterCredential.revoked_at.is_(None),
        )
    ).all()
    for credential in active_credentials:
        credential.revoked_at = now

    secret = generate_router_secret()
    db.add(
        RouterCredential(
            router_id=router_id,
            token_hash=hash_router_secret(secret),
        )
    )
    db.commit()
    return secret
