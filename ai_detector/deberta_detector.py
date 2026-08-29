"""
DeBERTa-v3-base AI detector module.

This is the production-facing detector interface.
It loads a fine-tuned checkpoint and produces chunk-level
AI probabilities with optional Platt calibration.

If no fine-tuned checkpoint exists, the detector reports
unavailable status and does NOT produce fake scores.
"""
import os
import time
import logging
from typing import List, Dict, Optional, Tuple

import numpy as np

from .chunker import chunk_text
from .calibrator import LogisticCalibrator, fit_platt_scaling
from .scoring import aggregate_chunk_scores

logger = logging.getLogger(__name__)

# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

MODEL_NAME = "microsoft/deberta-v3-base"

DEFAULT_CHECKPOINT = os.path.join(
    BASE_DIR, "models", "deberta_detector"
)

DEFAULT_CALIBRATOR_PATH = os.path.join(
    DEFAULT_CHECKPOINT, "calibrator.json"
)

MAX_LENGTH = 512
BATCH_SIZE = 8
AI_THRESHOLD = 0.50


# =========================================================
# MODEL LOADING
# =========================================================

class AIDetector:
    """
    Loads a fine-tuned DeBERTa-v3-base checkpoint and runs
    chunk-level AI detection with optional Platt calibration.
    """

    def __init__(
        self,
        checkpoint: str = DEFAULT_CHECKPOINT,
        calibrator_path: str = DEFAULT_CALIBRATOR_PATH,
        device: Optional[str] = None,
        max_length: int = MAX_LENGTH,
        batch_size: int = BATCH_SIZE,
        ai_threshold: float = AI_THRESHOLD,
    ):
        self.checkpoint = checkpoint
        self.calibrator_path = calibrator_path
        self.max_length = max_length
        self.batch_size = batch_size
        self.ai_threshold = ai_threshold

        self._tokenizer = None
        self._model = None
        self._calibrator = None
        self._device = device or self._detect_device()
        self._model_info = {}

    # ---------------------------------------------------------
    # Device detection
    # ---------------------------------------------------------

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    # ---------------------------------------------------------
    # Model status
    # ---------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return True if a fine-tuned checkpoint exists on disk."""
        if not os.path.isdir(self.checkpoint):
            return False
        config_path = os.path.join(self.checkpoint, "config.json")
        model_path = os.path.join(self.checkpoint, "model.safetensors")
        pytorch_path = os.path.join(self.checkpoint, "pytorch_model.bin")
        return os.path.isfile(config_path) and (
            os.path.isfile(model_path) or os.path.isfile(pytorch_path)
        )

    @property
    def device(self) -> str:
        return self._device

    @property
    def model_info(self) -> Dict:
        return dict(self._model_info)

    # ---------------------------------------------------------
    # Model loading
    # ---------------------------------------------------------

    def load(self):
        """Load tokenizer, model, and calibrator."""
        if self._model is not None and self._tokenizer is not None:
            return

        if not self.available:
            raise FileNotFoundError(
                f"Fine-tuned checkpoint not found at: {self.checkpoint}"
            )

        load_start = time.time()

        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
        )
        import torch

        logger.info(
            "Loading DeBERTa detector from %s on device=%s",
            self.checkpoint,
            self._device,
        )

        self._tokenizer = AutoTokenizer.from_pretrained(self.checkpoint)

        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.checkpoint,
            num_labels=2,
        )
        self._model.eval()

        if self._device == "cuda":
            self._model = self._model.cuda()

        # Load label mapping from config
        config_path = os.path.join(self.checkpoint, "config.json")
        if os.path.exists(config_path):
            import json
            with open(config_path, "r") as f:
                config = json.load(f)
            self._model_info = {
                "id2label": config.get("id2label", {"0": "human", "1": "ai"}),
                "label2id": config.get("label2id", {"human": 0, "ai": 1}),
                "model_name": config.get("_name_or_path", MODEL_NAME),
            }

        # Load calibrator if available
        self._calibrator = LogisticCalibrator.load(self.calibrator_path)
        if self._calibrator and self._calibrator.fitted:
            logger.info("Calibrator loaded from %s", self.calibrator_path)
        else:
            logger.info("No calibrated probabilities available; using raw scores.")

        load_time = time.time() - load_start
        logger.info(
            "DeBERTa detector loaded in %.2f seconds. Device: %s",
            load_time,
            self._device,
        )

    # ---------------------------------------------------------
    # Inference
    # ---------------------------------------------------------

    def _run_inference(self, chunks: List[Tuple[str, int, int]]) -> List[Dict]:
        """Run batched inference on chunks."""
        import torch

        texts = [c[0] for c in chunks]
        results: List[Dict] = []

        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i : i + self.batch_size]
            inputs = self._tokenizer(
                batch_texts,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_length,
                padding=True,
            )

            if self._device == "cuda":
                inputs = {k: v.cuda() for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1)

            ai_logits = logits[:, 1].cpu().numpy()

            for j, (chunk_text, tokens, words) in enumerate(chunks[i : i + self.batch_size]):
                human_prob = float(probs[j][0].item())
                ai_prob = float(probs[j][1].item())
                ai_logit = float(ai_logits[j])

                calibrated_ai_prob = ai_prob
                calibrated_human_prob = human_prob
                if self._calibrator is not None and self._calibrator.fitted:
                    calibrated_ai_prob = float(self._calibrator.transform(np.array([ai_logit]))[0])
                    calibrated_human_prob = 1.0 - calibrated_ai_prob

                label = "AI" if ai_prob >= self.ai_threshold else "HUMAN"
                cal_label = "AI" if calibrated_ai_prob >= self.ai_threshold else "HUMAN"

                results.append({
                    "text": chunk_text,
                    "tokens": tokens,
                    "words": words,
                    "human_probability": round(human_prob, 4),
                    "ai_probability": round(ai_prob, 4),
                    "calibrated_human_probability": round(calibrated_human_prob, 4),
                    "calibrated_ai_probability": round(calibrated_ai_prob, 4),
                    "label": label,
                    "calibrated_label": cal_label,
                    "is_ai": ai_prob >= self.ai_threshold,
                })

        return results

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def analyze(self, text: str) -> Dict:
        """
        Analyze text and return structured detection results.

        Returns a dictionary compatible with the Turnalyze pipeline.
        """
        start_time = time.time()

        # Check availability
        if not self.available:
            return {
                "available": False,
                "reason": "Fine-tuned checkpoint not found",
                "model": MODEL_NAME,
                "checkpoint": self.checkpoint,
                "device": self._device,
                "calibrated": False,
            }

        # Load model if needed
        if self._model is None:
            self.load()

        # Clean text (same as existing detector)
        clean_text = self._clean_text(text)
        words = len(clean_text.split())

        if words < 10:
            return {
                "available": True,
                "model": MODEL_NAME,
                "checkpoint": self.checkpoint,
                "device": self._device,
                "calibrated": (
                    self._calibrator is not None
                    and self._calibrator.fitted
                ),
                "ai_score": 0,
                "human_score": 100,
                "words": words,
                "status": "Human",
                "highlight_texts": [],
                "text_content": "",
                "segments": [],
                "chunks_analyzed": 0,
                "raw_avg_prob": 0.0,
                "calibrated_avg_prob": 0.0,
            }

        # Chunk
        chunks = chunk_text(
            self._tokenizer,
            clean_text,
            max_length=self.max_length,
        )

        if not chunks:
            return {
                "available": True,
                "model": MODEL_NAME,
                "checkpoint": self.checkpoint,
                "device": self._device,
                "calibrated": (
                    self._calibrator is not None
                    and self._calibrator.fitted
                ),
                "ai_score": 0,
                "human_score": 100,
                "words": words,
                "status": "Human",
                "highlight_texts": [],
                "text_content": "",
                "segments": [],
                "chunks_analyzed": 0,
                "raw_avg_prob": 0.0,
                "calibrated_avg_prob": 0.0,
            }

        # Inference
        results = self._run_inference(chunks)

        # Aggregate
        ai_score, human_score, meta = aggregate_chunk_scores(
            chunks, results, ai_threshold=self.ai_threshold
        )

        # Status
        if ai_score < 30:
            status = "Human"
        elif ai_score < 70:
            status = "Mixed"
        else:
            status = "AI"

        # Highlights: top chunks by AI probability, limited to 6
        sorted_results = sorted(
            results, key=lambda r: r["ai_probability"], reverse=True
        )
        highlight_texts = [r["text"] for r in sorted_results if r["is_ai"]][:6]

        # Segments for PDF highlighting
        segments = [
            {
                "text": r["text"],
                "ai_probability": r["ai_probability"],
                "calibrated_ai_probability": r["calibrated_ai_probability"],
                "is_ai": r["is_ai"],
            }
            for r in results
        ]

        # Compute calibrated average for metadata
        cal_weighted_sum = 0.0
        cal_total_weight = 0.0
        for (_, _, words), r in zip(chunks, results):
            cal_total_weight += words
            cal_weighted_sum += r["calibrated_ai_probability"] * words
        cal_avg = cal_weighted_sum / cal_total_weight if cal_total_weight > 0 else 0.0

        raw_weighted_sum = 0.0
        raw_total_weight = 0.0
        for (_, _, words), r in zip(chunks, results):
            raw_total_weight += words
            raw_weighted_sum += r["ai_probability"] * words
        raw_avg = raw_weighted_sum / raw_total_weight if raw_total_weight > 0 else 0.0

        inference_time = time.time() - start_time
        logger.info(
            "DeBERTa detector: chunks=%d, raw_avg=%.4f, cal_avg=%.4f, "
            "ai_score=%d, status=%s, time=%.2fs",
            len(chunks),
            raw_avg,
            cal_avg,
            ai_score,
            status,
            inference_time,
        )

        return {
            "available": True,
            "model": MODEL_NAME,
            "checkpoint": self.checkpoint,
            "device": self._device,
            "calibrated": (
                self._calibrator is not None
                and self._calibrator.fitted
            ),
            "ai_score": ai_score,
            "human_score": human_score,
            "ai_percentage": round(ai_score, 4),
            "human_percentage": round(human_score, 4),
            "ai_probability": round(raw_avg, 4),
            "human_probability": round(1.0 - raw_avg, 4),
            "words": words,
            "status": status,
            "highlight_texts": highlight_texts,
            "text_content": "\n".join(highlight_texts),
            "segments": segments,
            "chunks_analyzed": len(chunks),
            "raw_avg_prob": round(raw_avg, 4),
            "calibrated_avg_prob": round(cal_avg, 4),
            "mode": "deberta_prototype",
        }

    @staticmethod
    def _clean_text(raw_text: str) -> str:
        """Clean text using the same logic as the existing detector."""
        import re
        text = raw_text
        ref_match = re.search(
            r"\n\s*(references|bibliography)\s*\n", text, re.IGNORECASE
        )
        if ref_match:
            text = text[: ref_match.start()]
        text = re.sub(r"\r\n", "\n", text)
        text = re.sub(r"\r", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


# =========================================================
# SINGLETON ACCESS
# =========================================================

_detector_instance: Optional["AIDetector"] = None


def get_detector() -> AIDetector:
    """Return a singleton AIDetector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = AIDetector()
    return _detector_instance
