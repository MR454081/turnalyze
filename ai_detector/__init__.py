"""
Turnalyze AI Detector — DeBERTa-v3-base prototype package.
"""
from .deberta_detector import AIDetector, get_detector
from .chunker import chunk_text, extract_sentences
from .calibrator import LogisticCalibrator, fit_platt_scaling
from .scoring import aggregate_chunk_scores

__all__ = [
    "AIDetector",
    "get_detector",
    "chunk_text",
    "extract_sentences",
    "LogisticCalibrator",
    "fit_platt_scaling",
    "aggregate_chunk_scores",
]
