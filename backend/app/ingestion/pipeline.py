"""Stage handlers per pipeline profile (filled by T011–T016)."""
from __future__ import annotations

from ..core.config import Settings
from .worker import StageHandler


def handlers_for(settings: Settings) -> list[StageHandler]:
    """Ordered stages of the default pipeline; empty until extraction stages exist."""
    return []
