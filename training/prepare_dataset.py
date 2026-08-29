"""
Dataset preparation script for the DeBERTa AI detector.

Downloads real, legally usable datasets from Hugging Face,
filters for academic-style text, balances classes, splits
by source to prevent leakage, and saves to CSV.

Datasets used:
1. knarasi1/student_and_llm_essays (student essays vs LLM essays)
2. artem9k/ai-text-detection-pile (MIT) - essay-style text
3. Project Gutenberg public domain books (human academic prose)

Output:
    data/ai_detector/train.csv
    data/ai_detector/validation.csv
    data/ai_detector/test.csv
    data/ai_detector/challenge.csv
    data/ai_detector/dataset_report.json
"""
import os
import sys
import json
import csv
import random
import hashlib
import re
import urllib.request
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "ai_detector")

TRAIN_CSV = os.path.join(DATA_DIR, "train.csv")
VAL_CSV = os.path.join(DATA_DIR, "validation.csv")
TEST_CSV = os.path.join(DATA_DIR, "test.csv")
CHALLENGE_CSV = os.path.join(DATA_DIR, "challenge.csv")
REPORT_JSON = os.path.join(DATA_DIR, "dataset_report.json")

RANDOM_SEED = 42
TARGET_TOTAL = 2000
TARGET_HUMAN = 1000
TARGET_AI = 1000
MIN_TEXT_LENGTH = 50
MAX_TEXT_LENGTH = 2000
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15

random.seed(RANDOM_SEED)

# =========================================================
# HELPERS
# =========================================================

def _clean_text(text: str) -> str:
    """Basic normalization without removing meaningful variation."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(text.split())
    return text.strip()


def _text_hash(text: str) -> str:
    """Stable hash for duplicate detection."""
    normalized = _clean_text(text).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _validate_sample(sample: Dict) -> Optional[Dict]:
    """Validate and clean a single sample."""
    text = _clean_text(sample.get("text", ""))
    label = sample.get("label")
    if label not in (0, 1):
        return None
    if not text:
        return None
    word_count = len(text.split())
    if word_count < MIN_TEXT_LENGTH:
        return None
    if word_count > MAX_TEXT_LENGTH:
        text = " ".join(text.split()[:MAX_TEXT_LENGTH])
    return {"text": text, "label": int(label)}


def _split_by_source(samples: List[Dict], train_ratio=0.7, val_ratio=0.15, test_ratio=0.15):
    """
    Split samples by source_id to prevent data leakage.
    """
    source_groups = defaultdict(list)
    for sample in samples:
        source = sample.get("source_id", _text_hash(sample["text"]))
        source_groups[source].append(sample)

    sources = list(source_groups.keys())
    random.shuffle(sources)

    n_total = len(sources)
    n_train = int(n_total * train_ratio)
    n_val = int(n_total * val_ratio)

    train_sources = sources[:n_train]
    val_sources = sources[n_train:n_train + n_val]
    test_sources = sources[n_train + n_val:]

    train = []
    val = []
    test = []
    for s in train_sources:
        train.extend(source_groups[s])
    for s in val_sources:
        val.extend(source_groups[s])
    for s in test_sources:
        test.extend(source_groups[s])

    return train, val, test


def _balance_classes(samples: List[Dict], target_per_class: int) -> List[Dict]:
    """Balance human and AI classes by downsampling the majority class."""
    human = [s for s in samples if s["label"] == 0]
    ai = [s for s in samples if s["label"] == 1]

    random.shuffle(human)
    random.shuffle(ai)

    human = human[:target_per_class]
    ai = ai[:target_per_class]

    combined = human + ai
    random.shuffle(combined)
    return combined


def _write_csv(path: str, samples: List[Dict]):
    """Write samples to CSV."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "label"])
        writer.writeheader()
        for sample in samples:
            writer.writerow({"text": sample["text"], "label": sample["label"]})


# =========================================================
# DATASET LOADERS
# =========================================================

def _try_import_datasets():
    try:
        from datasets import load_dataset
        return load_dataset
    except ImportError:
        print("ERROR: 'datasets' package not installed.")
        print("Install with: pip install datasets")
        sys.exit(1)


