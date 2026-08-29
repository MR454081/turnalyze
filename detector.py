"""
TURNALYZE DETECTOR — TEMPORARY EXPERIMENTAL STATE

WARNING: This detector is currently in an EXPERIMENTAL state.
No validated AI model is active in production.

Oxidane/tmr-ai-text-detector has been isolated for testing because
it produces high false-positive rates on legitimate academic writing.

Do NOT present the scores produced by this module as validated
AI-authorship evidence. They are heuristic indicators only.

====================================================================
OPTION A: EXPERIMENTAL HEURISTIC (currently active)
====================================================================
A basic heuristic analyzer that flags stylistically suspicious text.
This is NOT a machine-learning model and is NOT validated for
academic authorship detection.

====================================================================
OPTION B: OXIDANE MODEL (isolated for testing)
====================================================================
Oxidane/tmr-ai-text-detector is available in _run_oxidane() for
offline testing only. It has known high false-positive rates on
academic prose and must NOT be used in production without further
domain-specific validation.
====================================================================
"""

import re
import os
import time
import logging
from typing import List, Dict, Optional, Tuple

from docx import Document
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# =========================================================
# CONFIGURATION
# =========================================================

MODEL_ID = "Oxidane/tmr-ai-text-detector"
MAX_TOKENS = 512
MIN_CHUNK_WORDS = 40
BATCH_SIZE = 8

# Heuristic weights
W_AI_MARKERS = 0.35
W_FORMAL = 0.20
W_VARIETY = 0.20
W_STARTERS = 0.15
W_LENGTH = 0.10

# Thresholds
AI_MARKER_THRESHOLD = 0.015
FORMAL_THRESHOLD = 0.12

# =========================================================
# GLOBAL MODEL CACHE (for Option B only)
# =========================================================

_tokenizer = None
_model = None
_device = None


def _get_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _load_model():
    global _tokenizer, _model, _device
    if _tokenizer is not None and _model is not None:
        return _tokenizer, _model, _device
    _device = _get_device()
    load_start = time.time()
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
    except Exception as exc:
        raise RuntimeError(
            f"Failed to import transformers/torch for detector: {exc}"
        ) from exc
    logger.info(
        "Loading detector model: %s on device=%s", MODEL_ID, _device
    )
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    _model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)
    _model.eval()
    if _device == "cuda":
        _model = _model.cuda()
    load_time = time.time() - load_start
    logger.info(
        "Detector model loaded in %.2f seconds. Labels: %s",
        load_time,
        _model.config.id2label,
    )
    return _tokenizer, _model, _device


# =========================================================
# TEXT EXTRACTION
# =========================================================

def read_docx(path: str) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def read_pdf(path: str) -> str:
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


# =========================================================
# TEXT CLEANING
# =========================================================

def _clean_text(raw_text: str) -> str:
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
# EXPERIMENTAL HEURISTIC DETECTOR (Option A)
# =========================================================

_AI_MARKERS = [
    "delve into", "intricacies", "tapestry", "multifaceted",
    "nuanced", "paramount", "testament to", "underscore",
    "pivotal", "robust", "comprehensive", "holistic",
    "it is important to note", "it is crucial to",
    "in today's world", "in today's rapidly evolving",
    "landscape", "realm", "delve", "furthermore",
    "moreover", "thus", "therefore", "consequently",
    "in conclusion", "to summarize", "in summary",
    "as we have seen", "as discussed", "as previously mentioned",
    "this paper", "this study", "this research",
    "the present study", "the present research",
    "significant", "crucial", "essential", "fundamental",
    "in light of", "in the context of", "with regard to",
    "a myriad of", "a plethora of", "a wealth of",
    "it is evident that", "it becomes clear that",
    "plays a vital role", "plays a crucial role",
    "contribute to", "contribute significantly",
    "foster", "leverage", "utilize", "facilitate",
    "not only", "but also", "both", "as well as",
]

_FORMAL_MARKERS = [
    "the", "of", "and", "in", "to", "of the", "in the",
    "on the", "for the", "with the", "by the", "to the",
    "that", "this", "these", "those", "which", "whose",
    "among", "between", "through", "during", "before",
    "after", "above", "below", "from", "into",
]

_AI_STARTERS = [
    "in today's", "the purpose of", "this paper aims",
    "this study aims", "the aim of", "the objective of",
    "it is clear", "it is important", "it is essential",
    "research has shown", "studies have shown",
    "it is worth noting", "it should be noted",
    "the fact that", "the reality is",
]


def _compute_ai_marker_density(text: str) -> float:
    words = text.lower().split()
    if not words:
        return 0.0
    count = 0
    for marker in _AI_MARKERS:
        if marker in text.lower():
            count += 1
    return min(count / 15.0, 1.0)


