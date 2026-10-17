"""Local administration CLI (owner database connection, never exposed over HTTP).

    python -m backend.app.cli create-runtime-login   # LOGIN role in bazi_runtime
    python -m backend.app.cli bootstrap-admin --email admin@example.test
    python -m backend.app.cli export-openapi          # contracts/openapi.json snapshot

Passwords come from an environment variable or an interactive prompt, never
from argv (shell history, process lists).
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, pool, text

from .auth.passwords import validate_new_password
from .auth.service import create_user
from .core.config import ConfigError, load_settings

BOOTSTRAP_PASSWORD_ENV = 'BAZI_BOOTSTRAP_PASSWORD'


def _password(prompt_env: str) -> str:
    value = os.environ.get(prompt_env)
    if value:
        return value
    first = getpass.getpass('Password: ')
    if first != getpass.getpass('Repeat password: '):
        raise SystemExit('Passwords do not match')
    return first


def bootstrap_admin(email: str) -> int:
    settings = load_settings()
    password = _password(BOOTSTRAP_PASSWORD_ENV)
    try:
        validate_new_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.begin() as conn:
        # One-time: refuse once any admin exists, so this cannot mint extra admins later.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bazi.users.admins'))"))
        if conn.execute(text("SELECT EXISTS (SELECT 1 FROM users WHERE role = 'admin')")).scalar():
            print('An admin already exists; use the admin UI/API to manage users.',
                  file=sys.stderr)
            return 1
        user = create_user(conn, email.strip().lower(), password, 'admin')
    print(f'Created admin {user["email"]} ({user["id"]})')
    return 0


def create_runtime_login() -> int:
    settings = load_settings()
    if not settings.postgres_app_user or not settings.postgres_app_password:
        raise SystemExit('Set POSTGRES_APP_USER and POSTGRES_APP_PASSWORD first')
    if settings.postgres_app_user == settings.postgres_user:
        raise SystemExit('POSTGRES_APP_USER must differ from the owner POSTGRES_USER')
    owner = settings.database_url
    with psycopg.connect(host=owner.host, port=owner.port, dbname=owner.database,
                         user=owner.username, password=owner.password, autocommit=True) as conn:
        role = sql.Identifier(settings.postgres_app_user)
        password = sql.Literal(settings.postgres_app_password.get_secret_value())
        exists = conn.execute('SELECT 1 FROM pg_roles WHERE rolname = %s',
                              (settings.postgres_app_user,)).fetchone()
        verb = sql.SQL('ALTER') if exists else sql.SQL('CREATE')
        conn.execute(sql.SQL('{} ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE'
                             ' PASSWORD {}').format(verb, role, password))
        conn.execute(sql.SQL('GRANT bazi_runtime TO {}').format(role))
        conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}')
                     .format(sql.Identifier(owner.database), role))
    print(f'Runtime login {settings.postgres_app_user} is ready (member of bazi_runtime)')
    return 0


OPENAPI_PATH = Path(__file__).resolve().parents[2] / 'contracts' / 'openapi.json'


def openapi_document() -> dict:
    """The contract from default settings only, so the snapshot never depends on .env."""
    from unittest.mock import patch

    from .main import create_app
    with patch.dict(os.environ, {}, clear=True):
        settings = load_settings(_env_file=None)
    return create_app(settings).openapi()


def export_openapi() -> int:
    OPENAPI_PATH.parent.mkdir(exist_ok=True)
    text_ = json.dumps(openapi_document(), indent=2, ensure_ascii=False, sort_keys=True) + '\n'
    OPENAPI_PATH.write_text(text_, encoding='utf-8', newline='\n')
    print(f'Wrote {OPENAPI_PATH}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m backend.app.cli')
    commands = parser.add_subparsers(dest='command', required=True)
    admin = commands.add_parser('bootstrap-admin', help='create the first admin account')
    admin.add_argument('--email', required=True)
    commands.add_parser('create-runtime-login', help='create/update the API database login')
    commands.add_parser('export-openapi', help='write contracts/openapi.json')
    args = parser.parse_args(argv)
    try:
        if args.command == 'bootstrap-admin':
            return bootstrap_admin(args.email)
        if args.command == 'export-openapi':
            return export_openapi()
        return create_runtime_login()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    raise SystemExit(main())
