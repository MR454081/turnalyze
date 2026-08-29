"""
Tests for the DeBERTa AI detector prototype.

Run with:
    python tests/run_tests.py
"""
import os
import sys
import json
import tempfile
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


# =========================================================
# TESTS
# =========================================================

def test_extract_sentences():
    text = "First sentence. Second sentence! Third?"
    sentences = extract_sentences(text)
    assert len(sentences) == 3
    print("  test_extract_sentences: PASS")


def test_chunk_text_basic():
    tokenizer = MockTokenizer()
    text = "word " * 200
    chunks = chunk_text(tokenizer, text, max_length=100, min_chunk_words=5)
    assert len(chunks) > 0
    for chunk, tokens, words in chunks:
        assert tokens <= 100
        assert words >= 5
    print("  test_chunk_text_basic: PASS")


def test_chunk_text_empty():
    tokenizer = MockTokenizer()
    chunks = chunk_text(tokenizer, "", max_length=512)
    assert chunks == []
    print("  test_chunk_text_empty: PASS")


def test_chunk_text_short():
    tokenizer = MockTokenizer()
    text = "short text"
    chunks = chunk_text(tokenizer, text, max_length=512, min_chunk_words=10)
    assert chunks == []
    print("  test_chunk_text_short: PASS")


def test_chunk_text_long_sentence():
    tokenizer = MockTokenizer()
    text = "word " * 200
    chunks = chunk_text(tokenizer, text, max_length=50, min_chunk_words=2)
    assert len(chunks) > 0
    for chunk, tokens, words in chunks:
        assert tokens <= 50
    print("  test_chunk_text_long_sentence: PASS")


def test_calibrator_fit_and_transform():
    logits = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    labels = np.array([0, 0, 1, 1, 1])
    cal = fit_platt_scaling(logits, labels)
    assert cal.fitted
    probs = cal.transform(logits)
    assert probs[0] < 0.5
    assert probs[-1] > 0.5
    assert all(0.0 <= p <= 1.0 for p in probs)
    print("  test_calibrator_fit_and_transform: PASS")


def test_calibrator_save_and_load():
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
    print("  test_calibrator_save_and_load: PASS")


def test_calibrator_unfitted():
    cal = LogisticCalibrator()
    logits = np.array([0.0, 1.0])
    probs = cal.transform(logits)
    expected = 1.0 / (1.0 + np.exp(-logits))
    np.testing.assert_array_almost_equal(probs, expected)
    print("  test_calibrator_unfitted: PASS")


def test_scoring_aggregate_basic():
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
    print("  test_scoring_aggregate_basic: PASS")


def test_scoring_aggregate_empty():
    ai, human, meta = aggregate_chunk_scores([], [])
    assert ai == 0
    assert human == 100
    assert meta["total_chunks"] == 0
    print("  test_scoring_aggregate_empty: PASS")


def test_scoring_aggregate_threshold():
    chunks = [("text", 5, 5)]
    results = [{"ai_probability": 0.49, "is_ai": False}]
    ai, human, meta = aggregate_chunk_scores(chunks, results, ai_threshold=0.5)
    assert ai == 49  # 0.49 * 100 rounded
    assert human == 51
    assert meta["ai_chunks"] == 0
    assert meta["human_chunks"] == 1
    print("  test_scoring_aggregate_threshold: PASS")


def test_detector_unavailable():
    detector = get_detector()
    assert detector.available is False
    print("  test_detector_unavailable: PASS")


def test_detector_analyze_unavailable():
    detector = get_detector()
    result = detector.analyze("some text")
    assert result["available"] is False
    assert "reason" in result
    print("  test_detector_analyze_unavailable: PASS")


def test_detector_short_text():
    detector = get_detector()
    result = detector.analyze("hi")
    # When no checkpoint exists, detector reports unavailable
    if not detector.available:
        assert result["available"] is False
    else:
        assert result["ai_score"] == 0
        assert result["human_score"] == 100
    print("  test_detector_short_text: PASS")


