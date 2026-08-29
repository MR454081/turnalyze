# DeBERTa-v3-base AI Detector — Training Guide

## Prerequisites

```bash
pip install torch transformers datasets scikit-learn joblib numpy
```

## Dataset Preparation

1. Populate `data/ai_detector/train.csv` with training samples.
2. Populate `data/ai_detector/validation.csv` with validation samples.
3. Populate `data/ai_detector/test.csv` with held-out test samples.

**CSV format:**
```csv
text,label
"Human-written academic text...",0
"AI-generated academic text...",1
```

**Split rules:**
- Split by source/document, NOT by random paragraph.
- Same document must not appear in both train and test.
- Same AI generation prompt must not leak across splits.

## Training Command

```bash
python training/train_deberta_detector.py
```

### Custom Arguments

```bash
python training/train_deberta_detector.py \
    --train_csv data/ai_detector/train.csv \
    --validation_csv data/ai_detector/validation.csv \
    --test_csv data/ai_detector/test.csv \
    --output_dir models/deberta-v3-base-ai-detector \
    --max_length 512 \
    --learning_rate 2e-5 \
    --batch_size 8 \
    --epochs 3 \
    --warmup_ratio 0.1 \
    --weight_decay 0.01 \
    --gradient_accumulation_steps 1 \
    --seed 42 \
    --fp16
```

## Output

The script saves to `models/deberta-v3-base-ai-detector/`:

| File | Description |
|------|-------------|
| `config.json` | Model configuration |
| `model.safetensors` | Trained weights |
| `tokenizer_config.json` | Tokenizer config |
| `vocab.json` | Vocabulary |
| `label_map.json` | Label mapping |
| `calibrator.json` | Platt scaling calibration |
| `metrics.json` | All evaluation metrics |

## Metrics Reported

- Accuracy
- Precision
- Recall
- F1
- ROC-AUC
- Confusion matrix (TN, FP, FN, TP)
- **Human false-positive rate**

## Calibration

After training, the script fits Platt scaling on validation logits and saves the calibrator. The inference pipeline then produces both raw and calibrated probabilities.

## Important

- Do NOT train with no data. The script exits if train/validation CSVs are empty.
- Demo data in `data/ai_detector/demo/` is for pipeline testing only.
- The model must be fine-tuned; the base `microsoft/deberta-v3-base` is NOT an AI detector.
