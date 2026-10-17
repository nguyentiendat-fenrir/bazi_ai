"""Ordered stage handlers of the default pipeline (extended by T013–T016)."""
from __future__ import annotations

from ..core.config import Settings
from .ocr_stage import OcrStage
from .pdf_stages import ExtractPdfStage, ValidatePdfStage
from .worker import StageHandler


def handlers_for(settings: Settings) -> list[StageHandler]:
    # PDF stages return no units for DOCX sources; DOCX stages arrive with T013.
    return [ValidatePdfStage(), ExtractPdfStage(), OcrStage()]
