from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Router, RouterCredential, Source, VPNEvent, VPNSession
from app.security import hash_router_secret


def test_domain_models_persist_router_source_event_and_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    secret = "example-high-entropy-router-secret"
    token_hash = hash_router_secret(secret)

    with Session(engine) as db:
        router = Router(name="router-01")
        db.add(router)
        db.flush()

        source = Source(
            router_id=router.id,
            name="primary-ovpn",
            services=["ovpn"],
            profiles=["example-ovpn-profile"],
            interfaces=[],
        )
        credential = RouterCredential(router_id=router.id, token_hash=token_hash)
        db.add_all([source, credential])
        db.flush()

        event = VPNEvent(
            router_id=router.id,
            source_id=source.id,
            external_event_id="example-event-0001",
            event_type="CONNECT",
            username="vpn-user",
            service="ovpn",
            caller_id="203.0.113.10",
            remote_address="10.10.0.20",
            occurred_at=datetime(2026, 8, 24, 12, 0, 0),
        )
        session = VPNSession(
            router_id=router.id,
            source_id=source.id,
            router_session_id="example-router-session",
            username="vpn-user",
            service="ovpn",
            state="ACTIVE",
            vpn_address="10.10.0.20",
            connected_at=datetime(2026, 8, 24, 12, 0, 0),
        )
        db.add_all([event, session])
        db.commit()

        stored_source = db.scalar(select(Source).where(Source.name == "primary-ovpn"))
        stored_event = db.scalar(
            select(VPNEvent).where(VPNEvent.external_event_id == "example-event-0001")
        )
        stored_session = db.scalar(select(VPNSession).where(VPNSession.state == "ACTIVE"))
        stored_credential = db.scalar(select(RouterCredential))

        assert stored_source is not None
        assert stored_source.services == ["ovpn"]
        assert stored_source.profiles == ["example-ovpn-profile"]
        assert stored_event is not None and stored_event.username == "vpn-user"
        assert stored_session is not None and stored_session.vpn_address == "10.10.0.20"
        assert stored_credential is not None
        assert stored_credential.token_hash == token_hash
        assert stored_credential.token_hash != secret
        assert len(stored_credential.token_hash) == 64


def test_hash_router_secret_rejects_empty_value():
    with pytest.raises(ValueError, match="router secret must not be empty"):
        hash_router_secret("")
