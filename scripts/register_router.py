import argparse

from app.database import get_session_factory
from app.services.routers import register_router


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register one RouterOS device and issue its one-time ingestion secret."
    )
    parser.add_argument("--name", required=True, help="Human-readable router name")
    parser.add_argument(
        "--source-name",
        default="primary-ovpn",
        help="Stable source identifier sent by RouterOS hooks",
    )
    parser.add_argument(
        "--service",
        action="append",
        dest="services",
        help="Allowed PPP service; may be repeated (default: ovpn)",
    )
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        default=[],
        help="PPP profile associated with this source; may be repeated",
    )
    parser.add_argument(
        "--interface",
        action="append",
        dest="interfaces",
        default=[],
        help="Interface selector associated with this source; may be repeated",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_factory = get_session_factory()
    with session_factory() as db:
        result = register_router(
            db,
            name=args.name,
            source_name=args.source_name,
            services=args.services or ["ovpn"],
            profiles=args.profiles,
            interfaces=args.interfaces,
        )

    print(f"router_id={result.router_id}")
    print(f"source_id={result.source_name}")
    print(f"router_secret={result.secret}")
    print("Store the router secret securely; plaintext cannot be recovered later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
