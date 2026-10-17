"""Ordered stage handlers of the default pipeline (extended by T015-T016)."""
from __future__ import annotations

from ..core.config import Settings
from .docx_stage import DocxExtractStage
from .ocr_stage import OcrStage
from .pdf_stages import ExtractPdfStage, ValidatePdfStage
from .quality import QualityStage
from .structure import StructureStage
from .worker import StageHandler


def handlers_for(settings: Settings) -> list[StageHandler]:
    # Each stage returns no units for sources it does not handle (PDF vs DOCX).
    return [ValidatePdfStage(), ExtractPdfStage(), DocxExtractStage(), OcrStage(),
            StructureStage(), QualityStage()]
