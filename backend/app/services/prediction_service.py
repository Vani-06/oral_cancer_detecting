import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Prediction, Report, User
from app.services.inference_service import inference_service

# Far above any clinical photo (12-50 MP is typical; 108 MP phone sensors are
# the outlier), but low enough that a crafted "decompression
# bomb" -- a tiny file that expands to gigabytes -- is rejected before decode.
MAX_IMAGE_PIXELS = 120_000_000


class PredictionService:
    """Handles prediction-related business logic.

    Currently persists uploaded images and creates pending prediction rows.
    The inference path remains replaceable for later ML integration.
    """

    def __init__(self, db: Session) -> None:
        self.db: Session = db
        self.upload_dir: Path = settings.UPLOAD_DIR
        self._ensure_upload_dir()

    def _ensure_upload_dir(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _validate_file(self, file: UploadFile) -> None:
        if file.filename is None:
            raise ValueError("No filename provided.")

        extension = Path(file.filename).suffix.lower()
        if extension not in settings.ALLOWED_EXTENSIONS:
            allowed_types = ", ".join(sorted(settings.ALLOWED_EXTENSIONS))
            raise ValueError(
                f"Unsupported file type '{extension}'. Allowed types: {allowed_types}"
            )

        if file.content_type and not file.content_type.startswith("image/"):
            raise ValueError("The uploaded file must be an image.")

        current_position = file.file.tell()
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(current_position)
        if file_size > settings.max_file_size_bytes:
            raise ValueError(
                f"File too large. Maximum allowed size is {settings.MAX_FILE_SIZE_MB} MB."
            )

    def save_image(self, file: UploadFile) -> str:
        self._validate_file(file)

        if file.filename is None:
            raise ValueError("No filename provided.")

        extension = Path(file.filename).suffix.lower()
        filename = f"{uuid4()}{extension}"
        destination = self.upload_dir / filename

        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer, length=1024 * 1024)

        # The initial size check can be bypassed by streamed uploads whose
        # file pointer does not expose the complete content length.
        if destination.stat().st_size > settings.max_file_size_bytes:
            destination.unlink(missing_ok=True)
            raise ValueError(
                f"File too large. Maximum allowed size is {settings.MAX_FILE_SIZE_MB} MB."
            )

        # The extension and Content-Type are client-supplied; confirm the bytes
        # are really an image before storing them or handing them to the model.
        try:
            self._verify_image(destination)
        except ValueError:
            destination.unlink(missing_ok=True)
            raise

        return filename

    @staticmethod
    def _verify_image(path: Path) -> None:
        try:
            with Image.open(path) as im:
                width, height = im.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image dimensions are too large.")
                im.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
            raise ValueError("The uploaded file is not a readable image.") from exc

    def create_prediction(
        self, user: User, file: UploadFile, metadata: dict | None = None
    ) -> Prediction:
        filename = self.save_image(file)
        prediction = Prediction(
            user_id=user.id,
            filename=filename,
            image_path=str(self.upload_dir / filename),
            metadata_json=metadata,
        )
        self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)

        # Inference runs synchronously, after the record is committed, so a
        # slow or failing model never blocks the upload itself from being
        # recorded. If no model is configured (inference_service.enabled is
        # False), the record stays Pending exactly as before real inference
        # existed -- this is the deliberate fallback path, not an error.
        if inference_service.enabled:
            # Random, like uploaded image names: the heatmap overlays the
            # patient's photo. It is only served through the authenticated
            # heatmap endpoint, but an unguessable name is defence in depth
            # if the directory is ever exposed by a misconfigured proxy.
            heatmap_filename = f"{uuid4().hex}.png"
            heatmap_path = self.upload_dir / "heatmaps" / heatmap_filename
            result = inference_service.predict(
                image_path=self.upload_dir / filename,
                heatmap_output_path=heatmap_path,
            )
            prediction.prediction = result.label
            prediction.confidence = result.confidence
            prediction.dysplasia_grade = result.dysplasia_grade
            prediction.heatmap_path = heatmap_filename
            self.db.commit()
            self.db.refresh(prediction)

        return prediction

    def list_predictions(self, user: User) -> list[Prediction]:
        stmt = (
            select(Prediction)
            .where(Prediction.user_id == user.id)
            .order_by(desc(Prediction.created_at), desc(Prediction.prediction_id))
        )
        return list(self.db.scalars(stmt).all())

    def get_prediction(self, prediction_id: int, user: User) -> Prediction | None:
        stmt = select(Prediction).where(
            Prediction.prediction_id == prediction_id,
            Prediction.user_id == user.id,
        )
        return self.db.scalar(stmt)

    def get_report(self, prediction_id: int, user: User) -> Report | None:
        prediction = self.get_prediction(prediction_id, user)
        if prediction is None:
            return None
        return prediction.report
