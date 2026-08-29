"""
Chunking utilities for the DeBERTa detector.

Respects tokenizer limits, preserves paragraph boundaries,
and maintains mapping from chunk -> original text.
"""
import re
from typing import List, Tuple


def extract_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(
    tokenizer,
    text: str,
    max_length: int = 512,
    overlap: int = 0,
    min_chunk_words: int = 10,
) -> List[Tuple[str, int, int]]:
    """
    Split text into chunks that fit within max_length tokens.

    Returns a list of (chunk_text, token_count, word_count) tuples.

    Strategy:
    1. Split by paragraph boundaries.
    2. Accumulate sentences into chunks respecting max_length.
    3. If a single sentence exceeds max_length, hard-truncate it.
    4. Filter out chunks with fewer than min_chunk_words.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    raw_chunks: List[str] = []
    current_parts: List[str] = []
    current_tokens = 0

    def flush():
        nonlocal current_parts, current_tokens
        if current_parts:
            raw_chunks.append(" ".join(current_parts))
            current_parts = []
            current_tokens = 0

    def count_tokens(part: str) -> int:
        return len(tokenizer.encode(part, add_special_tokens=True))

    for para in paragraphs:
        para_tokens = count_tokens(para)
        if para_tokens <= max_length:
            candidate = current_tokens + para_tokens + (1 if current_parts else 0)
            if candidate <= max_length:
                current_parts.append(para)
                current_tokens = candidate
                continue
            flush()
            current_parts.append(para)
            current_tokens = para_tokens
            continue

        sentences = extract_sentences(para)
        for sent in sentences:
            sent_tokens = count_tokens(sent)
            if sent_tokens > max_length:
                trunc_ids = tokenizer.encode(sent, add_special_tokens=True)[:max_length]
                trunc = tokenizer.decode(trunc_ids, skip_special_tokens=True)
                flush()
                raw_chunks.append(trunc)
                continue

            candidate = current_tokens + sent_tokens + (1 if current_parts else 0)
            if candidate <= max_length:
                current_parts.append(sent)
                current_tokens = candidate
            else:
                flush()
                current_parts.append(sent)
                current_tokens = sent_tokens

    flush()

    result: List[Tuple[str, int, int]] = []
    for chunk in raw_chunks:
        words = len(chunk.split())
        tokens = count_tokens(chunk)
        if words >= min_chunk_words or tokens >= min_chunk_words * 1.5:
            result.append((chunk, tokens, words))

    return result
