# ResNet-50 Oral Lesion Classifier -- Model Card

**Recommended checkpoint: `resnet50_oral_cancer_v4.pt` (round 4).** It is a
research model, not a validated diagnostic device. Enable it only with the
limitations in "Round 4" understood -- in particular, cancer-detection
sensitivity on the client's own photos cannot be measured with the data
available (one confirmed-cancer case).

| Round | Client false-Cancer rate (held-out patients) | Kaggle accuracy | Kaggle cancer sensitivity |
|---|---|---|---|
| 1 (Kaggle only) | 85.7% (98 photos) | 92.6% | 90.0% |
| 2 (+ spreadsheet photos) | 64.1% (39 photos, same 20 patients as round 4) | 89.6% | 92.9% |
| 3 (+ oversampling, layer3) | 35.0% (20 spreadsheet photos only) | 94.1% | 92.9% |
| **4 (+ folder photos, patient-level split)** | **12.8% (39 photos, 20 patients)** | 91.1% | **84.3%** |

Rounds 2 and 4 are compared on the identical 20 held-out patients; earlier
rounds were evaluated on different subsets and are indicative only.

## Architecture

ResNet-50 (ImageNet-pretrained), `layer4` + `fc` fine-tuned, all earlier
layers frozen. Binary output: Cancer / Non-Cancer.

## Training data

Kaggle "Oral cancer Dataset 2.0" (`zaidpy/oral-cancer-dataset`), the version
matching this project's progress report (500 Cancer / 450 Non-Cancer). The
raw download had real duplicate and near-duplicate images (8% of the Cancer
class); these were clustered and deduplicated *before* splitting, and the
split was verified to have zero exact-hash overlap across train/val/test.

Final deduplicated set: 900 unique images (467 Cancer, 433 Non-Cancer),
split 70/15/15 stratified by class:

| split | Cancer | Non-Cancer |
|---|---|---|
| train | 327 | 303 |
| val   | 70  | 65  |
| test  | 70  | 65  |

Trained 15 epochs; best checkpoint selected by validation accuracy (epoch 3,
before the model started overfitting -- train accuracy climbed to 99%+ by
epoch 15 while validation accuracy plateaued and validation loss rose).

## Metric set 1 -- Kaggle-internal test split (n=135)

Same distribution as training. This is the number that looks good, and the
number that matters least for real-world use.

| metric | value |
|---|---|
| Accuracy | 0.926 |
| Precision (Cancer) | 0.955 |
| Recall (Cancer) | 0.900 |
| F1 (Cancer) | 0.926 |
| ROC-AUC | 0.979 |
| False-Cancer-call rate on Non-Cancer images | 3/65 (4.6%) |

## Metric set 2 -- client external validation (n=99, real clinical photos)

Extracted directly from the client's own patient records (see
`ml/scripts/prepare_client_validation.py`). 98 Non-Cancer (precancerous:
dysplasia grades, OSMF, PVL, hyperkeratosis), 1 confirmed Cancer.

| metric | value |
|---|---|
| Accuracy | 0.152 |
| False-Cancer-call rate on Non-Cancer images | **84/98 (85.7%)** |
| ROC-AUC | 0.939 (see note below -- do not trust this number) |

**This set cannot measure cancer-detection sensitivity** (1 positive case is
not enough), but it decisively measures something else: whether the model
can be trusted on real clinical photos at all. It cannot.

## Critical limitation -- this is not a calibration problem

The ROC-AUC of 0.939 looks reassuring next to 15% accuracy, which prompted a
direct check: does the model's raw confidence score still *rank* images
correctly even if the decision threshold is wrong for this photo domain?

It does not. The one true Cancer case scores 0.998 -- but ranks **7th out of
99** images by P(Cancer). Six Non-Cancer (precancerous) photos score higher.
The Non-Cancer score distribution has a **median of 0.932**; 84/98 exceed
0.5, and 25/98 exceed 0.99. The model's output is saturated near-certain
"Cancer" for most real client photos, true label notwithstanding. No
decision threshold fixes this -- the underlying signal is not there.

This points to **domain shift**, not a tunable defect: the Kaggle training
images are a different visual population from the client's clinical
photography (lighting, camera, framing, compression, and possibly
patient population), and the model has learned features that saturate on
whatever differs from Kaggle's training distribution -- which apparently
includes the client's precancerous lesion photos generally, not anything
specific to malignancy.

## What this means for deployment

**Do not point the backend's `MODEL_PATH` at this checkpoint.** On the
client's own real photos, it would flag genuine precancerous conditions as
cancer roughly 6 times out of 7. That is worse than the current honest
"Pending" state, which at least does not mislead.

