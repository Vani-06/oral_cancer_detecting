# resnet50_oral_cancer.pt -- Model Card

**Status: NOT deployed to the live backend. `MODEL_PATH` is intentionally left
unset.** See "Critical limitation" below -- this is the reason.

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

## Plausible next steps (not yet attempted)

- Include some client images directly in training/fine-tuning, not only
  validation -- despite the tiny n and 98:1 class skew, this is likely the
  single highest-leverage fix, since it would expose the model to the
  client's actual photo domain during training rather than only at eval time.
- Domain-appropriate augmentation during training (color/lighting jitter
  matched to real clinical photo variation, not just mild jitter tuned for
  Kaggle's own images).
- A larger or more representative training set that includes precancerous
  lesion photos as their own category, rather than binary
  Kaggle-clean-Cancer-vs-Non-Cancer.
- Investigate whether the saturation is specific to `layer4`+`fc` fine-tuning
  (too little of the network adapted to the new domain) vs. a fundamentally
  different training distribution problem -- worth a controlled comparison
  before assuming more data alone fixes it.

## Reproducing

```
ml/.venv/Scripts/python.exe scripts/prepare_kaggle.py
ml/.venv/Scripts/python.exe scripts/prepare_client_validation.py <path-to-treatment-xlsx>
ml/.venv/Scripts/python.exe scripts/train.py --epochs 15
ml/.venv/Scripts/python.exe scripts/evaluate.py
```
