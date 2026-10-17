"""Typed runtime configuration loaded from environment and the ignored .env file.

Secrets stay ``SecretStr`` so they never appear in repr, logs or error messages.
Validation errors are re-raised as ``ConfigError`` listing field names and rules
only: pydantic's own message would echo the rejected input value.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """Startup configuration is invalid; the message never contains values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8',
                                      extra='ignore', frozen=True)

    app_env: Literal['dev', 'test', 'production'] = 'dev'
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = 'INFO'

    postgres_host: str = 'postgres'
    postgres_port: int = Field(5432, ge=1, le=65535)
    postgres_db: str = 'bazi'
    postgres_user: str = 'bazi'
    postgres_password: SecretStr | None = None
    redis_url: str = 'redis://redis:6379/0'

    session_signing_key: SecretStr | None = None
    field_encryption_key: SecretStr | None = None

    llm_provider: Literal['openai_compatible'] = 'openai_compatible'
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    embedding_model: str | None = None

    @field_validator('postgres_password', 'session_signing_key', 'field_encryption_key',
                     'llm_api_key', 'llm_base_url', 'llm_model', 'embedding_model',
                     mode='before')
    @classmethod
    def empty_is_unset(cls, value):
        # .env.example ships blank placeholders; treat them as "not configured".
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator('llm_base_url')
    @classmethod
    def base_url_is_v1(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(('http://', 'https://')) or not value.rstrip('/').endswith('/v1'):
            raise ValueError('must be an http(s) URL ending in /v1')
        return value.rstrip('/')

    @model_validator(mode='after')
    def production_secrets(self) -> 'Settings':
        if self.app_env != 'production':
            return self
        required = {'postgres_password': self.postgres_password,
                    'session_signing_key': self.session_signing_key,
                    'field_encryption_key': self.field_encryption_key}
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f'production requires {", ".join(missing)}')
        short = [name for name, value in required.items()
                 if name != 'postgres_password'
                 and len(value.get_secret_value()) < MIN_SECRET_LENGTH]
        if short:
            raise ValueError(f'{", ".join(short)} must be at least {MIN_SECRET_LENGTH} characters')
        return self

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)

    def secret_values(self) -> list[str]:
        """Configured secret strings, used by the log redactor."""
        secrets = (self.postgres_password, self.session_signing_key,
                   self.field_encryption_key, self.llm_api_key)
        return [s.get_secret_value() for s in secrets if s is not None]


def load_settings(**overrides) -> Settings:
    """Load settings, failing with field names and rules but no input values."""
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_input=False, include_url=False):
            field = '.'.join(str(part) for part in error['loc']) or 'settings'
            problems.append(f'{field}: {error["msg"]}')
        raise ConfigError('Invalid configuration: ' + '; '.join(problems)) from None
