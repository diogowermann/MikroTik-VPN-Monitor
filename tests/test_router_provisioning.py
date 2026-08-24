from sqlalchemy import select

from app.models import Router, RouterCredential, Source
from app.security import hash_router_secret
from app.services.routers import add_source, register_router, rotate_router_secret


def test_register_router_persists_only_secret_hash(session_factory):
    with session_factory() as db:
        result = register_router(
            db,
            name="router-01",
            source_name="primary-ovpn",
            services=["ovpn"],
            profiles=["example-ovpn-profile"],
            interfaces=[],
        )

        router = db.get(Router, result.router_id)
        source = db.scalar(
            select(Source).where(
                Source.router_id == result.router_id,
                Source.name == "primary-ovpn",
            )
        )
        credential = db.scalar(
            select(RouterCredential).where(RouterCredential.router_id == result.router_id)
        )

        assert router is not None and router.name == "router-01"
        assert source is not None and source.services == ["ovpn"]
        assert source.profiles == ["example-ovpn-profile"]
        assert credential is not None
        assert credential.token_hash == hash_router_secret(result.secret)
        assert credential.token_hash != result.secret


def test_add_source_can_stage_additional_profile_disabled(session_factory):
    with session_factory() as db:
        registered = register_router(db, name="router-01")
        source = add_source(
            db,
            router_id=registered.router_id,
            name="secondary-ovpn",
            services=["ovpn"],
            profiles=["example-restricted-profile"],
            interfaces=["example-interface-selector"],
            enabled=False,
        )

        assert source.name == "secondary-ovpn"
        assert source.services == ["ovpn"]
        assert source.profiles == ["example-restricted-profile"]
        assert source.interfaces == ["example-interface-selector"]
        assert source.enabled is False


def test_rotate_router_secret_revokes_previous_credential(session_factory):
    with session_factory() as db:
        registered = register_router(db, name="router-01")
        old_hash = hash_router_secret(registered.secret)

        new_secret = rotate_router_secret(db, router_id=registered.router_id)
        new_hash = hash_router_secret(new_secret)
        credentials = db.scalars(
            select(RouterCredential).where(
                RouterCredential.router_id == registered.router_id
            )
        ).all()

        old_credential = next(item for item in credentials if item.token_hash == old_hash)
        new_credential = next(item for item in credentials if item.token_hash == new_hash)

        assert new_secret != registered.secret
        assert len(credentials) == 2
        assert old_credential.revoked_at is not None
        assert new_credential.revoked_at is None
