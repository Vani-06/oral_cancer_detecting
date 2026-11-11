#!/bin/sh
# Start-up for the Hugging Face Space: fetch the models, prepare the
# database, run the API on the port Spaces expects (7860).
set -e

python fetch_models.py
export MODEL_PATH="$MODEL_DIR/resnet50_oral_cancer_v7.pt"
export GATE_MODEL_PATH="$MODEL_DIR/oral_photo_gate_v1.pt"
export GRADING_MODEL_PATH="$MODEL_DIR/resnet50_dysplasia_grade_v2.pt"

if [ -z "$SECRET_KEY" ]; then
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  export SECRET_KEY
  echo "SECRET_KEY is not set: made one for this run, so everyone is signed out at each restart. Set it as a Space secret to avoid that."
fi

case "$DATABASE_URL" in
  sqlite*)
    # Free Spaces lose their disk on restart, so a SQLite database starts empty each time.
    export AUTO_CREATE_TABLES=true ;;
  *)
    export AUTO_CREATE_TABLES=false
    alembic upgrade head ;;
esac

exec uvicorn app.main:app --host 0.0.0.0 --port 7860 --proxy-headers --forwarded-allow-ips='*'