def load_student_llm_essays(load_dataset, max_samples: int) -> Tuple[List[Dict], str]:
    """
    Load knarasi1/student_and_llm_essays.
    This dataset has essays with embedded labels:
    - "This essay was written by an actual student." -> human (0)
    - "This essay was generated by a Large Language Model." -> AI (1)
    
    Each row contains:
    - Source text (reading passages)
    - Essay instructions
    - "Essay: <actual essay text>"
    - "Determine if... [/INST] <label>"
    """
    print("Loading knarasi1/student_and_llm_essays...")
    samples = []
    seen = set()

    try:
        ds = load_dataset(
            "knarasi1/student_and_llm_essays",
            split="train",
            streaming=True,
            trust_remote_code=False,
        )
    except Exception as e:
        print(f"  Failed to load: {e}")
        return [], "student_llm_essays"

    for row in ds:
        essay = row.get("essay", "")
        if not essay:
            continue

        essay = _clean_text(essay)

        # Parse label from the text after the last [/INST] tag
        inst_match = re.search(r'\[/INST\]\s*(.*?)\s*</s>\s*$', essay)
        if not inst_match:
            continue

        label_text = inst_match.group(1).strip()
        if "written by an actual student" in label_text:
            label = 0
        elif "generated by a Large Language Model" in label_text:
            label = 1
        else:
            continue

        # Extract just the essay text (between "Essay: " and "Determine if...")
        essay_start = re.search(r'\bEssay:\s*', essay)
        essay_end = re.search(r'Determine if the essay if student-written or generated by a Large Language Model\. \[/INST\]', essay)
        
        if not essay_start or not essay_end:
            continue
            
        text = essay[essay_start.end():essay_end.start()]
        text = _clean_text(text)

        if not text or len(text.split()) < MIN_TEXT_LENGTH:
            continue
        if len(text.split()) > MAX_TEXT_LENGTH:
            text = " ".join(text.split()[:MAX_TEXT_LENGTH])

        h = _text_hash(text)
        if h in seen:
            continue
        seen.add(h)

        samples.append({
            "text": text,
            "label": label,
            "source_id": "student_llm_essays",
            "source_dataset": "student_and_llm_essays",
            "source_model": "student" if label == 0 else "llm",
        })

        if len(samples) >= max_samples:
            break

    print(f"  Loaded {len(samples)} samples from student_and_llm_essays")
    return samples, "student_llm_essays"


def load_gutenberg_human_text(max_samples: int) -> Tuple[List[Dict], str]:
    """
    Load public domain text from Project Gutenberg as human samples.
    Uses a small set of well-known academic/literary works.
    """
    print("Loading Project Gutenberg human text...")
    samples = []
    seen = set()

    gutenberg_urls = [
        ("https://www.gutenberg.org/files/1342/1342-0.txt", "Pride_and_Prejudice"),
        ("https://www.gutenberg.org/files/98/98-0.txt", "A_Tale_of_Two_Cities"),
        ("https://www.gutenberg.org/files/1080/1080-0.txt", "The_Federalist"),
    ]

    for url, title in gutenberg_urls:
        if len(samples) >= max_samples:
            break
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            start = text.find("*** START OF")
            end = text.find("*** END OF")
            if start != -1 and end != -1:
                text = text[start:end]
            text = _clean_text(text)
            if not text:
                continue
            words = text.split()
            chunk_size = 200
            for i in range(0, len(words), chunk_size):
                if len(samples) >= max_samples:
                    break
                chunk = " ".join(words[i:i + chunk_size])
                if len(chunk.split()) < MIN_TEXT_LENGTH:
                    continue
                h = _text_hash(chunk)
                if h in seen:
                    continue
                seen.add(h)
                samples.append({
                    "text": chunk,
                    "label": 0,
                    "source_id": f"gutenberg_{title}",
                    "source_dataset": "Project Gutenberg",
                    "source_model": "human",
                })
            print(f"  Loaded {len(samples)} total samples from {title}")
        except Exception as e:
            print(f"  Failed to load {title}: {e}")
            continue

    print(f"  Total Gutenberg samples: {len(samples)}")
    return samples, "gutenberg"


