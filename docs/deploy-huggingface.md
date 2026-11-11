# Free deployment: API on Hugging Face Spaces, web app on Vercel

A no-cost way to give people a working link for demonstrations. Render's free
plan cannot run the models (512 MB memory against about 1 GB needed);
Hugging Face's free CPU Spaces give 16 GB.

## Read first

- **Demo only, not patient data.** Free tiers have no guarantees, and Hugging
  Face's servers are not in India.
- **A public Space shows its source code.** The Space has to be public so the
  Vercel site can call it, and anyone can then read the API code, including the
  triage method and thresholds. The model files stay private (they live in a
  separate private repository). Decide about the patent first if that matters.
- **The free Space sleeps** after about 48 hours without visitors; the first
  request afterwards takes 30 to 60 seconds.
- **The free disk is wiped on every restart.** With the default SQLite
  database, accounts and results disappear then. To keep them, use a free
  Postgres database (step 6).
- **The Docker image has not been built on the developer's machine** (Docker
  Desktop would not start). The app itself was tested locally in the same
  production mode and settings. If the first Space build fails, the build log
  names the step.

## 1. Accounts and tools (once)

1. Create a free account at https://huggingface.co and note your username.
2. Create an access token with write access at
   https://huggingface.co/settings/tokens.
3. In a terminal (Command Prompt or PowerShell):

   ```
   pip install -U huggingface_hub
   hf auth login
   ```

   Paste the token when it asks. Do not share it with anyone.

## 2. Upload the models to a private repository

Replace `YOURNAME` with your Hugging Face username:

```
hf repos create oralsentinel-models --repo-type model --private
hf upload YOURNAME/oralsentinel-models C:\Dev\multimodal-dl-oral-cancer-detection\mlrtifacts . --include "resnet50_oral_cancer_v7.pt" --include "oral_photo_gate_v1.pt" --include "resnet50_dysplasia_grade_v2.pt"
```

Check it is really private: this must print `401` (200 would mean public):

```
curl -s -o NUL -w "%{http_code}" https://huggingface.co/api/models/YOURNAME/oralsentinel-models
```

If it prints 200, run `hf repos settings YOURNAME/oralsentinel-models --private`
and check again. (If the `create` line fails, `hf upload` quietly creates a
**public** repo, so always run this check.)

Then create a **read-only** token for the Space: at
https://huggingface.co/settings/tokens choose New token > Fine-grained, give
it read access to `YOURNAME/oralsentinel-models` only, and copy it. This is
the `HF_TOKEN` in step 4.

## 3. Create the Space and push the code

Build the Space folder from the repository, then push it:

```
python C:\Dev\multimodal-dl-oral-cancer-detection\deploy\huggingface\build_space.py --out C:\Dev\oralsentinel-space
hf repos create oralsentinel-api --repo-type space --sdk docker
cd C:\Dev\oralsentinel-space
git init -b main
git add .
git commit -m "OralSentinel API"
git remote add space https://huggingface.co/spaces/YOURNAME/oralsentinel-api
git push space main
```

When git asks for a password, use your **write** token (username: your
Hugging Face username). The first push starts a build; do step 4 while it runs.

## 4. Space settings

Open https://huggingface.co/spaces/YOURNAME/oralsentinel-api > Settings.

**Variables**

| Name | Value |
|---|---|
| `MODEL_REPO` | `YOURNAME/oralsentinel-models` |
| `CORS_ORIGINS` | the Vercel address from step 5 (use `https://example.invalid` until you have it) |
| `APP_URL` | the same Vercel address |

**Secrets**

| Name | Value |
|---|---|
| `HF_TOKEN` | the read-only token from step 2 |
| `SECRET_KEY` | a random string; make one with `python -c "import secrets; print(secrets.token_urlsafe(48))"` (without it, everyone is signed out at each restart) |

After saving, the Space rebuilds. It is ready when
`https://YOURNAME-oralsentinel-api.hf.space/config/public` shows a short line
of text (JSON). Start-up takes about a minute: it downloads the models, then
loads them.

## 5. The web app on Vercel

1. Go to https://vercel.com, sign in with GitHub, and choose Add New > Project
   > import `Vani-06/oral_cancer_detecting` (give Vercel access to that
   repository only).
2. Set **Root Directory** to `frontend`.
3. Add the environment variable `VITE_API_BASE_URL` with the Space address:
   `https://YOURNAME-oralsentinel-api.hf.space` (no trailing slash).
4. Deploy. Copy the address Vercel gives you.

## 6. Connect them, and (optionally) keep the data

1. In the Space settings, change `CORS_ORIGINS` and `APP_URL` to the Vercel
   address (no trailing slash). The Space restarts.
2. Open the Vercel address, create an account, and run one analysis. That
   address is the link to send to people.

To keep accounts and results across restarts, create a free Postgres database
at https://neon.tech, copy its connection string, and add it as a Space secret
named `DATABASE_URL`, ending with `?sslmode=require`. The tables are created
on the next start.

## Updating

Run `build_space.py` again, then in `C:\Dev\oralsentinel-space` run
`git add .`, `git commit -m "update"` and `git push space main`. The Vercel
site updates itself when `main` changes.
