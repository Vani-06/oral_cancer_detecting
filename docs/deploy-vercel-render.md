# Deploying on Vercel (web app) and Render (API and database)

The web app is a static site, which suits Vercel. The API loads three neural
networks and needs a database and a disk, which suits Render. Google Cloud in
Mumbai (`deploy/gcp/`) remains the option that keeps data in India.

A no-cost alternative for demonstrations: `docs/deploy-huggingface.md`.

## Before you start

- **Render has no India region.** The blueprint uses Singapore, so photos and
  patient details stored there leave India. Use this deployment for
  demonstrations and synthetic or consented test data until legal advice on
  the DPDP Act says otherwise (`docs/data-protection-and-security.md`).
- **The free Render plan cannot run the API.** The three networks need 0.6 GB
  of memory after loading and 0.94 GB at peak; free and Starter instances
  have 512 MB.
- **The Docker image has not been built on this machine** (Docker Desktop
  would not start), so the first Render build is its first real build. If it
  fails, the build log names the step.

## Cost (check Render's pricing page before confirming)

| Item | Plan | About |
|---|---|---|
| API on Render | Standard, 2 GB memory | $25 / month |
| Postgres on Render | Basic 256 MB | $6 / month |
| Disk for photos on Render | 1 GB | $0.25 / month |
| Web app on Vercel | Hobby | Free (non-commercial use only) |

## The branch to deploy

Deploy the `main` branch of the private repository
(https://github.com/Vani-06/oral_cancer_detecting). It includes the three
model files (90 to 93 MB each), which the Docker build copies into the
image. Keep this repository private: the models were trained on clinic
photos.

## 1. API and database on Render

1. Sign in at https://dashboard.render.com with GitHub and give Render access
   to the private repository only.
2. New > Blueprint > choose the repository and the branch `main`.
   Render reads `render.yaml` and lists one web service, one database and one
   disk.
3. It asks for two values. Enter a placeholder for both for now, for example
   `https://example.invalid`; step 3 below replaces them.
   - `CORS_ORIGINS`
   - `APP_URL`
4. Apply. The first build takes 10 to 15 minutes (it installs PyTorch). The
   service is ready when `https://<your-service>.onrender.com/config/public`
   returns JSON.

## 2. Web app on Vercel

1. Sign in at https://vercel.com with GitHub. Add New > Project > import the
   same repository.
2. Set **Root Directory** to `frontend`. The production branch is `main`.
3. Add one environment variable:
   - `VITE_API_BASE_URL` = the Render address from step 1, without a trailing
     slash, e.g. `https://oralsentinel-api.onrender.com`
4. Deploy. Note the address Vercel gives the site, e.g.
   `https://oralsentinel.vercel.app`.

## 3. Connect the two

In Render > oralsentinel-api > Environment, set both of these to the Vercel
address (no trailing slash), then save; the service restarts:

- `CORS_ORIGINS`
- `APP_URL`

Open the Vercel address, create an account and run one analysis.

## Settings you may want to change on Render

| Setting | Default in `render.yaml` | Change when |
|---|---|---|
| `REGISTRATION_MODE` | `open` | Set `invite` (codes from `scripts/create_invite.py` in the Render shell) or `domain` with `ALLOWED_EMAIL_DOMAINS` to restrict who can sign up |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | not set | Needed for password-reset emails; without them the reset page says it is not set up |
| `RETENTION_DAYS` | `0` (keep) | A retention period is agreed |
| `ANALYSIS_PAUSED` | `false` | A serious incident (`docs/incident-and-breach-response.md`) |

## Updating

Auto-deploy is off on Render. After pushing new work to `main`, press
Manual Deploy on Render; Vercel redeploys the web app by itself.
