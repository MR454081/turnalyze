# Academic AI-Detection Model Comparison
## Turnalyze — Post-Oxidane Evaluation

**Date:** 2026-08-21  
**Status:** Oxidane isolated. Experimental heuristic active. No production AI model deployed.

---

## Validation Dataset Recommendation

Before evaluating any candidate, we recommend using one of the following defensible evaluation datasets that are **independent of any candidate model's training data**:

| Dataset | Description | Human Academic | AI Academic | Notes |
|---------|-------------|----------------|-------------|-------|
| **RAID Benchmark** (Dugan et al., ACL 2024) | 6M+ generations, 11 generators, 8 domains, 12 adversarial attacks | Yes (news, wiki, abstracts, reviews, poetry, recipes, Reddit, books) | Yes | Largest independent benchmark. **Critical finding:** most detectors fail at FPR < 1%. |
| **PAN@CLEF 2025 GenAIDetect Shared Task** | Student essay detection with modern LLMs | Yes (student essays) | Yes (GPT-4, Claude, etc.) | Includes evasion tactics and modern LLMs. |
| **ASU STEM Student Essay Study** (2024/2025) | 174 STEM undergrad essays (50 human + 49 AI) | Yes (human-written anatomy/physiology essays) | Yes (AI-generated) | Independent evaluation of 4 detectors on real student work. |
| **Liang et al. TOEFL Dataset** | 91 TOEFL essays (non-native English) | Yes | No (human-only) | Documents extreme FPR on non-native academic writing. |
| **HC3 / HC3 Plus** | Human vs ChatGPT conversations and essays | Yes | Yes (ChatGPT) | Widely used but older; may not include modern LLMs. |
| **Kaggle "LLM Detect AI Generated Text"** | Vanderbilt/Learning Agency Lab competition | Yes (student essays) | Yes (various LLMs) | 27k+ essays. Good for academic prose evaluation. |

**Recommended primary validation:** RAID Benchmark + ASU STEM Study + Kaggle competition data.

---

## Candidate Model Comparison

### 1. Oxidane/tmr-ai-text-detector (ISOLATED — NOT FOR PRODUCTION)

| Property | Value |
|----------|-------|
| **Architecture** | RoBERTa-base (125M params) |
| **Training dataset** | RAID (50k stratified samples: 45% human, 55% AI) |
| **Human academic data** | RAID includes abstracts, reviews, Wikipedia, Reddit, poetry, recipes, books, news |
| **AI academic data** | 11 generative models in RAID |
| **Evaluation dataset** | RAID held-out (100k samples), RAID leaderboard (672k test samples) |
| **Student writing tested** | No specific student essay evaluation published |
| **Modern LLMs tested** | Yes — RAID includes 11 generators |
| **Human false-positive rate** | **97.42% accuracy on held-out, but FPR at 5% threshold is high for academic prose** |
| **AI detection performance** | AUROC 99.28% on RAID (all settings), 99.85% (no adversarial) |
| **OOD evaluation** | Yes — RAID tests OOD generators, attacks, decoding strategies |
| **Context length** | 512 tokens |
| **License** | MIT |
| **CPU requirements** | Low — RoBERTa-base, ~500MB |
| **Maintenance** | Active (2025) |
| **Known limitations** | **Model card explicitly warns: "may have higher false positive rates on casual conversation, short text, or domains not seen during training"** |

**Verdict for Turnalyze:** **NOT SUITABLE.** Our testing confirmed 96–99% AI scores on genuine student theses and academic documents. The model was trained on RAID which includes diverse domains but appears to heavily weight formal/structured prose as AI signal. This is the exact failure mode documented in academic literature (Liang et al. 2023, Stanford HAI).

---

### 2. desklib/ai-text-detector-academic-v1.01

| Property | Value |
|----------|-------|
| **Architecture** | microsoft/deberta-v3-large (0.4B params) |
| **Training dataset** | Academic-specific data (details not fully disclosed) |
| **Human academic data** | Academic papers (details undisclosed) |
| **AI academic data** | Various LLMs (details undisclosed) |
| **Evaluation dataset** | Claims "leading performance on RAID Benchmark" |
| **Student writing tested** | Not explicitly stated |
| **Modern LLMs tested** | Yes — claims adversarial robustness |
| **Human false-positive rate** | Not explicitly stated on model card |
| **AI detection performance** | Claims high accuracy on academic data; RAID leaderboard performance claimed |
| **OOD evaluation** | Claims robustness across academic contexts |
| **Context length** | 768 tokens (per usage example) |
| **License** | MIT |
| **CPU requirements** | Moderate — DeBERTa-v3-large, ~1.3GB |
| **Maintenance** | Active (Desklib commercial product) |
| **Known limitations** | Model card warns: "may not perform optimally on general-purpose or creative writing texts" |

