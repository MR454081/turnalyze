"""
Tests for the DeBERTa AI detector prototype.

Run with:
    python -m pytest tests/test_ai_detector.py -v
"""
import os
import sys
import json
import tempfile
import pytest
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from ai_detector.chunker import chunk_text, extract_sentences
from ai_detector.calibrator import LogisticCalibrator, fit_platt_scaling
from ai_detector.scoring import aggregate_chunk_scores
from ai_detector import get_detector


# =========================================================
# FIXTURES
# =========================================================

class MockTokenizer:
    """Mock tokenizer for chunker tests."""

    def encode(self, text, add_special_tokens=True):
        words = text.split()
        return list(range(len(words)))

    def decode(self, ids, skip_special_tokens=False):
        return " ".join(["word"] * len(ids))


@pytest.fixture
def mock_tokenizer():
    return MockTokenizer()


@pytest.fixture
def sample_text():
    return (
        "The influence of country of origin on consumer perceptions has been "
        "extensively studied in international marketing literature. This paper "
        "examines how brand origin interacts with country of origin to shape "
        "consumer attitudes and purchase intentions. We conducted an experiment "
        "with 240 participants using a between-subjects design. Results indicate "
        "that brand origin moderates the effect of country of origin on perceived quality. "
        "Specifically, strong brand origins attenuated negative country of origin effects, "
        "while weak brand origins amplified them. " * 5
    )


# =========================================================
# CHUNKER TESTS
# =========================================================

class TestChunker:

    def test_extract_sentences(self):
        text = "First sentence. Second sentence! Third?"
        sentences = extract_sentences(text)
        assert len(sentences) == 3

    def test_chunk_text_basic(self, mock_tokenizer):
        text = "word " * 200
        chunks = chunk_text(mock_tokenizer, text, max_length=100, min_chunk_words=5)
        assert len(chunks) > 0
        for chunk, tokens, words in chunks:
            assert tokens <= 100
            assert words >= 5

    def test_chunk_text_empty(self, mock_tokenizer):
        chunks = chunk_text(mock_tokenizer, "", max_length=512)
        assert chunks == []

    def test_chunk_text_short(self, mock_tokenizer):
        text = "short text"
        chunks = chunk_text(mock_tokenizer, text, max_length=512, min_chunk_words=10)
        assert chunks == []

    def test_chunk_text_long_sentence(self, mock_tokenizer):
        text = "word " * 200
        chunks = chunk_text(mock_tokenizer, text, max_length=50, min_chunk_words=2)
        assert len(chunks) > 0
        for chunk, tokens, words in chunks:
            assert tokens <= 50


# =========================================================
# CALIBRATOR TESTS
# =========================================================

class TestCalibrator:

    def test_fit_and_transform(self):
        logits = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
        labels = np.array([0, 0, 1, 1, 1])
        cal = fit_platt_scaling(logits, labels)
        assert cal.fitted

        probs = cal.transform(logits)
        assert probs[0] < 0.5  # negative logit -> human
        assert probs[-1] > 0.5  # positive logit -> AI
        assert all(0.0 <= p <= 1.0 for p in probs)

    def test_save_and_load(self):
        cal = LogisticCalibrator()
        logits = np.array([-1.0, 1.0])
        labels = np.array([0, 1])
        cal.fit(logits, labels)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            cal.save(path)
            loaded = LogisticCalibrator.load(path)
            assert loaded is not None
            assert loaded.fitted
            assert loaded.a == cal.a
            assert loaded.b == cal.b
        finally:
            os.unlink(path)

    def test_unfitted_transform(self):
        cal = LogisticCalibrator()
        logits = np.array([0.0, 1.0])
        probs = cal.transform(logits)
        expected = 1.0 / (1.0 + np.exp(-logits))
        np.testing.assert_array_almost_equal(probs, expected)


# =========================================================
# SCORING TESTS
# =========================================================

class TestScoring:

    def test_aggregate_basic(self):
        chunks = [
            ("text one", 10, 10),
            ("text two", 10, 10),
            ("text three", 10, 10),
        ]
        results = [
            {"ai_probability": 0.8, "is_ai": True},
            {"ai_probability": 0.3, "is_ai": False},
            {"ai_probability": 0.9, "is_ai": True},
        ]
        ai, human, meta = aggregate_chunk_scores(chunks, results)
        assert 0 <= ai <= 100
        assert 0 <= human <= 100
        assert ai + human == 100
        assert meta["ai_chunks"] == 2
        assert meta["human_chunks"] == 1

    def test_aggregate_empty(self):
        ai, human, meta = aggregate_chunk_scores([], [])
        assert ai == 0
        assert human == 100
        assert meta["total_chunks"] == 0

    def test_aggregate_threshold(self):
        chunks = [("text", 5, 5)]
        results = [{"ai_probability": 0.49, "is_ai": False}]
        ai, human, meta = aggregate_chunk_scores(chunks, results, ai_threshold=0.5)
        assert ai == 0
        assert human == 100


# =========================================================
# DETECTOR TESTS
# =========================================================

class TestDetector:

    def test_detector_unavailable_without_checkpoint(self):
        detector = get_detector()
        assert detector.available is False

    def test_analyze_returns_unavailable(self):
        detector = get_detector()
        result = detector.analyze("some text")
        assert result["available"] is False
        assert "reason" in result

    def test_analyze_short_text(self):
        detector = get_detector()
        result = detector.analyze("hi")
        assert result["ai_score"] == 0
        assert result["human_score"] == 100

    def test_model_info(self):
        detector = get_detector()
        info = detector.model_info
        assert "model_name" in info or len(info) == 0

    def test_device_detection(self):
        detector = get_detector()
        assert detector.device in ("cpu", "cuda")


# =========================================================
# INTEGRATION TESTS
# =========================================================

class TestIntegration:

    def test_flask_app_imports(self):
        from app import app
        assert app is not None

    def test_health_endpoint(self):
        from app import app
        client = app.test_client()
        r = client.get("/health")
        assert r.status_code == 200
        data = r.get_json()
        assert data["application"] == "Turnalyze"

    def test_ai_detector_status_endpoint(self):
        from app import app
        client = app.test_client()
        r = client.get("/api/ai-detector/status")
        assert r.status_code == 200
        data = r.get_json()
        assert "available" in data
        assert "model" in data
        assert "device" in data

    def test_existing_detector_still_works(self):
        from detector import detect_ai
        text = "This is a test of the existing detector."
        result = detect_ai(text)
        assert "ai_score" in result
        assert "human_score" in result
        assert "status" in result
        assert "mode" in result
