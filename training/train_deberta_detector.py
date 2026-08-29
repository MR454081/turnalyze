"""
Training script for DeBERTa-v3-base AI text detector.

Usage:
    python training/train_deberta_detector.py

The script reads data/ai_detector/{train,validation,test}.csv,
fine-tunes DeBERTa-v3-base as a binary classifier, and saves
the checkpoint to models/deberta_detector/.

It also fits a Platt scaling calibrator on validation predictions
and saves it alongside the model.
"""
import os
import sys
import json
import time
import logging
import argparse
from typing import Optional

import torch
import numpy as np
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
    DataCollatorWithPadding,
    set_seed,
)
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)

# =========================================================
# PATH SETUP
# =========================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from ai_detector.calibrator import fit_platt_scaling

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================================================
# CONSTANTS
# =========================================================

MODEL_NAME = "microsoft/deberta-v3-base"
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "models", "deberta_detector")
DEFAULT_TRAIN_CSV = os.path.join(BASE_DIR, "data", "ai_detector", "train.csv")
DEFAULT_VAL_CSV = os.path.join(BASE_DIR, "data", "ai_detector", "validation.csv")
DEFAULT_TEST_CSV = os.path.join(BASE_DIR, "data", "ai_detector", "test.csv")

LABEL_MAP = {"human": 0, "ai": 1}
REVERSE_LABEL_MAP = {0: "human", 1: "ai"}

# =========================================================
# ARGUMENTS
# =========================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Train DeBERTa-v3-base AI text detector"
    )
    parser.add_argument("--train_csv", default=DEFAULT_TRAIN_CSV)
    parser.add_argument("--validation_csv", default=DEFAULT_VAL_CSV)
    parser.add_argument("--test_csv", default=DEFAULT_TEST_CSV)
    parser.add_argument("--output_dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max_length", type=int, default=512)
    parser.add_argument("--learning_rate", type=float, default=2e-5)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--eval_batch_size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--warmup_ratio", type=float, default=0.1)
    parser.add_argument("--weight_decay", type=float, default=0.01)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fp16", action="store_true", help="Use mixed precision (CUDA only)")
    parser.add_argument("--no_cuda", action="store_true", help="Force CPU training")
    parser.add_argument("--use_fp16", action="store_true", help="Enable FP16 mixed precision when CUDA is available")
    return parser.parse_args()


# =========================================================
# DATA LOADING
# =========================================================

def load_csv(path: str) -> list:
    """Load a CSV with text,label columns."""
    import csv
    samples = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row.get("text", "").strip()
            label_raw = row.get("label", "").strip()
            if not text or not label_raw:
                continue
            try:
                label = int(label_raw)
            except ValueError:
                continue
            samples.append({"text": text, "label": label})
    return samples


def check_class_balance(samples: list, split_name: str):
    """Report class distribution."""
    human = sum(1 for s in samples if s["label"] == 0)
    ai = sum(1 for s in samples if s["label"] == 1)
    total = len(samples)
    logger.info(
        "%s split: %d samples (human=%d, ai=%d)",
        split_name, total, human, ai,
    )
    if total > 0:
        logger.info(
            "  Class balance: human=%.1f%%, ai=%.1f%%",
            100.0 * human / total,
            100.0 * ai / total,
        )


# =========================================================
# TOKENIZATION
# =========================================================

def tokenize_function(examples, tokenizer, max_length: int):
    return tokenizer(
        examples["text"],
        truncation=True,
        max_length=max_length,
        padding=False,
    )


# =========================================================
# METRICS
# =========================================================

