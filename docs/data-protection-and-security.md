# Data protection and security status

What the application stores, how it is protected, and what is still missing
before real patient data is used. Written in response to the external review
(items 45, 46, 50 and 53).

## What is stored

| Data | Where | Notes |
|---|---|---|
| Clinician account: name, email, bcrypt password hash | Database (`users`) | No plain-text passwords |
| Analyses: photo file name, results, model version, patient details (age, sex, habits, site, symptoms, history, notes) | Database (`predictions`) | No patient name field; an optional free-text patient reference |
| Lesion and reference photos, heatmaps | `UPLOAD_DIR` (a private Cloud Storage bucket in the cloud deployment) | Random file names; served only to the uploading clinician |
| PDF reports | `REPORT_DIR` | Generated on demand, served only to the uploading clinician |

## In place

- Every photo, heatmap and report is served only through authenticated
  endpoints to the clinician who uploaded it (tested).
- Passwords hashed with bcrypt; sessions are expiring JWTs; sign-in lock-out
  after repeated failures; sign-up and upload rate limits.
- Sign-up requires confirming professional use and patient consent.
- Strict validation of all patient details and uploaded files.
- Cloud deployment (Google Cloud, Mumbai): Cloud SQL and Cloud Storage
  encrypt data at rest by default; the bucket blocks public access; daily
  database backups; secrets in Secret Manager.
- Every result records the model files and thresholds that produced it.

## Not yet in place (required before real patient data)

| Gap | Proposed fix |
|---|---|
| No verification that a user is a clinician | Invite-only accounts or institutional email check |
| No multi-factor authentication or self-service password reset | Add TOTP MFA and an email reset flow; until then, admins reset with `backend/scripts/reset_password.py` |
| No audit log of who viewed or downloaded what | Application-level access log |
| No retention or deletion policy; no delete-my-data function | Agree retention with the clinical lead; add deletion of an analysis and its files |
| Consent is a self-declaration only | Record consent per patient, per the ethics approval |
| Local development and non-Google options have no encryption at rest or backups | Use encrypted disks and scheduled backups on any other host |
| Security reviewed internally only | Independent penetration test before real patient data |
| Legal basis under the DPDP Act 2023 not assessed | Legal advice; data residency in India is currently a policy choice |

## Past exposure (review item 50)

The guessable report and heatmap URLs found in the internal audit existed only
in local development builds. The application has not been deployed to any
publicly reachable server, so no patient data was exposed through them.
