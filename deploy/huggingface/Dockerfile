# API image for a Hugging Face Docker Space. The build context is the folder
# made by deploy/huggingface/build_space.py (not the repository root).
# The three model files are NOT in the image: they are downloaded at start-up
# from a private Hugging Face model repository (see fetch_models.py).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Hugging Face runs Spaces as user 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
RUN mkdir -p /home/user/data /home/user/models

ENV ENVIRONMENT=production \
    ALLOW_REGISTRATION=true \
    REGISTRATION_MODE=open \
    MODEL_DIR=/home/user/models \
    UPLOAD_DIR=/home/user/data/uploads \
    REPORT_DIR=/home/user/data/reports \
    DATABASE_URL=sqlite:////home/user/data/oralsentinel.db

EXPOSE 7860
CMD ["sh", "entrypoint.sh"]
