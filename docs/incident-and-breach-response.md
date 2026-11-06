# Incident and breach response

How problems with OralSentinel are reported, judged and fixed: wrong results
(clinical incidents) and security or data incidents. Written for review items
49 and 50. Roles are filled in by the project before any real patient data is
used; until then the project lead holds all of them.

| Role | Responsibility |
|---|---|
| Clinical lead | Judges clinical incidents; decides whether to pause the tool |
| Technical lead | Investigates, fixes, deploys, keeps the incident log |
| Data protection contact | Decides on notification of patients and authorities |

## 1. Clinical incidents (a wrong or harmful result)

**How they arrive.** Clinicians use "Report a wrong result" on the result page
(stored with the analysis: what was wrong, the actual diagnosis, a comment), or
contact the team directly.

**Review.** The technical lead reviews new reports every week.

- The analysis version stored with the result identifies the exact model
  files, temperature and thresholds used.
- The access log shows what was viewed and when.

**Severity**

| Level | Example | Action |
|---|---|---|
| Serious | A cancer later confirmed by biopsy was called "no cancer" | Clinical lead told within 1 working day. Decide whether to pause new analyses: set `ANALYSIS_PAUSED=true` and redeploy (uploads are refused with an explanation; past results and reports stay readable). Root-cause review within 2 weeks. |
| Moderate | A clear non-cancer called "cancer"; a good photo refused | Logged and reviewed monthly for patterns (site, camera, lighting). |
| Minor | A wrong dysplasia grade | Logged; the grade is already labelled low reliability. |

**Fixing.** A fix that changes results needs the following before release:

- A new model file name.
- A passing regression test (`backend/tests/test_model_regression.py`, with
  expected values updated only on purpose).
- Re-checked triage thresholds (`ml/scripts/conformal_triage.py`).
- An entry in the model card.

The analysis version then changes on every new result, so old and new
results can be told apart.

## 2. Security and data incidents

Examples: an unexpected sign-in in a user's access log, a lost laptop with
exported reports, a leaked secret, a vulnerability report, or data visible
to the wrong user.

1. **Contain (same day).** Depending on the incident:
   - Rotate `SECRET_KEY`. This signs everyone out, because all sessions are
     JSON Web Tokens signed with it.
   - Reset affected passwords with `backend/scripts/reset_password.py`.
   - Turn off public sign-up (`ALLOW_REGISTRATION=false` or
     `REGISTRATION_MODE=invite`).
   - If needed, stop the service. On Cloud Run, set traffic to zero or
     remove public access.
2. **Assess (within 24 hours).** Use the access log (`audit_events`: user,
   action, analysis, IP, time) and the cloud logs to work out:
   - which accounts and analyses were involved;
   - whether patient photos or details were viewed or copied;
   - for how long.
3. **Notify.** The data protection contact decides, with legal advice, who
   must be told and when. The following timelines must be confirmed by legal
   advice before deployment:
   - Under the Digital Personal Data Protection Act 2023 and its Rules, a
     personal data breach is reported to the Data Protection Board and to the
     affected people.
   - CERT-In's 2022 directions require certain cyber incidents to be
     reported within 6 hours of being noticed.
   - The hospital's own incident policy and the ethics committee also apply
     to research data.
4. **Fix and learn (within 2 weeks).** Close the cause, add a test that would
   have caught it, record the incident in the log below, and update
   `docs/data-protection-and-security.md`.

## 3. Incident log

| Date | Type | Summary | Data affected | Action | Closed |
|---|---|---|---|---|---|
| Before deployment | Security (internal audit) | Report and heatmap URLs were guessable in local development builds | None: never deployed to a reachable server | Files served only through authenticated, owner-checked endpoints; tested | Yes |
| 6 Nov 2026 | Defect (end-to-end test) | Follow-up and delete buttons blocked by cross-origin rules | None | CORS allows PATCH and DELETE; backend test added | Yes |
