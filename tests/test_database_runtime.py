from sqlalchemy import create_engine

import app.database  # noqa: F401  # registers SQLite Engine connect hooks


def test_sqlite_file_database_uses_production_pragmas(tmp_path):
    database_path = tmp_path / "runtime.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    with engine.connect() as connection:
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        synchronous = connection.exec_driver_sql("PRAGMA synchronous").scalar_one()

    engine.dispose()

    assert foreign_keys == 1
    assert busy_timeout == 5000
    assert str(journal_mode).lower() == "wal"
    assert synchronous == 1  # NORMAL
