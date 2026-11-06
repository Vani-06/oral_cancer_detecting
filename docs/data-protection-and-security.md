# Data protection and security status

What the application stores, how it is protected, and what is still missing
before real patient data is used. Written in response to the external review
(items 45, 46, 50 and 53).

## What is stored

| Data | Where | Notes |
|---|---|---|
| Clinician account: name, email, bcrypt password hash, two-factor secret (if on), hashed one-time reset token | Database (`users`) | No plain-text passwords or tokens |
| Access log: who signed in, uploaded, viewed, downloaded, followed up, deleted; time and IP | Database (`audit_events`) | Kept when an analysis is deleted, so deletions stay accountable |
| Follow-up status and note, consent time, wrong-result reports | Database (`predictions`, `result_feedback`) | |
| One-time invitation codes | Database (`invites`) | Stored hashed |
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
- Every result records the model files, temperature and thresholds that produced it.
- Sign-up can be limited to invited clinicians (`REGISTRATION_MODE=invite`,
  codes from `backend/scripts/create_invite.py`) or institutional email
  domains (`REGISTRATION_MODE=domain`, `ALLOWED_EMAIL_DOMAINS`).
- Optional two-factor sign-in (authenticator app, RFC 6238), turned on per
  account from the Account page.
- Self-service password reset by a one-time emailed link (needs `SMTP_*`
  settings; refused in production without them).
- Access log of every sign-in (including failed ones), upload, view, download,
  follow-up change and deletion; each user can read their own on the Account page.
- Each upload requires the clinician to confirm the patient's consent; the
  time is stored with the analysis and shown on the result.
- A clinician can permanently delete an analysis with its photos, heatmap and
  report. `backend/scripts/purge_expired.py` deletes analyses older than
  `RETENTION_DAYS` (0 = keep); schedule it daily once the period is agreed.
- Photos too dark, washed out or blurred to analyse are refused with a reason.
- Incident and breach response: see `docs/incident-and-breach-response.md`.

## Not yet in place (required before real patient data)

| Gap | Proposed fix |
|---|---|
| Invite / domain sign-up exists but who may be invited is not decided | Clinical lead decides; run with `REGISTRATION_MODE=invite` |
| Two-factor sign-in is optional | Make it mandatory once all users have set it up |
| Retention period not agreed | Clinical lead and ethics committee set `RETENTION_DAYS` |
| Consent is the clinician's confirmation per upload, not a signed patient form | Keep the signed form in the clinic record, per the ethics approval |
| Local development and non-Google options have no encryption at rest or backups | Use encrypted disks and scheduled backups on any other host |
| Security reviewed internally only | Independent penetration test before real patient data |
| Legal basis under the DPDP Act 2023 not assessed | Legal advice; data residency in India is currently a policy choice |

## Past exposure (review item 50)

The guessable report and heatmap URLs found in the internal audit existed only
in local development builds. The application has not been deployed to any
publicly reachable server, so no patient data was exposed through them.