def _compute_formality_score(text: str) -> float:
    words = text.lower().split()
    if not words:
        return 0.0
    formal = sum(1 for w in words if w in _FORMAL_MARKERS)
    return min(formal / max(len(words), 1), 1.0)


def _compute_variety_score(text: str) -> float:
    words = text.lower().split()
    if not words:
        return 0.0
    unique = len(set(words))
    total = len(words)
    ratio = unique / total if total else 0.0
    if ratio > 0.7:
        return 1.0
    elif ratio > 0.5:
        return 0.5
    return 0.0


def _compute_starter_score(text: str) -> float:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if not sentences:
        return 0.0
    count = sum(
        1 for s in sentences[: min(len(sentences), 5)]
        if any(s.lower().startswith(st) for st in _AI_STARTERS)
    )
    return min(count / max(len(sentences[:5]), 1), 1.0)


def _compute_length_score(words: int) -> float:
    if words >= 300:
        return 1.0
    elif words >= 150:
        return 0.5
    return 0.0


def _heuristic_score(text: str) -> Tuple[int, int, Dict]:
    marker_density = _compute_ai_marker_density(text)
    formality = _compute_formality_score(text)
    variety = _compute_variety_score(text)
    starter = _compute_starter_score(text)
    words = len(text.split())
    length = _compute_length_score(words)

    ai_component = (
        W_AI_MARKERS * marker_density
        + W_FORMAL * formality
        + W_VARIETY * variety
        + W_STARTERS * starter
        + W_LENGTH * length
    )

    ai_score = int(round(ai_component * 100))
    ai_score = max(0, min(100, ai_score))
    human_score = 100 - ai_score

    details = {
        "marker_density": marker_density,
        "formality": formality,
        "variety": variety,
        "starter_score": starter,
        "length_score": length,
        "ai_component": ai_component,
    }

    return ai_score, human_score, details


# =========================================================
# OXIDANE MODEL INFERENCE (Option B — testing only)
# =========================================================

def _split_into_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _split_paragraph_into_sentences(paragraph: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    return [s.strip() for s in sentences if s.strip()]


def _token_count(tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=True))


def _chunk_text(tokenizer, text: str) -> List[str]:
    paragraphs = _split_into_paragraphs(text)
    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0

    def flush_current():
        nonlocal current, current_tokens
        if current:
            chunks.append(" ".join(current))
            current = []
            current_tokens = 0

    for para in paragraphs:
        para_tokens = _token_count(tokenizer, para)
        if para_tokens <= MAX_TOKENS:
            candidate_tokens = current_tokens + para_tokens + (1 if current else 0)
            if candidate_tokens <= MAX_TOKENS:
                current.append(para)
                current_tokens = candidate_tokens
                continue
            else:
                flush_current()
                current.append(para)
                current_tokens = para_tokens
                continue
        sentences = _split_paragraph_into_sentences(para)
        for sent in sentences:
            sent_tokens = _token_count(tokenizer, sent)
            if sent_tokens > MAX_TOKENS:
                trunc = tokenizer.decode(
                    tokenizer.encode(sent, add_special_tokens=True)[:MAX_TOKENS],
                    skip_special_tokens=True,
                )
                flush_current()
                chunks.append(trunc)
                continue
            candidate_tokens = current_tokens + sent_tokens + (1 if current else 0)
            if candidate_tokens <= MAX_TOKENS:
                current.append(sent)
                current_tokens = candidate_tokens
            else:
                flush_current()
                current.append(sent)
                current_tokens = sent_tokens
    flush_current()
    return chunks


def _filter_chunks(chunks: List[str], tokenizer) -> List[str]:
    filtered = []
    for chunk in chunks:
        words = len(chunk.split())
        if words >= MIN_CHUNK_WORDS:
            filtered.append(chunk)
        elif words >= 10 and _token_count(tokenizer, chunk) >= 20:
            filtered.append(chunk)
    return filtered


def _run_inference(tokenizer, model, device, chunks: List[str]) -> List[Dict]:
    results: List[Dict] = []
    total_chunks = len(chunks)
    for i in range(0, total_chunks, BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        inputs = tokenizer(
            batch,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_TOKENS,
            padding=True,
        )
        if device == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}
        import torch
        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
        for j, chunk_text in enumerate(batch):
            human_prob = probs[j][0].item()
            ai_prob = probs[j][1].item()
            results.append(
                {
                    "text": chunk_text,
                    "ai_probability": round(ai_prob, 4),
                    "human_probability": round(human_prob, 4),
                    "is_ai": ai_prob > human_prob,
                }
            )
    return results


