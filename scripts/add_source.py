import argparse

from app.database import get_session_factory
from app.services.routers import add_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add one configurable monitoring source to a registered RouterOS device."
    )
    parser.add_argument("--router-id", required=True, help="Registered router UUID")
    parser.add_argument("--name", required=True, help="Stable source name")
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
    parser.add_argument(
        "--disabled",
        action="store_true",
        help="Create the source disabled so it can be enabled deliberately later",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_factory = get_session_factory()
    with session_factory() as db:
        source = add_source(
            db,
            router_id=args.router_id,
            name=args.name,
            services=args.services or ["ovpn"],
            profiles=args.profiles,
            interfaces=args.interfaces,
            enabled=not args.disabled,
        )

    print(f"router_id={args.router_id}")
    print(f"source_id={source.name}")
    print(f"enabled={str(source.enabled).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
