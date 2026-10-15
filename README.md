# Multimodal Oral Cancer Detection

Research web platform for AI-assisted oral lesion assessment: clinicians
upload a clinical photo plus structured patient context, and receive a
Cancer / Non-Cancer prediction, a confidence score, a Grad-CAM heatmap, and a
downloadable PDF report, with per-user history.

> **Research prototype, not a medical device.** The current model has
> documented limitations on real clinical photos -- read
> [`ml/artifacts/model_card.md`](ml/artifacts/model_card.md) and
> [`docs/research-report.md`](docs/research-report.md) before enabling it.

## Architecture

| Part | Stack | Location |
|---|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind v4 | `frontend/` |
| API | FastAPI, SQLAlchemy 2, Alembic, JWT (PyJWT) + bcrypt | `backend/` |
| Database | PostgreSQL 16 (Docker), SQLite fallback | `docker-compose.yml` |
| Model | ResNet-50 transfer learning + Grad-CAM, CPU inference | `backend/app/services/inference_service.py` |
| Training | PyTorch, separate environment | `ml/` |

Request flow: `POST /predict` stores the image and metadata, then (if a
model is configured) runs inference and Grad-CAM synchronously and stores the
result. Reports are generated on demand by `GET /reports/{id}` and are only
served through that authenticated endpoint.

## Running locally

**Database**

```bash
docker compose up -d db
```

Postgres listens on host port **5434** (not 5432, to avoid clashing with a
native install).

**Backend** (from `backend/`)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
cp .env.example .env
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

**Frontend** (from `frontend/`)

```bash
npm install
cp .env.example .env.local
npm run dev
```

App: http://localhost:5173

## Enabling the model

Predictions stay **Pending** until `MODEL_PATH` in `backend/.env` points at a
trained checkpoint. Weights are not committed (`ml/artifacts/` is
gitignored); train them with the scripts below or obtain them separately.

Set `GATE_MODEL_PATH` too (built by `ml/scripts/build_photo_gate.py`): it
refuses uploads that are not clinical photos of the mouth -- slides,
screenshots, blank images -- which the cancer model would otherwise label
anyway. See `ml/artifacts/model_card.md` for what each model can and cannot do.

## Training (from `ml/`)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/prepare_kaggle.py
.venv/Scripts/python.exe scripts/prepare_client_validation.py <treatment.xlsx>
.venv/Scripts/python.exe scripts/prepare_client_cases.py <treatment.xlsx> <clinical_dir> <histopath_dir>
.venv/Scripts/python.exe scripts/prepare_case_split.py
.venv/Scripts/python.exe scripts/train.py --train-dir data/case_split/train --val-dir data/case_split/val --checkpoint-name resnet50_oral_cancer_v4.pt
.venv/Scripts/python.exe scripts/evaluate.py --checkpoint artifacts/resnet50_oral_cancer_v4.pt --client-eval-dir data/case_split/holdout
```

`prepare_kaggle.py` needs a Kaggle API token in `~/.kaggle/access_token`.

## Tests

```bash
cd backend && .venv/Scripts/python.exe -m pytest
cd frontend && npx tsc -b && npm run lint && npm run build
```

## Client data handling

The client's treatment spreadsheet contains real patient identifiers. It is
never committed and never copied into the repository. The `ml/scripts/prepare_*`
scripts read it in place and write only image bytes, a binary label, a coarse
diagnosis group and a case index under `ml/data/` (gitignored). Splits are by
patient (case), never by image.
