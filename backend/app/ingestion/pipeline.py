"""Ordered stage handlers of the default pipeline (extended by T012–T016)."""
from __future__ import annotations

from ..core.config import Settings
from .pdf_stages import ExtractPdfStage, ValidatePdfStage
from .worker import StageHandler


def handlers_for(settings: Settings) -> list[StageHandler]:
    # PDF stages return no units for DOCX sources; DOCX stages arrive with T013.
    return [ValidatePdfStage(), ExtractPdfStage()]