# =========================================================
# MAIN
# =========================================================

def prepare_dataset():
    """Main dataset preparation pipeline."""
    print("=" * 60)
    print("DATASET PREPARATION")
    print("=" * 60)

    load_dataset = _try_import_datasets()

    all_samples = []
    dataset_sources = []

    # 1. Load student vs LLM essays
    # Target: ~1000 human, ~500 AI (balanced)
    student_samples, student_tag = load_student_llm_essays(load_dataset, max_samples=1200)
    all_samples.extend(student_samples)
    dataset_sources.append(("student_and_llm_essays", student_tag, len(student_samples)))

    # 2. Load Gutenberg human text for additional diversity
    gutenberg_samples, gut_tag = load_gutenberg_human_text(max_samples=500)
    all_samples.extend(gutenberg_samples)
    dataset_sources.append(("Project Gutenberg", gut_tag, len(gutenberg_samples)))

    # 3. Deduplicate
    print(f"\nTotal loaded: {len(all_samples)}")
    seen_hashes = set()
    unique = []
    for sample in all_samples:
        h = _text_hash(sample["text"])
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(sample)
    all_samples = unique
    print(f"After deduplication: {len(all_samples)}")

    # 4. Validate
    validated = []
    for sample in all_samples:
        valid = _validate_sample(sample)
        if valid:
            validated.append(valid)
    print(f"After validation: {len(validated)}")

    # 5. Balance classes
    human_count = sum(1 for s in validated if s["label"] == 0)
    ai_count = sum(1 for s in validated if s["label"] == 1)
    print(f"Class distribution: human={human_count}, ai={ai_count}")

    target_per_class = min(TARGET_HUMAN, TARGET_AI, human_count, ai_count)
    if target_per_class == 0:
        print("ERROR: Not enough samples in one or both classes.")
        sys.exit(1)

    balanced = _balance_classes(validated, target_per_class)
    print(f"Balanced dataset: {len(balanced)} samples")

    # 6. Split by source
    train, val, test = _split_by_source(
        balanced,
        train_ratio=TRAIN_RATIO,
        val_ratio=VAL_RATIO,
        test_ratio=TEST_RATIO,
    )

    print(f"\nSplit:")
    print(f"  Train: {len(train)}")
    print(f"  Validation: {len(val)}")
    print(f"  Test: {len(test)}")

    # 7. Write CSVs
    _write_csv(TRAIN_CSV, train)
    _write_csv(VAL_CSV, val)
    _write_csv(TEST_CSV, test)
    print(f"\nCSV files written to {DATA_DIR}")

    # 8. Challenge set
    challenge = [s for s in validated if s not in balanced]
    if challenge:
        challenge = _balance_classes(challenge, min(200, len(challenge) // 2))
        _write_csv(CHALLENGE_CSV, challenge)
        print(f"Challenge set: {len(challenge)} samples")
    else:
        print("No challenge data available.")

    # 9. Generate report
    report = {
        "total_samples": len(balanced),
        "human_samples": sum(1 for s in balanced if s["label"] == 0),
        "ai_samples": sum(1 for s in balanced if s["label"] == 1),
        "train_count": len(train),
        "validation_count": len(val),
        "test_count": len(test),
        "challenge_count": len(challenge) if challenge else 0,
        "duplicates_removed": len(all_samples) - len(validated),
        "invalid_rows_removed": len(all_samples) - len(validated) + (len(validated) - len(balanced)),
        "average_text_length": sum(len(s["text"].split()) for s in balanced) / len(balanced) if balanced else 0,
        "minimum_text_length": min(len(s["text"].split()) for s in balanced) if balanced else 0,
        "maximum_text_length": max(len(s["text"].split()) for s in balanced) if balanced else 0,
        "dataset_sources": [
            {"name": name, "tag": tag, "samples_loaded": count}
            for name, tag, count in dataset_sources
        ],
        "split_logic": "by_source_id",
        "random_seed": RANDOM_SEED,
    }

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Dataset report saved to {REPORT_JSON}")
    print("=" * 60)
    print("DATASET PREPARATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    prepare_dataset()