def compute_metrics(eval_pred):
    """Compute accuracy, precision, recall, F1, ROC-AUC, and confusion matrix."""
    logits, labels = eval_pred
    probs = torch.softmax(torch.tensor(logits), dim=-1).numpy()
    preds = np.argmax(logits, axis=-1)

    acc = accuracy_score(labels, preds)
    precision = precision_score(labels, preds, zero_division=0)
    recall = recall_score(labels, preds, zero_division=0)
    f1 = f1_score(labels, preds, zero_division=0)

    try:
        roc_auc = roc_auc_score(labels, probs[:, 1])
    except ValueError:
        roc_auc = 0.0

    tn, fp, fn, tp = confusion_matrix(labels, preds).ravel()

    # Human false-positive rate: human (label 0) misclassified as AI (pred 1)
    human_fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    return {
        "accuracy": round(acc, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "roc_auc": round(roc_auc, 4),
        "human_fpr": round(human_fpr, 4),
        "true_negative": int(tn),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_positive": int(tp),
    }


# =========================================================
# MAIN TRAINING LOOP
# =========================================================

def main():
    args = parse_args()
    set_seed(args.seed)

    # Device
    use_cuda = torch.cuda.is_available() and not args.no_cuda
    device = "cuda" if use_cuda else "cpu"
    logger.info("Device: %s", device)

    if use_cuda:
        gpu_name = torch.cuda.get_device_name(0)
        cuda_version = torch.version.cuda
        logger.info("GPU: %s", gpu_name)
        logger.info("CUDA version: %s", cuda_version)
        logger.info("CUDA available: True")
    else:
        logger.warning("CUDA not available. Training on CPU.")

    # Enable mixed precision on CUDA
    use_fp16 = use_cuda and (args.fp16 or args.use_fp16)
    if use_fp16:
        logger.info("Mixed precision (FP16) enabled.")
    elif use_cuda:
        logger.info("Mixed precision (FP16) not enabled.")

    # Load data
    logger.info("Loading datasets...")
    train_samples = load_csv(args.train_csv)
    val_samples = load_csv(args.validation_csv)
    test_samples = load_csv(args.test_csv)

    check_class_balance(train_samples, "train")
    check_class_balance(val_samples, "validation")
    check_class_balance(test_samples, "test")

    if not train_samples:
        logger.error("Training dataset is empty. Populate data/ai_detector/train.csv before training.")
        sys.exit(1)

    if not val_samples:
        logger.error("Validation dataset is empty. Populate data/ai_detector/validation.csv before training.")
        sys.exit(1)

    # Create Hugging Face Datasets
    train_ds = Dataset.from_list(train_samples)
    val_ds = Dataset.from_list(val_samples)
    test_ds = Dataset.from_list(test_samples) if test_samples else None

    # Tokenizer
    logger.info("Loading tokenizer: %s", MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def tokenize(examples):
        return tokenize_function(examples, tokenizer, args.max_length)

    train_ds = train_ds.map(tokenize, batched=True, remove_columns=["text"])
    val_ds = val_ds.map(tokenize, batched=True, remove_columns=["text"])
    if test_ds:
        test_ds = test_ds.map(tokenize, batched=True, remove_columns=["text"])

    # Model
    logger.info("Loading base model: %s", MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=2,
        id2label=REVERSE_LABEL_MAP,
        label2id=LABEL_MAP,
    )

    # Compute warmup_steps from warmup_ratio for TrainingArguments compatibility.
    # Transformers >= 4.x removed warmup_ratio in favor of warmup_steps.
    total_training_steps = (
        len(train_ds)
        / (args.gradient_accumulation_steps * args.batch_size)
    ) * args.epochs
    warmup_steps = int(total_training_steps * args.warmup_ratio)
    logger.info(
        "Total training steps: %.0f, warmup_steps: %d (from warmup_ratio=%.2f)",
        total_training_steps,
        warmup_steps,
        args.warmup_ratio,
    )

    # Training arguments
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        learning_rate=args.learning_rate,
        warmup_steps=warmup_steps,
        weight_decay=args.weight_decay,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        fp16=use_fp16,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_dir=os.path.join(args.output_dir, "logs"),
        logging_steps=10,
        seed=args.seed,
        report_to="none",
    )

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    # Train
    logger.info("Training started...")
    train_result = trainer.train()
    logger.info("Training complete.")

    # Save final model
    logger.info("Saving model to %s", args.output_dir)
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    # Save label mapping
    label_map_path = os.path.join(args.output_dir, "label_map.json")
    with open(label_map_path, "w") as f:
        json.dump(
            {"id2label": REVERSE_LABEL_MAP, "label2id": LABEL_MAP},
            f,
            indent=2,
        )

    # Validation metrics
    logger.info("Evaluating validation set...")
    val_metrics = trainer.evaluate(val_ds)
    logger.info("Validation metrics: %s", val_metrics)

    # Test metrics
    test_metrics = {}
    if test_ds:
        logger.info("Evaluating test set...")
        test_metrics = trainer.evaluate(test_ds)
        logger.info("Test metrics: %s", test_metrics)

    # Calibration: fit on validation predictions
    logger.info("Fitting calibration on validation predictions...")
    val_predictions = trainer.predict(val_ds)
    val_logits = val_predictions.predictions[:, 1]  # AI class logit
    val_labels = val_predictions.label_ids

    calibrator = fit_platt_scaling(val_logits, val_labels)
    calibrator_path = os.path.join(args.output_dir, "calibrator.json")
    calibrator.save(calibrator_path)
    logger.info("Calibrator saved to %s", calibrator_path)

    # Save all metrics
    metrics = {
        "model_name": MODEL_NAME,
        "checkpoint": args.output_dir,
        "max_length": args.max_length,
        "train_samples": len(train_samples),
        "validation_samples": len(val_samples),
        "test_samples": len(test_samples) if test_samples else 0,
        "training_args": {
            "learning_rate": args.learning_rate,
            "batch_size": args.batch_size,
            "epochs": args.epochs,
            "warmup_ratio": args.warmup_ratio,
            "warmup_steps": warmup_steps,
            "weight_decay": args.weight_decay,
            "gradient_accumulation_steps": args.gradient_accumulation_steps,
        },
        "validation_metrics": {
            k: round(v, 4) if isinstance(v, float) else v
            for k, v in val_metrics.items()
        },
        "test_metrics": {
            k: round(v, 4) if isinstance(v, float) else v
            for k, v in test_metrics.items()
        },
        "calibration": "platt_scaling",
        "calibrator_path": calibrator_path,
    }

    metrics_path = os.path.join(args.output_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Metrics saved to %s", metrics_path)

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"Model saved to: {args.output_dir}")
    print(f"Calibrator saved to: {calibrator_path}")
    print(f"Metrics saved to: {metrics_path}")
    print(f"\nValidation metrics:")
    for k, v in val_metrics.items():
        print(f"  {k}: {v}")
    if test_metrics:
        print(f"\nTest metrics:")
        for k, v in test_metrics.items():
            print(f"  {k}: {v}")
    print("=" * 60)


if __name__ == "__main__":
    main()