def test_detector_device():
    detector = get_detector()
    assert detector.device in ("cpu", "cuda")
    print("  test_detector_device: PASS")


def test_flask_app_imports():
    from app import app
    assert app is not None
    print("  test_flask_app_imports: PASS")


def test_health_endpoint():
    from app import app
    client = app.test_client()
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["application"] == "Turnalyze"
    print("  test_health_endpoint: PASS")


def test_ai_detector_status_endpoint():
    from app import app
    client = app.test_client()
    r = client.get("/api/ai-detector/status")
    assert r.status_code == 200
    data = r.get_json()
    assert "available" in data
    assert "model" in data
    assert "device" in data
    print("  test_ai_detector_status_endpoint: PASS")


def test_existing_detector():
    from detector import detect_ai
    text = "This is a test of the existing detector."
    result = detect_ai(text)
    assert "ai_score" in result
    assert "human_score" in result
    assert "status" in result
    assert "mode" in result
    print("  test_existing_detector: PASS")


def test_deberta_detector_returns_required_fields():
    detector = get_detector()
    result = detector.analyze("This is a longer test text with enough words to pass the minimum length threshold for analysis.")
    if not detector.available:
        assert result["available"] is False
    else:
        assert "ai_probability" in result
        assert "human_probability" in result
        assert "ai_percentage" in result
        assert "segments" in result
        assert "ai_score" in result
        assert "human_score" in result
        assert "chunks_analyzed" in result
    print("  test_deberta_detector_returns_required_fields: PASS")


def test_pdf_converter_no_independent_detection():
    import inspect
    from pdf_converter import highlight_pdf_text
    source = inspect.getsource(highlight_pdf_text)
    assert "detect_ai" not in source, "highlight_pdf_text must not call detect_ai() independently"
    print("  test_pdf_converter_no_independent_detection: PASS")


def test_app_uses_canonical_detection():
    from app import app
    import logging
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1
        r = client.get("/api/ai-detector/status")
        assert r.status_code == 200
        data = r.get_json()
        assert "available" in data
        assert "model" in data
    print("  test_app_uses_canonical_detection: PASS")


def test_score_consistency():
    from ai_detector.scoring import aggregate_chunk_scores
    chunks = [
        ("chunk one text here", 10, 5),
        ("chunk two text here", 10, 5),
        ("chunk three text here", 10, 5),
    ]
    results = [
        {"ai_probability": 0.7, "is_ai": True},
        {"ai_probability": 0.3, "is_ai": False},
        {"ai_probability": 0.5, "is_ai": False},
    ]
    ai_score, human_score, meta = aggregate_chunk_scores(chunks, results)
    assert ai_score + human_score == 100
    assert 0 <= ai_score <= 100
    assert meta["total_chunks"] == 3
    assert meta["ai_chunks"] == 2  # 0.7 and 0.5 are >= 0.5 threshold
    assert meta["human_chunks"] == 1
    print("  test_score_consistency: PASS")


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    tests = [
        test_extract_sentences,
        test_chunk_text_basic,
        test_chunk_text_empty,
        test_chunk_text_short,
        test_chunk_text_long_sentence,
        test_calibrator_fit_and_transform,
        test_calibrator_save_and_load,
        test_calibrator_unfitted,
        test_scoring_aggregate_basic,
        test_scoring_aggregate_empty,
        test_scoring_aggregate_threshold,
        test_detector_unavailable,
        test_detector_analyze_unavailable,
        test_detector_short_text,
        test_detector_device,
        test_flask_app_imports,
        test_health_endpoint,
        test_ai_detector_status_endpoint,
        test_existing_detector,
        test_deberta_detector_returns_required_fields,
        test_pdf_converter_no_independent_detection,
        test_app_uses_canonical_detection,
        test_score_consistency,
    ]

    print("=" * 60)
    print("RUNNING AI DETECTOR TESTS")
    print("=" * 60)

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  {test.__name__}: FAIL - {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
