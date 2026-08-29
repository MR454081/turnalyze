# Turnalyze AI Detector — DeBERTa-v3-base Prototype

## Overview

This package implements a prototype AI text detector based on
`microsoft/deberta-v3-base`, fine-tuned as a binary classifier
(Human vs AI).

## Modules

| Module | Purpose |
|--------|---------|
| `deberta_detector.py` | Main detector class (`AIDetector`) and singleton access (`get_detector`) |
| `chunker.py` | Text chunking with token-aware paragraph preservation |
| `calibrator.py` | Platt scaling calibration on logits |
| `scoring.py` | Length-weighted aggregation of chunk probabilities |

## Usage

```python
from ai_detector import get_detector

detector = get_detector()

# Check if a fine-tuned checkpoint exists
if detector.available:
    result = detector.analyze(text)
    print(f"AI score: {result['ai_score']}%")
    print(f"Status: {result['status']}")
    print(f"Calibrated: {result['calibrated']}")
else:
    print("Fine-tuned checkpoint not found.")
```

## Return Format

```python
{
    "available": True,
    "model": "microsoft/deberta-v3-base",
    "checkpoint": "models/deberta-v3-base-ai-detector",
    "device": "cpu",
    "calibrated": True,
    "ai_score": 73,
    "human_score": 27,
    "words": 250,
    "status": "AI",
    "highlight_texts": [...],
    "segments": [...],
    "chunks_analyzed": 5,
    "raw_avg_prob": 0.81,
    "calibrated_avg_prob": 0.73,
    "mode": "deberta_prototype"
}
```

## Important Notes

- This is a **prototype**. The base DeBERTa-v3-base model is NOT an AI detector.
- A fine-tuned checkpoint must exist before the detector produces scores.
- If no checkpoint exists, `analyze()` returns `available: False` without fake scores.
- Calibration is optional; raw probabilities are used if no calibrator is found.
