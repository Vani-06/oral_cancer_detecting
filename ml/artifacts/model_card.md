# resnet50_oral_cancer.pt / resnet50_oral_cancer_v2.pt -- Model Card

**Status: NEITHER checkpoint is deployed to the live backend. `MODEL_PATH` is
intentionally left unset.** v2 is a large, real improvement over v1 (round
1), but is not yet accurate enough on real client photos to deploy. See
"Round 2" below.

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
- **Resolving the two loose, currently-unlabeled client image folders**
  (`clinical images zip`, `histopath thesis images` -- see the main
  project plan for why these couldn't be matched to the treatment
  spreadsheet). If the client can supply whatever key connects them to a
  diagnosis, that's up to 100 more real client-domain images.

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

**resnet50_oral_cancer_v3.pt is not the recommended checkpoint. Round 2
(resnet50_oral_cancer_v2.pt) remains the best result so far.** Two
independent engineering attempts (retraining composition in round 2, then
oversampling+capacity in round 3) have now been tried; round 2's 30% is where
this stands until more client data is available. Further blind parameter
search from here has a low expected return relative to the two real levers
listed above (more confirmed-cancer photos, or the two unlabeled folders).

## Reproducing

```
ml/.venv/Scripts/python.exe scripts/prepare_kaggle.py
ml/.venv/Scripts/python.exe scripts/prepare_client_validation.py <path-to-treatment-xlsx>
ml/.venv/Scripts/python.exe scripts/prepare_combined_training.py
ml/.venv/Scripts/python.exe scripts/train.py --epochs 15
  --train-dir data/combined_train --val-dir data/combined_val
  --checkpoint-name resnet50_oral_cancer_v2.pt
ml/.venv/Scripts/python.exe scripts/evaluate.py --checkpoint artifacts/resnet50_oral_cancer_v2.pt --client-eval-dir data/client_holdout
```
