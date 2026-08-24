import argparse

from app.database import get_session_factory
from app.services.routers import rotate_router_secret


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rotate the ingestion secret for one registered RouterOS device."
    )
    parser.add_argument("--router-id", required=True, help="Registered router UUID")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_factory = get_session_factory()
    with session_factory() as db:
        secret = rotate_router_secret(db, router_id=args.router_id)

    print(f"router_id={args.router_id}")
    print(f"router_secret={secret}")
    print("Previous active router credentials were revoked immediately.")
    print("Store the new secret securely; plaintext cannot be recovered later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