## Round 2 (resnet50_oral_cancer_v2.pt) -- client data folded into training

Direct response to round 1's domain-shift finding: the standard fix for a
model that fails on real-world data despite good benchmark numbers is to
expose training to that real-world domain, not just validate against it.

Built via `ml/scripts/prepare_combined_training.py`. The client's 98
Non-Cancer images were split three ways (58 train / 20 val / 20 holdout, seed
42); the single Cancer image went to training, since a held-out sample of one
would prove nothing statistically anyway. Combined training set: 689 images
(328 Cancer, 361 Non-Cancer). Trained 15 epochs; best checkpoint at epoch 6.

**The `client_holdout/` 20 images were never seen during round 2's training
or validation.** They are the one honest measurement in this whole card.

| | Round 1 (Kaggle-only) | Round 2 (client data folded in) |
|---|---|---|
| Kaggle test accuracy | 92.6% | 89.6% |
| Kaggle false-Cancer-call rate (Non-Cancer) | 4.6% | 13.8% |
| **Client false-Cancer-call rate** (holdout, real photos, default 0.5 threshold) | **85.7%** (84/98, full set) | **30.0%** (6/20, true holdout) |

The Kaggle-side regression is the expected, acceptable cost of a model that's
no longer overfit to Kaggle's specific photo style. The client-side
improvement is large and real -- the score distribution on the holdout is
now spread across the full 0-1 range (was saturated near 1.0 in round 1),
confirming the fix addressed the actual mechanism, not just the symptom.

**This is still not "highly accurate."** A 30% false-positive rate on real
precancerous lesions is a genuine, substantial improvement, not a solved
problem.

### Threshold tuning -- tried, limited additional value

Calibrated candidate thresholds against the 20-image client *validation* set
(disjoint from the holdout, to avoid tuning against the same data used to
measure success), then confirmed once on the holdout:

| decision threshold | client false-positive rate | Kaggle cancer-detection sensitivity |
|---|---|---|
| 0.5 (default) | 30.0% (holdout) | 94.3% |
| 0.7 | 20.0% (holdout) | 88.6% |
| 0.9 | ~15% (val-projected) | 74.3% |

Raising the threshold buys a modest false-positive reduction at a steep,
monotonic cost to real cancer-detection sensitivity. There is no threshold
that meaningfully fixes this without trading away the thing the model exists
to do. **Not recommended as a substitute for more/better training data.**

### What would actually move this further

Every labeled client image (98 Non-Cancer + 1 Cancer) is now used somewhere
in train/val/holdout -- there is no more labeled client data left to add.
The two remaining levers both require more data, not more engineering:

- **More confirmed-cancer client photos.** The single existing one is doing
  as much work as it can. This is the single highest-leverage gap.
- ~~Resolving the two loose, currently-unlabeled client image folders~~ --
  **superseded: the folders were labeled all along.** See "Round 4" for the
  correction and how it was established.

Secondary, lower-confidence options: domain-appropriate augmentation tuned to
the client's actual photo conditions (lighting/color, not just Kaggle-style
mild jitter), or a controlled comparison of how much of the network to
unfreeze during fine-tuning.

## Round 3 (resnet50_oral_cancer_v3.pt) -- oversampling + deeper unfreeze, negative result

