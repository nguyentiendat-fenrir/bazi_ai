"""Structured JSON logs with request correlation and secret redaction.

Redaction is defence in depth: code must still avoid logging book text, birth
data and chat content. Known secret values from settings are masked verbatim;
common credential shapes (key=value, Bearer tokens, URL passwords) by pattern.
"""
from __future__ import annotations

from contextvars import ContextVar
import json
import logging
import re
import sys
import time
import traceback

request_id_var: ContextVar[str | None] = ContextVar('request_id', default=None)

REDACTED = '[REDACTED]'
# Extra record attributes copied into the JSON line; everything else is dropped.
EXTRA_FIELDS = ('event', 'method', 'path', 'status', 'duration_ms', 'error_code', 'exc_type')
_PATTERNS = (
    (re.compile(r'(?i)\b(password|passwd|secret|token|api[_-]?key|signing[_-]?key)'
                r'(["\']?\s*[=:]\s*["\']?)[^\s"\',;&]+'), rf'\1\2{REDACTED}'),
    (re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+'), f'Bearer {REDACTED}'),
    (re.compile(r'(://[^/\s:@]+:)[^@\s/]+@'), rf'\1{REDACTED}@'),
)
_HANDLER_MARK = '_bazi_json_handler'


class Redactor:
    def __init__(self, secrets: list[str] | None = None):
        # Longest first so a secret containing another is masked whole.
        self.secrets = sorted({s for s in secrets or [] if len(s) >= 4}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        for pattern, replacement in _PATTERNS:
            text = pattern.sub(replacement, text)
        return text


class JsonFormatter(logging.Formatter):
    def __init__(self, redactor: Redactor):
        super().__init__()
        self.redact = redactor

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(record.created))
                  + f'.{int(record.msecs):03d}Z',
            'level': record.levelname,
            'logger': record.name,
            'message': self.redact(record.getMessage()),
            'request_id': getattr(record, 'request_id', None) or request_id_var.get(),
        }
        for field in EXTRA_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry['exc_type'] = record.exc_info[0].__name__
            entry['traceback'] = self.redact(frames_only(record.exc_info))
        return json.dumps(entry, ensure_ascii=False, default=str)


def frames_only(exc_info) -> str:
    """Where it failed, not what it said: exception messages can quote user input (a
    duplicate key's value, a bad date), so only the frames and the exception types are
    kept — for the whole chain of causes."""
    parts, seen = [], set()
    current = traceback.TracebackException(*exc_info)
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = getattr(current, 'exc_type_str', None) or current.exc_type.__qualname__
        parts.append(''.join(current.stack.format()) + name)
        current = current.__cause__ or (None if current.__suppress_context__
                                         else current.__context__)
    return '\n-- caused by --\n'.join(reversed(parts))


def configure_logging(level: str, secrets: list[str], stream=None) -> logging.Handler:
    """Install one JSON handler on the root logger; safe to call repeatedly."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter(Redactor(secrets)))
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(level)
    # Our middleware writes the access line with request_id; uvicorn's would duplicate it.
    logging.getLogger('uvicorn.access').disabled = True
    for name in ('uvicorn', 'uvicorn.error'):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    # HTTP client libraries log full URLs (with query strings) at INFO/DEBUG.
    # httpx2/httpcore2 are the renamed forks huggingface_hub 2.x pulls in.
    for name in ('httpx', 'httpcore', 'httpx2', 'httpcore2'):
        logging.getLogger(name).setLevel(logging.WARNING)
    return handler
