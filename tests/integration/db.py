"""Throwaway PostgreSQL databases for schema tests.

``BAZI_TEST_DATABASE_URL`` is libpq conninfo for a server where the user may
create databases, e.g. the dev override of infra/compose.dev.yaml:
    host=127.0.0.1 port=55432 dbname=postgres user=bazi password=<POSTGRES_PASSWORD>
Unset → callers skip; a skip is not a pass.
"""
import hashlib
import os
from pathlib import Path
import unittest
import uuid

import psycopg
from psycopg import sql
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, pool

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get('BAZI_TEST_DATABASE_URL')
ALEMBIC_INI = ROOT / 'backend' / 'alembic.ini'


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def require_database() -> None:
    if not ADMIN_URL:
        raise unittest.SkipTest('BAZI_TEST_DATABASE_URL is not set; schema tests need PostgreSQL')


def database_url(name: str) -> str:
    return psycopg.conninfo.make_conninfo(ADMIN_URL, dbname=name)


def create_database() -> str:
    name = f'bazi_test_{uuid.uuid4().hex[:12]}'
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    return name


def drop_database(name: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)')
                      .format(sql.Identifier(name)))


def alembic(name: str, action: str, target: str) -> None:
    config = Config(str(ALEMBIC_INI))
    engine = create_engine('postgresql+psycopg://', poolclass=pool.NullPool,
                           creator=lambda: psycopg.connect(database_url(name)))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        getattr(command, action)(config, target)
    engine.dispose()


def migrated_database(target: str = 'head') -> str:
    """Create a database at ``target``; drops it again if the migration fails."""
    require_database()
    name = create_database()
    try:
        alembic(name, 'upgrade', target)
    except BaseException:
        drop_database(name)
        raise
    return name


def create_runtime_login(dbname: str) -> tuple[str, str]:
    """A throwaway LOGIN role in bazi_runtime (cluster-wide); returns (role, conninfo)."""
    role = f'bazi_rt_{uuid.uuid4().hex[:10]}'
    password = uuid.uuid4().hex
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}')
                      .format(sql.Identifier(role), sql.Literal(password)))
        admin.execute(sql.SQL('GRANT bazi_runtime TO {}').format(sql.Identifier(role)))
    info = psycopg.conninfo.conninfo_to_dict(ADMIN_URL)
    info.update(dbname=dbname, user=role, password=password)
    return role, psycopg.conninfo.make_conninfo(**info)


def drop_role(role: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))


def engine_for(conninfo: str):
    # A small pool like production (core.db.make_engine): a worker run opens thousands of
    # short transactions, and one TCP connection each exhausts Windows ephemeral ports.
    # Test databases are dropped WITH (FORCE), so pooled connections never block cleanup.
    return create_engine('postgresql+psycopg://', poolclass=pool.QueuePool, pool_size=2,
                         max_overflow=8, pool_pre_ping=True,
                         creator=lambda: psycopg.connect(conninfo))