**Concerns for Turnalyze:**
- Training data details are opaque (commercial product)
- No specific FPR numbers published for human academic writing
- DeBERTa-v3-large is heavier than RoBERTa but still feasible on CPU
- Claims need independent verification

---

### 3. andreas122001/roberta-academic-detector

| Property | Value |
|----------|-------|
| **Architecture** | RoBERTa-base (125M params) |
| **Training dataset** | ChatGPT-Research-Abstracts (20k samples) + arxiv-abstracts-2021 (human) |
| **Human academic data** | arXiv abstracts (real human research abstracts) |
| **AI academic data** | ChatGPT-generated research abstracts |
| **Evaluation dataset** | In-domain only (same distribution as training) |
| **Student writing tested** | No — only research abstracts, not student essays |
| **Modern LLMs tested** | **No — only ChatGPT (GPT-3.5 era), not GPT-4, Claude, etc.** |
| **Human false-positive rate** | Not explicitly reported; in-domain accuracy 98.2% |
| **AI detection performance** | 98.4% in-domain accuracy on ChatGPT abstracts |
| **OOD evaluation** | No — no OOD testing reported |
| **Context length** | 512 tokens |
| **License** | OpenRAIL |
| **CPU requirements** | Low — RoBERTa-base, ~500MB |
| **Maintenance** | 2023 bachelor's thesis — no updates since |
| **Known limitations** | Only trained on ChatGPT abstracts; no modern LLM evaluation; no student essay testing |

**Concerns for Turnalyze:**
- 2023 thesis — outdated for modern LLMs (GPT-4, Claude, Gemini, etc.)
- Only tested on research abstracts, not full student essays or theses
- No OOD evaluation
- OpenRAIL license has usage restrictions

---

### 4. followsci/bert-ai-text-detector

| Property | Value |
|----------|-------|
| **Architecture** | BERT-base-uncased (110M params) |
| **Training dataset** | Custom Academic Text Dataset (1.48M paragraph-level samples) |
| **Human academic data** | arXiv papers |
| **AI academic data** | Various LLMs (GPT, Claude, etc.) |
| **Evaluation dataset** | Self-reported test set (185,930 samples) |
| **Student writing tested** | No — paragraph-level academic text, not student essays |
| **Modern LLMs tested** | Claims various LLMs but no specific list |
| **Human false-positive rate** | **0.82% (self-reported)** |
| **AI detection performance** | 99.57% accuracy, 99.58% F1 (self-reported) |
| **OOD evaluation** | Not reported |
| **Context length** | 512 tokens |
| **License** | MIT |
| **CPU requirements** | Low — BERT-base, ~420MB |
| **Maintenance** | Unknown — minimal activity |
| **Known limitations** | Paragraph-level only; performance on full documents unknown; self-reported metrics only; no independent validation |

**Concerns for Turnalyze:**
- Only tested at paragraph level, not full documents
- Self-reported metrics without independent verification
- No OOD evaluation
- No student essay testing
- The 0.82% FPR claim needs independent validation on actual student writing

---

### 5. Binoculars (Hans et al., 2024)

| Property | Value |
|----------|-------|
| **Architecture** | Zero-shot metric-based (Falcon-7B performer + reference model) |
| **Training dataset** | No fine-tuning — uses pre-trained Falcon models |
| **Human academic data** | News, Creative Writing, Student Essay datasets |
| **AI academic data** | LLaMA-2-13B, Falcon-7B generated text |
| **Evaluation dataset** | RAID, Student Essay, News, Creative Writing |
| **Student writing tested** | Yes — Student Essay dataset |
| **Modern LLMs tested** | LLaMA-2-13B, Falcon-7B, GPT-4, Gemini (March 2024) |
| **Human false-positive rate** | **0.01% (at 0.01% FPR threshold)** |
| **AI detection performance** | AUC 1.00 on student essays; TPR@0.01% FPR = 3.89% on student essays |
| **OOD evaluation** | Yes — tested on unseen generators |
| **Context length** | 512 tokens |
| **License** | Apache 2.0 (Falcon models) |
| **CPU requirements** | Very high — requires Falcon-7B (~13GB VRAM, not feasible on CPU) |
| **Maintenance** | 2024 academic paper |
| **Known limitations** | **Not feasible for CPU deployment.** TPR@0.01% FPR on student essays is only 3.89% — extremely low detection rate at ultra-low FPR. |