Tested two of the "secondary options" above together, still with zero new
data: `layer3` unfrozen in addition to `layer4`+`fc` (more capacity to adapt
mid-level texture/color features to the client's photo domain), plus
`WeightedRandomSampler` oversampling client images 4x (raising their share of
each epoch's draws from ~11% to ~27%). Same combined_train/val split as round
2; `client_holdout/` still untouched.

| | Round 2 | Round 3 |
|---|---|---|
| Kaggle test accuracy | 89.6% | **94.1%** (best yet) |
| Kaggle false-Cancer-call rate | 13.8% | **4.6%** (best yet) |
| **Client holdout false-Cancer-call rate** | **30.0%** | **35.0% (worse)** |

**Worse on the metric that matters, better on the ones that don't.** Most
likely explanation: Kaggle images still made up ~73% of every epoch's draws
even at 4x client oversampling, and the added `layer3` capacity gave the
model more room to fit that still-dominant distribution more precisely --
the opposite of the intended effect. Extra capacity without a training mix
that's actually client-dominant seems to make the domain-shift problem
worse, not better.

**resnet50_oral_cancer_v3.pt is not recommended** (superseded by round 4).

## Round 4 (resnet50_oral_cancer_v4.pt) -- both client photo sources, patient-level split

### Correction: the "unlabeled" client folders are labeled

Earlier rounds treated the folders `clinical images zip` (`N c p.jpeg`) and
`histopath thesis images` (`N H.jpeg`) as unusable, because their clinical
photos never matched the spreadsheet's embedded photos. That conclusion was
incomplete. Comparing the **histopath** slides instead (rotation- and
mirror-invariant correlation of normalised 16x16 grayscale descriptors):

- 99 of 100 folder slides are pixel-identical to the spreadsheet's embedded
  histopath image (correlation 1.000), and every one satisfies
  **folder case N = spreadsheet row N+1**.
- Case 12 is the single exception (correlation 0.085); its folder clinical
  photo is excluded as unverified.
- The folder clinical photos are *different photographs of the same lesions*
  (no exact match, but colour similarity ranks the expected case well above
  chance: median rank 30/100, top-10 for 23 of 99 cases vs ~10 by chance).

Result (`prepare_client_cases.py`): **198 client photos from 100 patients**
(99 spreadsheet + 99 verified folder photos; row 52 has only a folder photo).
Histopathology: 24 mild, 39 moderate, 36 severe dysplasia, 1 carcinoma.

### Training and evaluation

`prepare_case_split.py` splits **by patient**, reusing round 2's exact
patient assignment so the two rounds are compared on the identical 20
held-out patients (now 39 photos). Train: Kaggle + 119 client photos; val:
Kaggle + 40 client photos; holdout untouched. Round 2's configuration
(`layer4` + `fc`, no oversampling), best checkpoint at epoch 9 (val 0.886).

| Same 20 held-out patients, 39 photos | Round 2 | **Round 4** |
|---|---|---|
| Client false-Cancer rate | 64.1% (25/39) | **12.8% (5/39)** |
| -- spreadsheet photos | 30.0% (6/20) | 10.0% (2/20) |
| -- folder photos | 100% (19/19) | 15.8% (3/19) |

| Kaggle test (n=135) | Round 2 | Round 4 |
|---|---|---|
| Accuracy | 89.6% | 91.1% |
| False-Cancer rate | 13.8% | 1.5% |
| **Cancer sensitivity** | **92.9%** | **84.3%** (11 of 70 missed) |

Round 2's earlier 30% figure only covered spreadsheet photos; on folder
photos -- a capture source it never saw -- it flagged every one. Round 4
fixes that, at the cost of being more conservative on Kaggle cancers.

### Remaining false positives track dysplasia severity

| Held-out histopathology | Called "Cancer" (round 4) |
|---|---|
| Mild dysplasia | 0 / 16 |
| Moderate dysplasia | 2 / 14 |
| Severe dysplasia | 3 / 9 |

Severe vs mild: Fisher one-sided p = 0.037 (moderate+severe vs mild: p =
0.058). Small sample, so suggestive rather than proven -- but it contrasts
with round 1, whose scores were saturated across every grade (90-96% of
photos above 0.5 regardless of grade, Spearman rho = 0.11, p = 0.12). Round 4's
errors concentrate where clinical risk is highest.

### Operating point (decision threshold)

The backend's `CANCER_THRESHOLD` (default 0.5) sets the P(Cancer) cut-off.
Threshold candidates were chosen on the **validation** set only and then
applied once to test/holdout:

| Threshold | Val sensitivity | Val client FP | Test sensitivity | Test Kaggle FP | Holdout client FP |
|---|---|---|---|---|---|
| 0.50 | 80.0% | 12.5% | 84.3% | 1.5% | 12.8% |
| 0.40 | 82.9% | 15.0% | 85.7% | 1.5% | 12.8% |
| 0.30 | 82.9% | 17.5% | 91.4% | 4.6% | 12.8% |
| 0.20 | 82.9% | 30.0% | 92.9% | 6.2% | 17.9% |
| 0.10 | 88.6% | 37.5% | 95.7% | 12.3% | 23.1% |

No threshold improves sensitivity for free. Which trade-off is acceptable
(missed cancers vs false alarms) is a clinical decision for the client; the
default stays 0.5 until they make it.

### Limitations that still apply

- **Cancer sensitivity on client photos is unmeasured.** The client set has
  one carcinoma case (in training). All client metrics above are
  false-positive rates on dysplasia cases.
- Kaggle sensitivity fell to 84.3% -- 16% of Kaggle cancers are missed at
  the default threshold.
- 100 client patients from one source; no external site, device or
  population validation.
- Binary labels flatten a graded histopathology spectrum (all dysplasia is
  "Non-Cancer"); whether high-grade dysplasia should be flagged is a product
  question for the client.

## Stress test (October 2026) -- random images, harmless edits, non-oral uploads

`scripts/stress_test.py`, round 4 checkpoint, threshold 0.5. Nothing below
was used for training or threshold choice except where stated.

**Harmless edits change the answer for 3-10% of photos.** Each held-out
photo was re-run after mirroring, rotating (90/180/10 degrees), quarter
resolution, JPEG quality 25, +/-20% brightness and an 80% centre crop.
Rotate-90 and cropping were worst (~10% of client holdout answers flipped).
Averaging the model over flipped/rotated copies (test-time augmentation)
looked better on the test sets but made **no difference on validation**
(88.6% with or without), so it was not adopted -- adopting it would have
meant choosing on test data.

**Non-oral images got a confident-looking result.** With no "none of the
above" output, 90% of histopathology slides, 97% of desktop wallpapers and
100% of blank / noise / document images were labelled Non-Cancer -- false
reassurance. The cancer model's own features separate these poorly (it
rejected only about half at a usable cut-off).

**Fix: a photo check before inference** (`scripts/build_photo_gate.py`,
backend `GATE_MODEL_PATH`). ImageNet ResNet-50 features, mean cosine
distance to the 5 nearest training photos, cut-off = 99.5th percentile of
validation-photo distances. Built from oral photos only; the non-oral
images are evaluation only.

| | accepted | refused |
|---|---|---|
| Client holdout photos (39) | 100% | 0% |
| Kaggle test photos (135) | 100% | 0% |
| Histopathology slides (100) | 5% | **95%** |
| Desktop wallpapers (37) | 0% | **100%** |
| Blank / noise / pattern / document (16) | 0% | **100%** |

By construction about 0.5% of genuine photos like the validation set will be
refused (the user is asked for a clearer close-up). Weak spots: photos
heavily degraded or rotated with black corners are refused more often
(~80% of held-out client photos accepted after a 10-degree tilt with black
corners), and the non-oral test set has no faces, skin, teeth or other
body-part photos -- how the check treats those is unmeasured.

## Dysplasia grading (mild / moderate / severe) -- weak; enabled at the client's request

`scripts/train_grading.py`: ResNet-50, layer4 + head fine-tuned, 196 photos
of 99 client patients with a histopathology grade (48 mild, 77 moderate,
71 severe photos). 5-fold cross-validation grouped by patient: every
patient graded once, by a model that never saw them.

| | ImageNet start | Cancer-model (v4) start | Always "moderate" |
|---|---|---|---|
| Photo accuracy | 44.9% | 40.8% | 39.3% |
| Balanced accuracy | 44.4% | 39.1% | 33.3% |
| Quadratic weighted kappa | 0.25 | 0.06 | 0 |
| Patient accuracy | 44.4% | 44.4% | ~39% |

"Within one grade" (89%) is not reported as a success: always answering
"moderate" scores 100% on it. The best model is barely better than guessing
the commonest grade. The client needs a grade shown, so the ImageNet-start
model is trained on all 99 patients (`train_grading.py final --init
imagenet`, `resnet50_dysplasia_grade_v1.pt`) and enabled, with "Low
reliability: matched the biopsy grade for about 45% of patients in testing"
printed next to every grade in the app and the PDF.

A follow-up benchmark (`scripts/benchmark_grading.py`, 10x repeated 5-fold
CV, per patient) found nothing better: case-sheet details alone (age, sex,
habits, habit years, medical history, site and findings from the notes)
reached kappa 0.15, but 13% of shuffled-grade runs scored as high, so it is
indistinguishable from luck; frozen photo features reached 0.07; photo plus
details 0.06. Grade is defined on histopathology, and the
photo may simply not carry enough of that signal at this sample size; more
graded cases, or grading from the slides themselves, are the options.

## Reproducing

```
ml/.venv/Scripts/python.exe scripts/prepare_kaggle.py
ml/.venv/Scripts/python.exe scripts/prepare_client_validation.py <treatment.xlsx>
ml/.venv/Scripts/python.exe scripts/prepare_client_cases.py <treatment.xlsx> <clinical_dir> <histopath_dir>
ml/.venv/Scripts/python.exe scripts/prepare_case_split.py
ml/.venv/Scripts/python.exe scripts/train.py --epochs 15 --train-dir data/case_split/train --val-dir data/case_split/val --checkpoint-name resnet50_oral_cancer_v4.pt
ml/.venv/Scripts/python.exe scripts/evaluate.py --checkpoint artifacts/resnet50_oral_cancer_v4.pt --client-eval-dir data/case_split/holdout
ml/.venv/Scripts/python.exe scripts/stress_test.py
ml/.venv/Scripts/python.exe scripts/build_photo_gate.py
ml/.venv/Scripts/python.exe scripts/train_grading.py cv --init imagenet
```
