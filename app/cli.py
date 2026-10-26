"""CLI di amministrazione: `python -m app.cli <comando>`."""

import argparse
import getpass

from app.main import app
from app.models.session import get_session
from app.services.bootstrap import ensure_owner, seed_reference_data


def _generate_vapid() -> None:
    import base64

    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    vapid = Vapid()
    vapid.generate_keys()
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    print(f"VAPID_PRIVATE_KEY={b64(private)}")
    print(f"VAPID_PUBLIC_KEY={b64(public)}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="watchly")
    sub = parser.add_subparsers(dest="command", required=True)

    owner = sub.add_parser("create-owner", help="crea l'utente proprietario")
    owner.add_argument("--email", required=True)

    sub.add_parser("generate-vapid", help="genera una coppia di chiavi VAPID per il Web Push")

    args = parser.parse_args()
    if args.command == "generate-vapid":
        _generate_vapid()
        return
    with app.app_context():
        session = get_session()
        seed_reference_data(session)
        if args.command == "create-owner":
            ensure_owner(session, args.email, getpass.getpass("Password: "))


if __name__ == "__main__":
    main()