**Concerns for Turnalyze:**
- Requires GPU — not feasible for CPU-only deployment
- At ultra-low FPR (0.01%), detection rate on student essays is negligible (3.89%)
- Zero-shot approach may not generalize to modern LLMs

---

### 6. Pangram Labs / DAMAGE (Masrour et al., 2025)

| Property | Value |
|----------|-------|
| **Architecture** | LoRA adapters on frozen base model |
| **Training dataset** | Proprietary (not publicly disclosed) |
| **Human academic data** | Academic text (details undisclosed) |
| **AI academic data** | Multiple LLMs with humanizer augmentation |
| **Evaluation dataset** | RAID, internal datasets |
| **Student writing tested** | Not explicitly stated |
| **Modern LLMs tested** | Yes — GPT-4o and others |
| **Human false-positive rate** | Claims 0.01% (1 in 10,000) — independently verified by U. Chicago + U. Maryland |
| **AI detection performance** | 100% TPR on raw AI, 98.26% TPR on humanized AI at 5% FPR |
| **OOD evaluation** | Yes — RAID benchmark |
| **Context length** | 512 tokens |
| **License** | Commercial / Proprietary |
| **CPU requirements** | Moderate (LoRA adapters) |
| **Maintenance** | Active commercial product |
| **Known limitations** | **Not open source — requires API/subscription. Independently verified but proprietary.** |

**Concerns for Turnalyze:**
- Not open source — requires API access
- Cost considerations for API usage
- Dependency on external service

---

### 7. Proofademic (Commercial)

| Property | Value |
|----------|-------|
| **Architecture** | Sentence-level transformer classifier |
| **Training dataset** | ~195k academic documents |
| **Human academic data** | Academic submissions (native + non-native English) |
| **AI academic data** | 8 frontier LLMs (GPT-5, Claude Sonnet 4.5, Gemini 2.5 Pro, Llama 4 Maverick, DeepSeek-R1, Mistral Large 2, etc.) |
| **Evaluation dataset** | 4,200 human + 2,600 mixed documents |
| **Student writing tested** | Yes — specifically designed for student/academic writing |
| **Modern LLMs tested** | Yes — 8 frontier LLMs |
| **Human false-positive rate** | **0.2% doc-level, 0.5% non-native FPR** |
| **AI detection performance** | 92.9% sentence F1, 97.6–99.9% accuracy across modern LLMs |
| **OOD evaluation** | Yes — generalizes to unseen LLMs (Qwen 3.5, Grok 3) |
| **Context length** | Sentence-level with 5-sentence sliding window |
| **License** | Commercial / Proprietary |
| **CPU requirements** | Moderate (API-based) |
| **Maintenance** | Active commercial product |
| **Known limitations** | **Not open source — requires API/subscription. Best academic-specific detector but not self-hostable.** |

**Concerns for Turnalyze:**
- Not open source
- API/subscription required
- Sentence-level approach requires different architecture than document-level

---

## Summary Comparison Table

| Model | Architecture | Human Academic FPR | Modern LLMs Tested | Student Essays | Open Source | CPU Feasible | License | Maintenance | Turnalyze Suitability |
|-------|-------------|-------------------|-------------------|----------------|-------------|--------------|---------|-------------|----------------------|
| **Oxidane** | RoBERTa-base | **~98% (FAILS)** | Yes (RAID) | No | Yes | Yes | MIT | Active | ❌ REJECTED |
| **Desklib Academic** | DeBERTa-v3-large | Unknown | Yes | Unclear | Yes | Moderate | MIT | Active | ⚠️ Needs validation |
| **NTNU RoBERTa** | RoBERTa-base | Unknown (no FPR) | No (ChatGPT only) | No | Yes | Yes | OpenRAIL | Dormant (2023) | ❌ Outdated |
| **FollowSci BERT** | BERT-base | 0.82% (self-reported) | Claims yes | No | Yes | Yes | MIT | Unknown | ⚠️ Needs validation |
| **Binoculars** | Zero-shot Falcon | 0.01% | Partial (2024) | Yes | Yes | ❌ No | Apache 2.0 | Academic | ❌ Not CPU-feasible |
| **Pangram/DAMAGE** | LoRA adapters | 0.01% (verified) | Yes | Unclear | ❌ No | Moderate | Commercial | Active | ⚠️ API dependency |
| **Proofademic** | Sentence-level | 0.2% | Yes (8 LLMs) | Yes | ❌ No | API | Commercial | Active | ⚠️ Best but not open source |

