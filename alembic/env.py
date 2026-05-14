import os
import sys
from pathlib import Path

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(BASE_DIR))

config = context.config


def _load_database_url() -> str:
    env_path = BASE_DIR / "app" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            if key.strip() == "DATABASE_URL":
                return value.strip().strip("\"'")
    return os.environ["DATABASE_URL"]


config.set_main_option("sqlalchemy.url", _load_database_url())
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.models import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
