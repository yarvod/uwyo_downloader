from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config(db_url: str) -> Config:
    config = Config()
    here = Path(__file__).parent
    config.set_main_option("script_location", str(here / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("timezone", "UTC")
    return config


def run_migrations(db_url: str) -> None:
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
