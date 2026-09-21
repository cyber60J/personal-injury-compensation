from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


class MigrationTests(unittest.TestCase):
    def test_fresh_schema_upgrades_and_matches_metadata(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "migration.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            previous_url = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = database_url
            try:
                config = Config(str(root / "alembic.ini"))
                config.set_main_option("script_location", str(root / "alembic"))
                command.upgrade(config, "head")
                command.check(config)

                engine = create_engine(database_url)
                tables = set(inspect(engine).get_table_names())
                self.assertIn("calculation_snapshots", tables)
                self.assertIn("review_tasks", tables)
                snapshot_columns = {
                    item["name"] for item in inspect(engine).get_columns("calculation_snapshots")
                }
                self.assertIn("algorithm_version", snapshot_columns)
                self.assertIn("standards_snapshot", snapshot_columns)
                engine.dispose()

                command.downgrade(config, "base")
                engine = create_engine(database_url)
                remaining = set(inspect(engine).get_table_names())
                self.assertNotIn("users", remaining)
                self.assertNotIn("cases", remaining)
                engine.dispose()
            finally:
                if previous_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = previous_url


if __name__ == "__main__":
    unittest.main()
