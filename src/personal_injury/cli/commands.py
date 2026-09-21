from __future__ import annotations

import argparse
import json
from pathlib import Path

from personal_injury.application.services import import_legacy_case
from personal_injury.infrastructure.collector_import import import_collector_status
from personal_injury.infrastructure.database import (
    UserModel,
    create_engine_for_url,
    create_session_factory,
)


def import_legacy_command() -> None:
    parser = argparse.ArgumentParser(description="Import a legacy JSON case into the local database")
    parser.add_argument("--file", default="data/example_case.json")
    parser.add_argument("--username", required=True, help="Existing administrator or lawyer username")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    from personal_injury.infrastructure.settings import get_settings

    database_url = args.database_url or get_settings().database_url
    engine = create_engine_for_url(database_url)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        actor = session.query(UserModel).filter(UserModel.username == args.username).first()
        if not actor:
            raise SystemExit(f"User not found: {args.username}")
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        case = import_legacy_case(session, payload, actor)
        print(case.id)


def import_collector_command() -> None:
    parser = argparse.ArgumentParser(description="Import collector status as pending statistical standards")
    parser.add_argument("--file", default="data_collection_status.json")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    from personal_injury.infrastructure.settings import get_settings

    database_url = args.database_url or get_settings().database_url
    engine = create_engine_for_url(database_url)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        print(import_collector_status(session, args.file))


if __name__ == "__main__":
    import_legacy_command()