def _aggregate_score(chunks: List[str], results: List[Dict]) -> Tuple[int, int]:
    if not results:
        return 0, 100
    total_weight = 0.0
    weighted_sum = 0.0
    for chunk, result in zip(chunks, results):
        weight = len(chunk.split())
        total_weight += weight
        weighted_sum += result["ai_probability"] * weight
    if total_weight == 0:
        avg_prob = sum(r["ai_probability"] for r in results) / len(results)
    else:
        avg_prob = weighted_sum / total_weight
    ai_score = int(round(avg_prob * 100))
    ai_score = max(0, min(100, ai_score))
    human_score = 100 - ai_score
    return ai_score, human_score


def _run_oxidane(text: str) -> Dict:
    tokenizer, model, device = _load_model()
    clean_text = _clean_text(text)
    words = len(clean_text.split())
    if words < 10:
        return {
            "ai_score": 0,
            "human_score": 100,
            "words": words,
            "status": "Human",
            "highlight_texts": [],
            "text_content": "",
            "segments": [],
            "mode": "oxidane_isolated",
        }
    raw_chunks = _chunk_text(tokenizer, clean_text)
    chunks = _filter_chunks(raw_chunks, tokenizer)
    if not chunks:
        return {
            "ai_score": 0,
            "human_score": 100,
            "words": words,
            "status": "Human",
            "highlight_texts": [],
            "text_content": "",
            "segments": [],
            "mode": "oxidane_isolated",
        }
    results = _run_inference(tokenizer, model, device, chunks)
    ai_score, human_score = _aggregate_score(chunks, results)
    if ai_score < 30:
        status = "Human"
    elif ai_score < 70:
        status = "Mixed"
    else:
        status = "AI"
    sorted_results = sorted(
        results, key=lambda r: r["ai_probability"], reverse=True
    )
    highlight_texts = [r["text"] for r in sorted_results if r["is_ai"]][:6]
    segments = [
        {
            "text": r["text"],
            "ai_probability": r["ai_probability"],
            "is_ai": r["is_ai"],
        }
        for r in results
    ]
    return {
        "ai_score": ai_score,
        "human_score": human_score,
        "words": words,
        "status": status,
        "highlight_texts": highlight_texts,
        "text_content": "\n".join(highlight_texts),
        "segments": segments,
        "mode": "oxidane_isolated",
    }


# =========================================================
# PUBLIC API
# =========================================================

def detect_ai(text: str) -> Dict:
    """
    TURNALYZE DETECTOR — EXPERIMENTAL STATE

    WARNING: This is NOT a validated AI-authorship detector.
    The active mode uses a heuristic analyzer. Oxidane model
    results are isolated and not used in production.

    Returns a dictionary with:
        - ai_score: int (0-100)
        - human_score: int (0-100)
        - words: int
        - status: str ("Human", "Mixed", "AI")
        - mode: str ("heuristic_experimental")
        - highlight_texts: list of flagged segments
        - text_content: joined highlight_texts
        - segments: per-segment results
    """
    start_time = time.time()

    clean_text = _clean_text(text)
    words = len(clean_text.split())

    if words < 10:
        logger.info("Text too short for meaningful detection: %d words", words)
        return {
            "ai_score": 0,
            "human_score": 100,
            "words": words,
            "status": "Human",
            "mode": "heuristic_experimental",
            "highlight_texts": [],
            "text_content": "",
            "segments": [],
        }

    ai_score, human_score, details = _heuristic_score(clean_text)

    if ai_score < 30:
        status = "Human"
    elif ai_score < 70:
        status = "Mixed"
    else:
        status = "AI"

    highlight_texts = []
    segments = []

    if ai_score >= 50:
        sentences = re.split(r"(?<=[.!?])\s+", clean_text)
        flagged = []
        for sentence in sentences:
            if any(m in sentence.lower() for m in _AI_MARKERS):
                flagged.append(sentence)
        highlight_texts = flagged[:6]
        segments = [
            {"text": s, "ai_probability": 0.5, "is_ai": True}
            for s in highlight_texts
        ]

    inference_time = time.time() - start_time
    logger.info(
        "Detector complete: mode=heuristic_experimental, words=%d, "
        "ai_score=%d, human_score=%d, status=%s, time=%.2fs, "
        "details=%s",
        words,
        ai_score,
        human_score,
        status,
        inference_time,
        details,
    )

    return {
        "ai_score": ai_score,
        "human_score": human_score,
        "words": words,
        "status": status,
        "mode": "heuristic_experimental",
        "highlight_texts": highlight_texts,
        "text_content": "\n".join(highlight_texts),
        "segments": segments,
        "details": details,
    }


def detect_ai_oxidane_isolated(text: str) -> Dict:
    """
    Run the isolated Oxidane model for offline testing only.
    This function is NOT called by the production pipeline.
    """
    return _run_oxidane(text)
