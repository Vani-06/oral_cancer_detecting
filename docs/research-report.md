# Oral Cancer Detection Platform — Research Report

Oct 13, 2026 · Live version with charts: https://claude.ai/code/artifact/3a6a015a-612f-44a2-895b-6320fdd987c9

## Executive summary

The platform now works end to end with a real model: a clinician registers, uploads a lesion photo with patient context, and gets a ResNet-50 prediction, a Grad-CAM heatmap, a PDF report and a history entry. This was verified live in the browser on the `dev` branch.

The recommended model (round 4) wrongly calls **12.8%** of held-out client dysplasia photos "Cancer", down from 85.7% for the first model and 64.1% for round 2 on the same patients. On the public Kaggle test set it reaches 91.1% accuracy but detects only **84.3%** of cancers.

The biggest finding was a correction: the client's two image folders, earlier judged unlabeled, match the treatment spreadsheet row for row. That doubled the client data to 198 photos from 100 patients.

A full audit found and fixed 9 defects, including two that exposed patient data at guessable public URLs, and added the project's first 14 automated tests.

**Verdict:** a working research platform, not a validated diagnostic tool. Cancer-detection sensitivity on the client's own photos cannot be measured (one carcinoma case), and the sensitivity-versus-false-alarm trade-off needs a clinical decision.

## Scope and client requirements

Every confirmed client requirement is now implemented; two are met only at research grade.

| Requirement (client-confirmed) | Status | Where it stands |
| --- | --- | --- |
| Secure authentication | Met | JWT (PyJWT, HS256, expiring) + bcrypt; per-user data isolation tested |
| Clinical image upload | Met | Type and size validation on client and server; EXIF orientation handled |
| Patient context (multimodal input) | Met | 12-field schema, validated on both sides, stored and shown on reopen |
| Cancer / Non-Cancer prediction | Research grade | ResNet-50 round 4; sensitivity limits below |
| Confidence score | Research grade | Shown as a gauge; probabilities are not yet calibrated |
| Explainability heatmap | Met | Grad-CAM on `layer4`, overlaid on the photo |
| Prediction history | Met | Per-user list, dashboard counts, reopen any analysis |
| Downloadable PDF report | Met | Photo, heatmap, prediction, patient context, disclaimer; authenticated only |
| Database persistence | Met | PostgreSQL 16 with Alembic migrations; SQLite fallback |
| Cloud deployment | Not started | Docker image and Compose exist; no cloud environment yet |

The patient metadata fields were designed by the development team, not taken from a client specification, and should be confirmed with the client.

## Data

Training combines a public Kaggle set with 198 client photos from 100 patients; the client data is almost entirely precancerous.

| Source | Content | Labels | Role |
| --- | --- | --- | --- |
| Kaggle `zaidpy/oral-cancer-dataset` (v2.0) | 900 unique photos after deduplication (467 Cancer, 433 Non-Cancer) | Folder names | Main training set; 70/15/15 split |
| Client treatment spreadsheet | 164 patient rows; 100 with embedded clinical + histopath photos | Histopathology diagnosis per row | Labels for all client photos |
| Client folders (`N c p`, `N H`) | 100 clinical + 100 histopath photos | Via the spreadsheet (see below) | Second clinical photo per patient |

**Client cohort by histopathology:** 24 mild, 39 moderate and 36 severe dysplasia, and 1 carcinoma. Labels are binary: only SCC or carcinoma counts as Cancer, so 99 of 100 patients are Non-Cancer.

**Correction to an earlier conclusion.** The folders were first judged unlabeled because no folder clinical photo matched a spreadsheet photo, even allowing rotation and mirroring. Comparing the histopathology slides instead settled it: 99 of 100 folder slides are pixel-identical to the spreadsheet's (correlation 1.000), and all follow **folder case N = spreadsheet row N+1**. The folder clinical photos are different shots of the same lesions. Case 12's slide does not match, so its folder photo is excluded.

**Patient data handling.** The spreadsheet holds names, an 11-digit ID and clinical notes. It is never copied into the repository; extraction scripts write only image bytes, a binary label, a coarse diagnosis group and a case index, all gitignored. Every split is by patient, so two photos of one lesion never land on both sides.

## Model development

Four training rounds cut the false-Cancer rate on real client photos from 85.7% to 12.8%; the fix that worked was training on the client's photo domain, not more model capacity.

All rounds fine-tune an ImageNet-pretrained ResNet-50 (`layer4` and the classifier head), on CPU, 15 epochs, keeping the checkpoint with the best validation accuracy.

