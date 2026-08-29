"""
Score aggregation for chunk-level AI probabilities.

Implements length-weighted aggregation and document-level
score calculation with configurable thresholds.
"""
from typing import List, Dict, Tuple


def aggregate_chunk_scores(
    chunks: List[Tuple[str, int, int]],
    results: List[Dict],
    ai_threshold: float = 0.50,
) -> Tuple[int, int, Dict]:
    """
    Aggregate chunk-level probabilities into a document-level score.

    Uses length-weighted averaging: longer chunks carry more weight.

    Parameters
    ----------
    chunks : list of (text, token_count, word_count)
        Chunks produced by the chunker.
    results : list of dict
        Per-chunk inference results with 'ai_probability' and 'label'.
    ai_threshold : float
        Threshold for classifying a chunk as AI.

    Returns
    -------
    ai_score : int
        Document-level AI score (0-100).
    human_score : int
        Document-level human score (0-100).
    metadata : dict
        Breakdown including chunk counts, weighted average, etc.
    """
    if not results or not chunks:
        return 0, 100, {
            "total_chunks": 0,
            "ai_chunks": 0,
            "human_chunks": 0,
            "weighted_avg_prob": 0.0,
            "total_words": 0,
        }

    total_weight = 0.0
    weighted_sum = 0.0
    ai_chunks = 0
    human_chunks = 0

    for (chunk_text, tokens, words), result in zip(chunks, results):
        weight = words
        total_weight += weight
        prob = float(result.get("ai_probability", 0.0))
        weighted_sum += prob * weight

        if prob >= ai_threshold:
            ai_chunks += 1
        else:
            human_chunks += 1

    if total_weight > 0:
        avg_prob = weighted_sum / total_weight
    else:
        avg_prob = sum(r.get("ai_probability", 0.0) for r in results) / len(results)

    ai_score = int(round(avg_prob * 100))
    ai_score = max(0, min(100, ai_score))
    human_score = 100 - ai_score

    total_words = sum(w for _, _, w in chunks)

    metadata = {
        "total_chunks": len(chunks),
        "ai_chunks": ai_chunks,
        "human_chunks": human_chunks,
        "weighted_avg_prob": round(avg_prob, 4),
        "total_words": total_words,
        "ai_threshold": ai_threshold,
    }

    return ai_score, human_score, metadata
