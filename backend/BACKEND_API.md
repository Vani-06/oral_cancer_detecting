# Backend API

FastAPI service. When `ENVIRONMENT` is not `production`, interactive docs with
full request and response schemas are served at `/docs`.

Authentication is a bearer token from `/login` or `/register`:
`Authorization: Bearer <token>`. Every `/predictions/*` and `/reports/*`
endpoint returns only the signed-in clinician's own records (`404` otherwise).

## Accounts

| Method | Path | Notes |
|---|---|---|
| GET | `/config/public` | Sign-up mode (`open`, `invite`, `domain`) and whether email password reset is available |
| POST | `/register` | `email`, `password`, `full_name`, `confirms_professional_use: true`; `invite_code` when invite-only |
| POST | `/login` | `email`, `password`; `mfa_code` when two-factor sign-in is on (`403` asks for it) |
| GET | `/me` | Current user |
| GET | `/me/audit` | The user's latest 200 access-log events |
| POST | `/mfa/setup` | Returns a TOTP secret and `otpauth://` URI |
| POST | `/mfa/enable` | `code` |
| POST | `/mfa/disable` | `code`, `password` |
| POST | `/password-reset/request` | `email`; always `202`, emails a one-time link if the account exists |
| POST | `/password-reset/confirm` | `token`, `new_password` |

## Analyses

| Method | Path | Notes |
|---|---|---|
| POST | `/predict` | Multipart: `file` (photo), `consent_confirmed=true`, optional `reference_file` and `metadata_json`. Returns the result immediately. |
| GET | `/predictions` | The user's analyses, newest first |
| GET | `/predictions/{id}` | One analysis: result, grade, follow-up, consent time, model version |
| DELETE | `/predictions/{id}` | Deletes the analysis and its photos, heatmap and report |
| PATCH | `/predictions/{id}/follow-up` | `status`: `needed`, `referred`, `retake_requested`, `closed`; optional `note` |
| POST | `/predictions/{id}/feedback` | Report a wrong result: `kind`, optional `actual_diagnosis`, `comment` |
| GET | `/predictions/{id}/image` | Lesion photo |
| GET | `/predictions/{id}/reference-image` | Optional opposite-side photo |
| GET | `/predictions/{id}/heatmap` | Grad-CAM overlay |
| GET | `/reports/{id}` | PDF report, generated on first request |

`POST /predict` returns `400` with a reason when the image is not a clinical
oral photo or is too dark, washed out or blurred, `429` when the hourly limit
is reached, and `503` while `ANALYSIS_PAUSED` is set.

## Result fields

| Field | Values |
|---|---|
| `prediction` | `Cancer`, `Non-Cancer` (single-answer label) |
| `assessment` | `cancer`, `inconclusive`, `no_cancer` (three-level triage) |
| `dysplasia_grade` | `none`, `mild`, `moderate`, `severe` |
| `model_version` | Model files, temperature and triage thresholds used |

## Health

`GET /` and `GET /health` return `{"status": "healthy"}`.
