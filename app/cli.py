"""CLI di amministrazione: `python -m app.cli <comando>`."""

import argparse
import getpass
from datetime import UTC, datetime

from app.models.data_source import DataSource
from app.models.service import Service
from app.models.session import get_session_factory
from app.services.bootstrap import ensure_owner, seed_reference_data


def main() -> None:
    parser = argparse.ArgumentParser(prog="watchly")
    sub = parser.add_subparsers(dest="command", required=True)

    owner = sub.add_parser("create-owner", help="crea l'utente proprietario")
    owner.add_argument("--email", required=True)

    validate = sub.add_parser(
        "validate-source",
        help="marca una fonte come validata per la disponibilità IT per episodio",
    )
    validate.add_argument("source_id")
    validate.add_argument("--revoke", action="store_true")

    service = sub.add_parser("add-service", help="registra una piattaforma di streaming")
    service.add_argument("service_id")
    service.add_argument("name")

    args = parser.parse_args()
    with get_session_factory()() as db:
        seed_reference_data(db)
        if args.command == "create-owner":
            ensure_owner(db, args.email, getpass.getpass("Password: "))
        elif args.command == "validate-source":
            source = db.get(DataSource, args.source_id)
            if source is None:
                raise SystemExit("Fonte sconosciuta")
            source.italy_episode_availability_validated = not args.revoke
            source.validated_at = None if args.revoke else datetime.now(UTC)
            db.commit()
        elif args.command == "add-service":
            if db.get(Service, args.service_id) is None:
                db.add(Service(id=args.service_id, name=args.name, country_scope="IT"))
                db.commit()


if __name__ == "__main__":
    main()
