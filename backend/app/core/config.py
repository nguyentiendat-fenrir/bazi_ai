"""Typed runtime configuration loaded from environment and the ignored .env file.

Secrets stay ``SecretStr`` so they never appear in repr, logs or error messages.
Validation errors are re-raised as ``ConfigError`` listing field names and rules
only: pydantic's own message would echo the rejected input value.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

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
    # Runtime login (member of bazi_runtime, subject to RLS). Migrations and the
    # bootstrap CLI use postgres_user; the API must not run as that owner role.
    postgres_app_user: str | None = None
    postgres_app_password: SecretStr | None = None
    redis_url: str = 'redis://redis:6379/0'

    storage_backend: Literal['local', 's3'] = 'local'
    # Containers set STORAGE_ROOT=/data/objects (volume); the dev default stays git-ignored.
    storage_root: str = '.artifacts/objects'
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str = 'us-east-1'
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    max_upload_bytes: int = Field(250 * 1024 * 1024, ge=1)

    session_ttl_hours: int = Field(12, ge=1, le=24 * 30)
    # Origins allowed to send cookie-authenticated unsafe requests (CSRF defence).
    allowed_origins: list[str] = ['http://127.0.0.1:8000', 'http://localhost:8000',
                                  'http://127.0.0.1:3000', 'http://localhost:3000']
    login_max_failures: int = Field(5, ge=1)
    login_window_seconds: int = Field(900, ge=1)

    session_signing_key: SecretStr | None = None
    field_encryption_key: SecretStr | None = None
    # Encrypts backup archives (T052); without it backups are written in clear and must sit
    # on encrypted storage. Kept apart from the field key so either can rotate alone.
    backup_encryption_key: SecretStr | None = None

    llm_provider: Literal['openai_compatible'] = 'openai_compatible'
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    embedding_model: str | None = None

    # RAG pilot (backend/app/rag). Weights apply to min-max normalised scores per query.
    rag_dense_weight: float = Field(0.8, ge=0, le=1)
    rag_sparse_weight: float = Field(0.2, ge=0, le=1)
    rag_dense_candidates: int = Field(50, ge=1, le=500)
    rag_sparse_candidates: int = Field(50, ge=1, le=500)
    rag_rerank_depth: int = Field(10, ge=0, le=50)        # 0 turns the reranker off
    rag_rerank_chars: int = Field(600, ge=100, le=4000)   # child text sent per candidate
    rag_rerank_timeout: float = Field(20.0, gt=0)
    rag_dedupe_bits: int = Field(3, ge=0, le=16)          # simhash Hamming distance
    rag_context_tokens: int = Field(9000, ge=500, le=14000)
    rag_answer_tokens: int = Field(1500, ge=100, le=4000)
    rag_thinking: bool = False
    rag_temperature: float = Field(0.2, ge=0, le=1.5)
    rag_llm_timeout: float = Field(180.0, gt=0)
    rag_cpu_threads: int = Field(16, ge=1, le=64)
    # Where the Jina embedder/reranker run (rag/models.py reads RAG_DEVICE/RAG_DTYPE itself;
    # declared here so a typo fails at startup). Empty dtype: bf16 on the GPU, fp32 on the CPU.
    rag_device: str = Field('cpu', pattern=r'^(cpu|cuda(:\d+)?)$')
    rag_dtype: Literal['', 'fp32', 'bf16', 'fp16'] = ''
    rag_embedding_model: str = 'jinaai/jina-embeddings-v5-text-small'
    rag_embedding_revision: str = 'dd76d535f5447ca3897a9c893fb1e612ead98192'
    rag_reranker_model: str = 'jinaai/jina-reranker-v3.5'
    rag_reranker_revision: str = 'e8a93f33f0b22108f8c2364f8484ce3422552fbc'
    rag_summary_concurrency: int = Field(4, ge=1, le=16)
    rag_load_models: bool = True                          # API loads the CPU models at startup
    ocr_model: str = 'VietAlphaLabs/SenOCR-Vi'
    ocr_revision: str = 'main'
    ocr_precision: Literal['bf16', 'fp32'] = 'bf16'
    ocr_dpi: int = Field(200, ge=100, le=400)
    # OCR on another machine (ingestion/ocr_remote.py): the worker sends rendered pages there.
    ocr_remote_url: str | None = None
    ocr_remote_token: SecretStr | None = None
    # Shared judging password (argon2 hash, never the password) and its cookie lifetime.
    judge_password_hash: SecretStr | None = None
    judge_session_hours: int = Field(8, ge=1, le=72)
    # MCP server of the RAG (backend/app/mcpserver): off unless a token is set. Tools search as
    # MCP_USER_EMAIL, so they see exactly that account's library.
    mcp_token: SecretStr | None = None
    mcp_user_email: str | None = None
    mcp_answer_rounds: int = Field(7, ge=1, le=7)
    mcp_time_budget: float | None = Field(None, gt=0)
    # Sub-path the UI and API are published under ("/bazi"), for cookie paths the browser sees.
    public_base_path: str = Field('', pattern=r'^(/[A-Za-z0-9._-]+)*$')

    @field_validator('postgres_password', 'postgres_app_user', 'postgres_app_password',
                     'session_signing_key', 'field_encryption_key', 'backup_encryption_key',
                     'llm_api_key', 'llm_base_url', 'judge_password_hash',
                     'llm_model', 'embedding_model', 's3_endpoint_url', 's3_bucket',
                     's3_access_key_id', 's3_secret_access_key', 'mcp_token', 'mcp_user_email',
                     'mcp_time_budget', 'ocr_remote_url', 'ocr_remote_token', mode='before')
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
    def s3_complete(self) -> 'Settings':
        if self.storage_backend == 's3' and not self.s3_bucket:
            raise ValueError('storage_backend s3 requires s3_bucket')
        return self

    @model_validator(mode='after')
    def mcp_complete(self) -> 'Settings':
        if self.mcp_token is None:
            return self
        if len(self.mcp_token.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f'mcp_token must be at least {MIN_SECRET_LENGTH} characters')
        if not self.mcp_user_email:
            raise ValueError('mcp_token requires mcp_user_email (the account the tools search as)')
        return self

    @model_validator(mode='after')
    def ocr_remote_complete(self) -> 'Settings':
        if self.ocr_remote_url is None:
            return self
        if not self.ocr_remote_url.startswith(('http://', 'https://')):
            raise ValueError('ocr_remote_url must be an http(s) URL')
        token = self.ocr_remote_token.get_secret_value() if self.ocr_remote_token else ''
        if len(token) < MIN_SECRET_LENGTH:
            raise ValueError(f'ocr_remote_url requires ocr_remote_token of at least {MIN_SECRET_LENGTH} characters')
        return self

    @model_validator(mode='after')
    def production_secrets(self) -> 'Settings':
        if self.app_env != 'production':
            return self
        required = {'postgres_password': self.postgres_password,
                    'postgres_app_password': self.postgres_app_password,
                    'session_signing_key': self.session_signing_key,
                    'field_encryption_key': self.field_encryption_key}
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f'production requires {", ".join(missing)}')
        if not self.postgres_app_user or self.postgres_app_user == self.postgres_user:
            raise ValueError('production requires postgres_app_user distinct from postgres_user')
        short = [name for name, value in required.items()
                 if name not in ('postgres_password', 'postgres_app_password')
                 and len(value.get_secret_value()) < MIN_SECRET_LENGTH]
        if short:
            raise ValueError(f'{", ".join(short)} must be at least {MIN_SECRET_LENGTH} characters')
        return self

    def _url(self, user: str, password: SecretStr | None) -> URL:
        # URL objects escape the password and hide it in str()/repr().
        return URL.create('postgresql+psycopg', username=user,
                          password=password.get_secret_value() if password else None,
                          host=self.postgres_host, port=self.postgres_port,
                          database=self.postgres_db)

    @property
    def database_url(self) -> URL:
        """Owner/migration connection: migrations, bootstrap CLI, role setup."""
        return self._url(self.postgres_user, self.postgres_password)

    @property
    def runtime_database_url(self) -> URL:
        """API/worker connection; falls back to the owner only outside production."""
        if self.postgres_app_user:
            return self._url(self.postgres_app_user, self.postgres_app_password)
        return self.database_url

    @property
    def cookie_secure(self) -> bool:
        return self.app_env == 'production'

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)

    def secret_values(self) -> list[str]:
        """Configured secret strings, used by the log redactor."""
        secrets = (self.postgres_password, self.postgres_app_password, self.session_signing_key,
                   self.field_encryption_key, self.backup_encryption_key, self.llm_api_key,
                   self.s3_secret_access_key, self.judge_password_hash, self.mcp_token,
                   self.ocr_remote_token)
        return [s.get_secret_value() for s in secrets if s is not None]

    @property
    def mcp_enabled(self) -> bool:
        return bool(self.mcp_token and self.mcp_user_email)


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