| Round | What changed | Client false-Cancer rate | Kaggle accuracy | Kaggle cancer sensitivity |
| --- | --- | --- | --- | --- |
| 1 | Kaggle only | 85.7% (all 98 Non-Cancer spreadsheet photos) | 92.6% | 90.0% |
| 2 | + 79 spreadsheet photos in training | 64.1% (39 photos, 20 held-out patients) | 89.6% | 92.9% |
| 3 | + 4x client oversampling, `layer3` unfrozen | 35.0% (20 spreadsheet photos only) | 94.1% | 92.9% |
| **4** | + folder photos, patient-level split | **12.8% (same 39 photos as round 2)** | 91.1% | **84.3%** |

- **Round 1** scored almost every client photo as near-certain cancer: a domain-shift failure, not a threshold problem.
- **Round 2** looked like 30% on spreadsheet photos, but flagged all 19 folder photos of its held-out patients, a second capture domain it never saw.
- **Round 3** was a negative result: extra capacity fit the still-dominant Kaggle data more tightly.
- **Round 4** sees both client capture sources in training and is compared with round 2 on the identical 20 held-out patients. Its cost is sensitivity: it misses 11 of 70 Kaggle cancers at the default threshold.

Rounds 2 and 4 share a held-out set; rounds 1 and 3 were measured on different subsets, so their client numbers are indicative only.

## Clinical analysis

Round 4's remaining client errors concentrate on the highest-risk lesions, and no decision threshold improves cancer detection without a large rise in false alarms.

| Held-out histopathology | Photos called Cancer (round 4) |
| --- | --- |
| Mild dysplasia | 0 of 16 |
| Moderate dysplasia | 2 of 14 |
| Severe dysplasia | 3 of 9 |

Severe versus mild is significant at p = 0.037 (Fisher, one-sided); moderate and severe versus mild gives p = 0.058. The sample is small, so this is suggestive. The first model showed no such pattern: it called 90–96% of photos Cancer at every grade (Spearman ρ = 0.11, p = 0.12).

Operating points, chosen on the validation set (70 Kaggle cancers, 40 client photos):

| Cancer threshold | Validation sensitivity | Validation client false alarms |
| --- | --- | --- |
| 0.50 (default) | 80.0% | 12.5% |
| 0.40 | 82.9% | 15.0% |
| 0.30 | 82.9% | 17.5% |
| 0.20 | 82.9% | 30.0% |
| 0.15 | 84.3% | 30.0% |
| 0.10 | 88.6% | 37.5% |

Applied once to the test set, the same range moves Kaggle cancer sensitivity from 84.3% (threshold 0.5) to 95.7% (0.1), while held-out client false alarms rise from 12.8% to 23.1%. The backend's `CANCER_THRESHOLD` setting stays at 0.5 until the client chooses an operating point.

## Software audit

The audit found 9 defects, two of them privacy exposures; all are fixed, and the 6 backend and model defects are covered by new automated tests (the frontend has none yet).

| Area | Defect | Impact | Fix |
| --- | --- | --- | --- |
| Privacy | PDF reports written inside the public `/uploads` folder at `reports/{id}.pdf` | Anyone could download any patient's report by guessing a number | Reports moved to a private `REPORT_DIR`, served only by the authenticated endpoint, regenerated if missing |
| Privacy | Heatmaps (which overlay the patient photo) named `{prediction_id}.png` | Every patient photo enumerable by number | Random, unguessable file names |
| Backend | Report link only set after the first download, and the button is disabled without it | Reports could never be downloaded from the UI | Link set whenever a prediction is complete |
| Backend | Upload folder created after the static mount that needs it | A fresh clone crashed on startup | Folder created before mounting |
| Backend | Any JSON accepted as patient metadata | Unvalidated data stored and printed into reports | Server-side schema mirroring the frontend form |
| Model | Photo EXIF orientation ignored | Phone photos classified sideways; heatmap and PDF rotated | Orientation applied before inference and in reports |
| Frontend | Report download failed silently | A click did nothing on any error | Loading state and visible error messages |
| Frontend | Stored patient metadata ignored when reopening an analysis | History showed "not stored on the server", which was false | Result page uses the stored copy |
| Frontend | Probabilities rounded to whole percent | 99.8% displayed as "100%", implying certainty | Shown as ">99%" and "<1%" |

Gaps closed alongside: a reproducible ML environment (`ml/requirements.txt`), corrected configuration examples, a project README, readable report labels, and a configurable decision threshold (`CANCER_THRESHOLD`).

## End-to-end verification

The full clinician workflow was run live in a browser with the round 4 model loaded, and every step behaved correctly.

