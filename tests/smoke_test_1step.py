"""1-step smoke test for the DeBERTa training script.

Runs on CPU if CUDA is unavailable, but verifies:
- TrainingArguments construction with warmup_steps (not warmup_ratio)
- Model forward/backward/optimizer step completes
- DataCollatorWithPadding works
"""
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding,
)

MODEL_NAME = "microsoft/deberta-v3-base"


def main():
    print("=" * 60)
    print("1-STEP SMOKE TEST")
    print("=" * 60)

    use_cuda = torch.cuda.is_available()
    device = "cuda" if use_cuda else "cpu"
    print(f"Device: {device}")
    if use_cuda:
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"CUDA version: {torch.version.cuda}")
        print("FP16: enabled")
    else:
        print("WARNING: CUDA not available, running on CPU")

    # Tiny dataset: 4 samples
    samples = [
        {"text": "This is human written text about science.", "label": 0},
        {"text": "This is AI generated text about technology.", "label": 1},
        {"text": "Another human sample with different content.", "label": 0},
        {"text": "Another AI sample with more generated content.", "label": 1},
    ]
    ds = Dataset.from_list(samples)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def tokenize(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=512,
            padding=False,
        )

    ds = ds.map(tokenize, batched=True, remove_columns=["text"])

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=2,
        id2label={0: "human", 1: "ai"},
        label2id={"human": 0, "ai": 1},
    )
    model.to(device)

    # Calculate warmup_steps from warmup_ratio
    warmup_ratio = 0.1
    batch_size = 2
    gradient_accumulation_steps = 1
    epochs = 1
    total_training_steps = (len(ds) / (gradient_accumulation_steps * batch_size)) * epochs
    warmup_steps = int(total_training_steps * warmup_ratio)
    print(f"Total steps: {total_training_steps:.0f}, warmup_steps: {warmup_steps}")

    training_args = TrainingArguments(
        output_dir="./smoke_test_output",
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=2,
        learning_rate=2e-5,
        warmup_steps=warmup_steps,
        weight_decay=0.01,
        gradient_accumulation_steps=gradient_accumulation_steps,
        fp16=use_cuda,
        logging_steps=1,
        seed=42,
        report_to="none",
        max_steps=1,
    )

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ds,
        data_collator=data_collator,
    )

    print("\nRunning 1 training step...")
    start = time.time()
    train_result = trainer.train()
    elapsed = time.time() - start
    print(f"Step completed in {elapsed:.2f}s")
    print(f"Train result: {train_result.metrics}")

    # Verify key things
    assert training_args.warmup_steps == warmup_steps, "warmup_steps mismatch"
    assert train_result.global_step == 1, f"Expected 1 step, got {train_result.global_step}"

    print("\n" + "=" * 60)
    print("SMOKE TEST PASSED")
    print("=" * 60)
    print(f"Step time: {elapsed:.2f}s")
    print(f"Device: {device}")
    if use_cuda:
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"DataCollatorWithPadding: OK")
    print(f"Forward/backward/optimizer step: OK")
    print(f"warmup_steps (from warmup_ratio={warmup_ratio}): {warmup_steps}")
    print("=" * 60)


if __name__ == "__main__":
    main()
