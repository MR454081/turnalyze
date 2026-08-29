"""
Test tool for the DeBERTa AI detector prototype.

Usage:
    python tools/test_deberta_detector.py
    python tools/test_deberta_detector.py "some sample text"
    python tools/test_deberta_detector.py --file sample.txt
"""
import os
import sys
import argparse
import time
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from ai_detector import get_detector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Test DeBERTa AI detector")
    parser.add_argument("text", nargs="?", default=None, help="Text to analyze")
    parser.add_argument("--file", default=None, help="Text file to analyze")
    parser.add_argument("--checkpoint", default=None, help="Custom checkpoint path")
    args = parser.parse_args()

    # Build detector
    detector = get_detector()
    if args.checkpoint:
        detector = type(detector)(checkpoint=args.checkpoint)

    print("=" * 60)
    print("DeBERTa AI Detector Test")
    print("=" * 60)
    print(f"Model: {detector.model_info.get('model_name', 'microsoft/deberta-v3-base')}")
    print(f"Checkpoint: {detector.checkpoint}")
    print(f"Device: {detector.device}")
    print(f"Available: {detector.available}")
    print("=" * 60)

    if not detector.available:
        print("\nFine-tuned checkpoint not found.")
        print("Train the model first:")
        print("  python training/train_deberta_detector.py")
        return

    # Get text
    text = args.text
    if text is None and args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    if text is None:
        text = (
            "The influence of country of origin on consumer perceptions has been "
            "extensively studied in international marketing literature. This paper "
            "examines how brand origin interacts with country of origin to shape "
            "consumer attitudes and purchase intentions. We conducted an experiment "
            "with 240 participants using a between-subjects design. Results indicate "
            "that brand origin moderates the effect of country of origin on perceived quality."
        )

    print(f"\nInput text length: {len(text.split())} words")
    print("-" * 60)

    start = time.time()
    result = detector.analyze(text)
    elapsed = time.time() - start

    if not result.get("available", True):
        print(f"\nDetector unavailable: {result.get('reason')}")
        return

    print(f"\nRaw AI probability:    {result.get('raw_avg_prob', 0.0) * 100:.2f}%")
    print(f"Calibrated AI prob:    {result.get('calibrated_avg_prob', 0.0) * 100:.2f}%")
    print(f"Document AI score:     {result['ai_score']}%")
    print(f"Document Human score:  {result['human_score']}%")
    print(f"Status:                {result['status']}")
    print(f"Calibrated:            {result.get('calibrated', False)}")
    print(f"Chunks analyzed:       {result.get('chunks_analyzed', 0)}")
    print(f"Words:                 {result.get('words', 0)}")
    print(f"Inference time:        {elapsed:.2f}s")

    if result.get("segments"):
        print("\nTop AI segments:")
        for i, seg in enumerate(result["segments"][:5], 1):
            print(f"  {i}. [{seg['ai_probability']:.2f}] {seg['text'][:80]}...")

    print("=" * 60)


if __name__ == "__main__":
    main()
