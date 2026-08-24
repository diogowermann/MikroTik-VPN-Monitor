from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_creates_and_drops_domain_schema(tmp_path):
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"routers", "router_credentials", "sources", "vpn_events", "vpn_sessions"} <= tables

    source_columns = {column["name"] for column in inspector.get_columns("sources")}
    assert {"services", "profiles", "interfaces"} <= source_columns

    event_uniques = {
        constraint.get("name") for constraint in inspector.get_unique_constraints("vpn_events")
    }
    assert "uq_vpn_events_router_external" in event_uniques

    command.downgrade(config, "base")
    remaining_tables = set(inspect(engine).get_table_names())
    assert not {"routers", "router_credentials", "sources", "vpn_events", "vpn_sessions"} & remaining_tables