---

## Key Observations

### 1. The False Positive Problem Is Structural

The research consensus (Liang et al. 2023, RAID 2024, multiple 2025–2026 studies) confirms that **academic writing style is systematically misclassified as AI-generated** by almost all detectors. This is because:

- Academic prose uses formal vocabulary, predictable transitions, and structured arguments
- LLMs are trained on massive amounts of academic text
- The statistical signatures overlap significantly

**No open-source model has demonstrated credible, independently verified low FPR on human academic writing while maintaining high AI detection rates.**

### 2. Self-Reported Metrics Are Unreliable

Almost all open-source models report only in-domain accuracy. The RAID benchmark explicitly warns that "accuracy at fixed FPR" is the correct metric, and most models collapse when FPR is constrained below 1%.

### 3. The Best Academic Detector Is Commercial

**Proofademic** has the strongest evidence for academic use:
- 0.2% doc-level FPR on 4,200 human academic texts
- 0.5% FPR on non-native English writing
- 92.9% sentence F1
- Tested on 8 frontier LLMs
- Published methodology with hard negative mining

But it is **not open source**.

### 4. Open-Source Options Require Independent Validation

The most promising open-source candidates are:
- **desklib/ai-text-detector-academic-v1.01** — specifically fine-tuned for academic data, but training details opaque
- **followsci/bert-ai-text-detector** — claims low FPR, but only paragraph-level testing

Both need independent validation on:
1. Real student essays/theses (not just abstracts)
2. Modern LLM-generated academic text (GPT-4, Claude, Gemini, etc.)
3. Non-native English academic writing

---

## Final Recommendation

### NO SUITABLE PRETRAINED MODEL FOUND

After reviewing the available evidence:

1. **No open-source model** has demonstrated independently verified low false-positive rates on human academic writing (student essays, theses, dissertations) while maintaining high detection rates on modern AI-generated academic text.

2. **Oxidane** has been conclusively shown to fail on academic prose (96–99% AI on genuine student theses).

3. **The desklib and followsci models** show promise but lack:
   - Published FPR numbers on human academic writing
   - Testing on student essays (not just abstracts)
   - Evaluation against modern LLMs
   - Independent validation

4. **Binoculars** is not feasible for CPU deployment.

5. **Proofademic** is the strongest candidate but is proprietary/commercial.

---

## Recommended Path Forward

### Option A: Build/Fine-Tune a Domain-Specific Detector

**Recommend: YES**

Given the structural problem that academic writing resembles AI output, the only reliable path is to build a detector specifically trained on:

1. **Human data:** Real student essays, theses, and dissertations from multiple disciplines
2. **AI data:** Modern LLM-generated academic text (GPT-4, Claude, Gemini, Llama, DeepSeek)
3. **Hard negatives:** Formal academic prose, non-native English writing, heavily edited text
4. **Evaluation:** Held-out test set with explicit FPR constraints

This requires:
- A curated dataset of student writing
- Modern LLM-generated academic prose
- Iterative hard negative mining (as demonstrated by Proofademic)
- Publication of methodology for independent verification

**Estimated effort:** 3–6 months of data curation and training.

### Option B: Use a Commercial/API Detector

**Recommend: POSSIBLE, with caveats**

Proofademic offers the strongest evidence for academic use (0.2% FPR, sentence-level). However:

- Not open source
- API/subscription costs
- Dependency on external service
- Sentence-level architecture requires integration changes

If Turnalyze can accept commercial dependency, this is the most defensible option.

### Option C: Keep Detector as Experimental Research Feature

**Recommend: ADVISABLE INTERIM STATE**

Until a validated detector is available:

1. **Clearly label all detector output as experimental**
2. **Do not use scores for academic misconduct decisions**
3. **Present results as "stylistic analysis" not "AI authorship proof"**
4. **Continue research with independent validation**

---

## Conclusion

**DO NOT deploy any pretrained model for production AI-authorship detection in Turnalyze at this time.**

The current state of academic AI detection does not support reliable, low-false-positive detection of AI-generated academic writing. The Oxidane model's failure on student theses is not an anomaly — it reflects a well-documented structural limitation of current detectors.

The recommended next step is **Option C** (experimental feature) combined with **Option A** (building a domain-specific detector with proper validation).

If Turnalyze needs immediate production AI detection, **Option B** (Proofademic API) is the only option with credible published evidence for academic writing, but it introduces commercial dependency.
