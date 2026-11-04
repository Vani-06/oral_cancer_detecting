# API image with the three models built in. Build from the repository root:
#   docker build -f deploy/api.Dockerfile -t oralsentinel-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic.ini .
COPY backend/alembic ./alembic
COPY ml/artifacts/resnet50_oral_cancer_v7.pt ml/artifacts/oral_photo_gate_v1.pt ml/artifacts/resnet50_dysplasia_grade_v2.pt /models/

ENV ENVIRONMENT=production \
    AUTO_CREATE_TABLES=false \
    MODEL_PATH=/models/resnet50_oral_cancer_v7.pt \
    GATE_MODEL_PATH=/models/oral_photo_gate_v1.pt \
    GRADING_MODEL_PATH=/models/resnet50_dysplasia_grade_v2.pt \
    UPLOAD_DIR=/data/uploads \
    REPORT_DIR=/data/reports

EXPOSE 8080
# --proxy-headers: behind Cloud Run's front end, the client address used by
# the sign-up and sign-in limits comes from X-Forwarded-For.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
