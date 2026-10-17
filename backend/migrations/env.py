"""Alembic environment. Migrations are hand-written SQL (docs/04 is the contract).

Callers may pass an open connection via ``config.attributes['connection']``
(tests do); otherwise the URL is built from application settings.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from backend.app.core.config import load_settings

config = context.config
if config.config_file_name is not None and not config.attributes.get('connection'):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations_online() -> None:
    connection = config.attributes.get('connection')
    if connection is not None:
        context.configure(connection=connection, transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(load_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit('Offline SQL generation is not supported; run against a database.')
run_migrations_online()
