# Invention disclosure (draft) — CONFIDENTIAL

**Same-patient opposite-side referenced assessment of oral lesions from
clinical photographs, with a stability-based three-way result**

Status: internal draft for a patent attorney. Do not publish, present or
push to any public repository before a filing. Draft date: 4 Nov 2026.

## 1. Problem

AI screening of oral lesions from ordinary clinical photographs judges each
photo against *other people's* mouths. Camera, flash, white balance,
distance, mucosal pigmentation, tobacco staining and site anatomy all vary
between patients, and models learn these as shortcuts. In our system this
caused, for example, normal inner-cheek close-ups to be called cancer
(4 of 5 external healthy cheek photos), and harmless photo changes (glare,
JPEG compression, zooming out) made the model miss up to 15% more cancers.
A single yes/no answer also gives false reassurance when the model is
unsure.

## 2. The invention

A smartphone-based system and method in which:

1. **Guided paired capture.** For a suspected lesion at an anatomical site
   and side (e.g. left buccal mucosa), the system instructs the operator to
   also photograph the anatomically matched *contralateral* site of the same
   patient (right buccal mucosa) with the same device, light and distance.
2. **Self-referenced comparison.** The lesion photo and the patient's own
   reference photo are encoded by the same neural network; the assessment
   uses the lesion's difference from the patient's own tissue (distance in
   feature space), so patient- and device-specific appearance cancels out.
3. **Reference validation.** The reference photo is itself checked (oral
   photo gate; model votes). An abnormal-looking reference flags possible
   bilateral disease ("examine both sides").
4. **Lesion-specificity rule.** If the lesion photo is no more different
   from the patient's own reference than healthy tissue typically is between
   sides, a cancer call is not lesion-specific and becomes "inconclusive —
   refer"; the reference can never convert a result to "no cancer"
   (asymmetric, safety-preserving use of the reference).
5. **Stability-based three-way result.** The lesion photo is re-scored under
   a fixed set of diagnosis-preserving transformations (mirror, 90/180/270
   rotations, ±15% exposure, JPEG q40, 85% crop). The count of
   transformations voting cancer yields cancer / inconclusive / no cancer,
   with thresholds fixed on a validation set.
6. **Habit-side concordance.** The patient record captures lesion side and
   the side where betel quid / tobacco is habitually held; a lesion on the
   habit side is reported (informational in the current embodiment).
7. Dysplasia grade (none / mild / moderate / severe) reported alongside,
   with "none" disallowed when the result is cancer.

Single-photo embodiment: in a whole-mouth photo, the left half and the
mirrored right half of the same image serve as lesion and reference.

Implementation (this repository, private branch
`novelty/contralateral-reference`): `backend/app/services/inference_service.py`
(`_assess`, `_cancer_votes`, `_features`, `STABILITY_EDITS`), upload flow in
`frontend/src/pages/PredictPage.tsx`, experiments in
`ml/scripts/reference_experiments.py` and `ml/scripts/asymmetry_experiment.py`.

## 3. Evidence so far (held-out data, threshold 0.5)

| Measure | Result |
|---|---|
| Three-way output, corrected Kaggle test (135 photos): cancers called "no cancer" | 3.4% (single answer: 15.5% missed) |
| Three-way output: inconclusive rate (test / validation) | 8.1% / 12.0% |
| Three-way output: accuracy on decided cases (test) | 90.3% (single answer 87.4%) |
| Left vs mirrored right half asymmetry alone, AUC cancer vs non-cancer (validation / test) | 0.68 / 0.76 |
| Asymmetry added to the model, test AUC | 0.928 vs 0.932 alone (no gain from an untrained combination) |
| Reference colour normalisation (simulated, different-person reference) | **hurt** accuracy (0.87 -> 0.74-0.79); not part of the invention |
| Different-person reference (user uploads) | no separation (distances 0.52-0.83) — a same-patient pair is required |

Interpretation: the stability-based three-way result is validated. The
opposite-side signal exists (asymmetry AUC 0.68-0.76 without any training on
pairs), but its added value over the image model is **not yet shown**; that
requires paired same-patient photographs (section 5).

## 4. Prior art found (not a formal search)

- You et al., arXiv 2609.04512 (Sept 2026): white-light + autofluorescence
  oral images plus questionnaire; contralateral lesion-free tissue was
  *imaged*, but as ordinary normal samples, not as a comparison input.
- Optical spectroscopy of oral mucosa: contralateral normal sites measured
  per patient (e.g. US 6,571,118); colposcope patent WO2015077684A1 uses a
  contralaterally matched normal site. Spectroscopic probes, not
  photographs or learned feature comparison.
- Subhash et al. (diffuse reflectance, R540/R575): site-specific *population*
  normal references, not same-patient.
- Dermatology "ugly duckling" intra-patient comparison (Soenksen et al.
  2021; arXiv 2106.08021): comparison with the patient's own other lesions
  on skin; analogous field.
- Test-time augmentation for uncertainty (general ML): relevant to claim 5
  on its own; the combination with site-matched references and the
  asymmetric safety rule is the proposed contribution.
- Sascan Meditech "OralScan" device (Indian patent, CE) — also a naming
  conflict with this product's current name.

## 5. Pilot needed to prove the comparison

- Paired capture at the client: suspected site + contralateral site, same
  phone, both biopsied or clinically confirmed normal; target 150-300
  patients including confirmed cancers, plus 50-100 people with healthy
  mouths (both sides).
- Train a paired (Siamese) model on lesion/reference pairs; compare against
  the single-photo model on held-out patients (sensitivity, specificity,
  false alarms on normal cheek close-ups).
- Recalibrate `REFERENCE_SAME_AS_NORMAL_MAX` on real same-patient normal
  pairs.

## 6. Disclosure status

- The public repository (sofaspawn/multimodal-dl-oral-cancer-detection)
  already discloses: the photo gate, shortcut probes and augmentation,
  label correction, the grading model with a none class. Those are prior
  art against this filing.
- Not disclosed (private branch and private repo only): everything in
  section 2 and the experiments in section 3.
- In India, software per se is excluded (Patents Act s.3(k)); claims should
  be framed as a capture system and method with a technical effect
  (cancelling device, illumination and patient-specific appearance).