| Step | Input | Result |
| --- | --- | --- |
| Register and sign in | New account | Redirected to the dashboard |
| Upload + patient context | Held-out client photo, mild dysplasia, 12 metadata fields | Non-Cancer (correct), heatmap shown, report enabled |
| Upload | Kaggle test cancer photo | Non-Cancer at 52%, flagged "low confidence": a real missed cancer |
| Upload | A second Kaggle cancer photo | Cancer, 98%, high confidence |
| Download report | Button on the result page | 1 MB PDF with photo, heatmap, labelled metadata, disclaimer |
| Public report URL | `/uploads/reports/1.pdf` | 404, as intended |
| History and dashboard | Three analyses | Correct rows and counts (1 Cancer, 2 Non-Cancer) |
| Reopen analysis | `/predictions/1` loaded fresh | Stored patient context displayed |

Automated checks: 14 backend tests pass, and the frontend type-checks, lints and builds cleanly. The live run used the SQLite fallback because Docker did not start on this machine; PostgreSQL was verified live earlier in the project, and no database schema changed in this round. Test photos and generated files were deleted after the run.

## Existing limitations

The largest limitation is data: the client cohort contains one confirmed cancer, so the model's ability to catch cancer in the client's own photos is unknown.

**Data**

- One carcinoma among 100 client patients; all client metrics are false-alarm rates on dysplasia.
- 100 patients from one source and one clinical setting; no external site, camera or population.
- Kaggle images come from mixed, partly web-sourced origins, and 8% of one class were duplicates before cleaning.

**Model**

- Kaggle cancer sensitivity is 84.3% at the default threshold: about 1 in 6 cancers missed.
- Probabilities are uncalibrated and overconfident (99.8% on a routine case); scores should not be read as true likelihoods.
- Binary labels flatten graded histopathology; severe dysplasia is treated as Non-Cancer.
- Image only: patient metadata is stored and reported but not used by the model, so the system is not yet multimodal in its predictions.
- Grad-CAM shows where the model looked, not a lesion margin; heatmaps were spot-checked, not systematically validated.

**Clinical and regulatory**

- Not a medical device; no clinical validation, ethics approval or regulatory pathway has been started.
- The patient metadata fields were chosen by the development team and are unconfirmed by the client.

**Infrastructure**

- Images and heatmaps sit on local disk behind unguessable URLs, not authenticated or encrypted storage.
- Synchronous CPU inference (seconds per upload) suits a research pilot, not high volume.
- No cloud deployment, monitoring, backups or frontend tests.

## Recommendations and next steps

The next gains come from the client's data and clinical decisions, not more engineering; ordered by impact:

1. **Collect confirmed-cancer photos from the client's own clinic** (ideally 50+ patients, with histopathology). This is the only way to measure, and then improve, cancer detection on their photos.
2. **Agree the operating point with the clinical lead**, using the threshold table above, and set `CANCER_THRESHOLD` accordingly.
3. **Decide how high-grade dysplasia should be reported.** The data is graded and round 4's flags already lean toward severe cases; a three-level output (Non-Cancer / high-risk lesion / Cancer) may fit the clinic better than binary.
4. **Calibrate probabilities** with temperature scaling on the validation set, so displayed confidence means what it says.
5. **Confirm the patient metadata fields with the client**, then decide whether the model should use them.
6. **Before any real-patient use:** authenticated media storage, cloud deployment with backups and monitoring, frontend tests, and an ethics and regulatory review.

## Appendix: commits on `dev`

This round's commits in conventional format, newest first, on top of the earlier training rounds (`f5ddd2e`); this report is added in the commit after `0a542eb`.

| Commit | Message |
| --- | --- |
| `0a542eb` | docs: add project README with setup, training, testing and data handling |
| `82be797` | fix(web): never display model probabilities as 100% or 0% |
| `ad9c700` | docs(ml): add round 4 results, correct folder labeling finding, document thresholds |
| `fcdc49a` | feat(inference): make the cancer decision threshold configurable |
| `50d7966` | docs(config): document REPORT_DIR and MODEL_PATH, fix stale env examples |
| `662f8de` | chore(ml): pin training environment dependencies |
| `ddeef3f` | feat(ml): add patient-level train/val/holdout split reusing round 2 holdout |
| `a197ac4` | feat(ml): build case-level client dataset from both spreadsheet and folder photos |
| `1666f7a` | fix(web): show stored patient metadata when reopening a past analysis |
| `6e8c923` | fix(web): show report download errors and a loading state instead of failing silently |
| `e0bd47b` | test(api): add pytest suite for auth, uploads, metadata, isolation and reports |
| `ad097b8` | fix(reports): print upright photos and readable metadata, survive unreadable images |
| `a83530e` | fix(inference): respect exif orientation when classifying uploads |
| `6045f85` | fix(api): make reports downloadable and keep patient data off guessable public urls |
| `b3b1257` | feat(api): validate patient metadata against a schema at upload |

Trained weights and all client-derived images are gitignored and are not in any commit; the full model history is in `ml/artifacts/model_card.md`.
