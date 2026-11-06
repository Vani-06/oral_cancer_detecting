"""
Loads the trained ResNet-50 checkpoint (see ml/scripts/train.py) once at
startup and runs inference + Grad-CAM per upload.

Self-contained: does not import anything from ml/ (a separate, training-only
environment that isn't part of the deployed backend) -- the model
architecture and Grad-CAM logic are small enough to duplicate here rather
than couple the runtime service to the training toolchain's layout.

Two models, both ResNet-50 checkpoints in the same format:
- cancer detection (MODEL_PATH): Cancer / Non-Cancer, plus the Grad-CAM heatmap
- dysplasia grading (GRADING_MODEL_PATH, optional): none / mild / moderate / severe

plus an optional photo check (GATE_MODEL_PATH, a different format -- see
ml/scripts/build_photo_gate.py) that refuses images which are not clinical
photos of the mouth before either model sees them.

If MODEL_PATH is unset or the checkpoint file doesn't exist, `enabled` is
False and `predict()` is never called -- PredictionService leaves the record
Pending exactly as it did before real inference existed. This is a
deliberate fallback so local dev and any environment without the (large,
model-specific) weights file keeps working. Without a grading checkpoint,
predictions simply carry no grade.
"""

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageEnhance, ImageOps
from torchvision import transforms
from torchvision.models import resnet50

from app.core.config import settings

_GRADCAM_ALPHA = 0.45

# Grading checkpoint classes -> the short grade stored and shown.
_GRADE_NAMES = {
    "no_dysplasia": "none",  # four-class checkpoints (--with-normal)
    "mild_dysplasia": "mild",
    "moderate_dysplasia": "moderate",
    "severe_dysplasia": "severe",
}


def _jpeg(image: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _centre_crop(image: Image.Image, frac: float) -> Image.Image:
    w, h = image.size
    dw, dh = int(w * (1 - frac) / 2), int(h * (1 - frac) / 2)
    return image.crop((dw, dh, w - dw, h - dh))


# Edits that must not change a diagnosis. Must match STABILITY_EDITS in
# ml/scripts/reference_experiments.py, where the vote thresholds were chosen.
STABILITY_EDITS = [
    lambda im: im,
    ImageOps.mirror,
    lambda im: im.rotate(90, expand=True),
    lambda im: im.rotate(180),
    lambda im: im.rotate(270, expand=True),
    lambda im: ImageEnhance.Brightness(im).enhance(0.85),
    lambda im: ImageEnhance.Brightness(im).enhance(1.15),
    lambda im: _jpeg(im, 40),
    lambda im: _centre_crop(im, 0.85),
]


@dataclass(frozen=True)
class InferenceResult:
    label: str  # "Cancer" or "Non-Cancer" (single answer on the photo as taken)
    confidence: float  # probability of `label`; stored, never shown
    dysplasia_grade: str | None  # "none" / "mild" / "moderate" / "severe", or None
    assessment: str  # "cancer" / "no_cancer" / "inconclusive"
    reference_status: str | None = None  # "used" / "not_normal" / None (no reference)


def _load_checkpoint(path_setting: str | None):
    """Returns (model, transform, class_to_idx), or None if not configured."""
    if not path_setting or not Path(path_setting).is_file():
        return None
    checkpoint = torch.load(Path(path_setting), map_location="cpu", weights_only=False)
    class_to_idx: dict[str, int] = dict(checkpoint["class_to_idx"])

    model = resnet50(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, len(class_to_idx))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    transform = transforms.Compose(
        [
            transforms.Resize((checkpoint["img_size"], checkpoint["img_size"])),
            transforms.ToTensor(),
            transforms.Normalize(checkpoint["mean"], checkpoint["std"]),
        ]
    )
    return model, transform, class_to_idx


def _open_photo(image_path: Path) -> Image.Image:
    # Phone photos often store pixels sideways plus an EXIF "rotate" tag.
    # Browsers honour the tag when displaying the original, so without
    # this the model sees a rotated lesion and the heatmap overlay renders
    # rotated relative to the photo next to it.
    with Image.open(image_path) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


class PhotoGate:
    """Accepts an image only if its ImageNet ResNet-50 features are close to
    those of the training photos: mean cosine distance to the k nearest is
    at most the threshold fitted on validation photos."""

    def __init__(self, path: Path) -> None:
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        self._model = resnet50(weights=None)
        self._model.fc = torch.nn.Identity()
        self._model.load_state_dict(checkpoint["backbone_state_dict"])
        self._model.eval()
        self._bank = checkpoint["bank"].float()
        self._k = int(checkpoint["k"])
        self.threshold = float(checkpoint["threshold"])
        self._transform = transforms.Compose(
            [
                transforms.Resize((checkpoint["img_size"], checkpoint["img_size"])),
                transforms.ToTensor(),
                transforms.Normalize(checkpoint["mean"], checkpoint["std"]),
            ]
        )

    def distance(self, image: Image.Image) -> float:
        with torch.no_grad():
            feature = self._model(self._transform(image).unsqueeze(0))[0]
        feature = feature / feature.norm()
        return float(1 - (self._bank @ feature).topk(self._k).values.mean())

    def accepts(self, image: Image.Image) -> bool:
        return self.distance(image) <= self.threshold


def _share_identical_weights(source: torch.nn.Module, target: torch.nn.Module) -> int:
    """Points target's parameters at source's wherever they are identical.

    The cancer, grading and photo-check networks all keep ImageNet's frozen
    weights below layer4, so those tensors are duplicated three times in
    memory. Batch-norm running statistics drifted during training and are
    buffers, not parameters, so they stay per model and results are
    unchanged. Returns the number of values now shared.
    """
    shared = 0
    src = dict(source.named_parameters())
    for name, param in list(target.named_parameters()):
        if name.startswith(("layer4", "fc")) or name not in src:
            continue
        if src[name].shape == param.shape and torch.equal(src[name], param):
            module_name, _, attr = name.rpartition(".")
            setattr(target.get_submodule(module_name), attr, src[name])
            shared += param.numel()
    return shared


class InferenceService:
    def __init__(self) -> None:
        self.enabled = False
        self.grading_enabled = False
        self.gate: PhotoGate | None = None
        if settings.GATE_MODEL_PATH and Path(settings.GATE_MODEL_PATH).is_file():
            self.gate = PhotoGate(Path(settings.GATE_MODEL_PATH))
        self._model: torch.nn.Module | None = None
        self._transform: transforms.Compose | None = None
        self._idx_to_label: dict[int, str] | None = None

        cancer = _load_checkpoint(settings.MODEL_PATH)
        if cancer is None:
            return
        self._model, self._transform, self._label_to_idx = cancer
        self._idx_to_label = {v: k for k, v in self._label_to_idx.items()}
        self.enabled = True

        grading = _load_checkpoint(settings.GRADING_MODEL_PATH)
        if grading is not None:
            self._grading_model, self._grading_transform, grade_to_idx = grading
            self._idx_to_grade = {v: _GRADE_NAMES[k] for k, v in grade_to_idx.items()}
            self.grading_enabled = True

        self.shared_values = 0
        if self.grading_enabled:
            self.shared_values += _share_identical_weights(self._model, self._grading_model)
        if self.gate is not None:
            self.shared_values += _share_identical_weights(self._model, self.gate._model)

    def _grade(self, image: Image.Image, cancer: bool) -> str | None:
        if not self.grading_enabled:
            return None
        with torch.no_grad():
            logits = self._grading_model(self._grading_transform(image).unsqueeze(0))[0]
        if cancer:
            # The grading model never saw carcinoma, so "none" next to a
            # Cancer result is meaningless (it said "none" for 44% of Kaggle
            # cancer test photos). Report the likeliest dysplasia grade.
            for idx, grade in self._idx_to_grade.items():
                if grade == "none":
                    logits[idx] = float("-inf")
        return self._idx_to_grade[int(logits.argmax().item())]

    @staticmethod
    def _calibrated(logits: torch.Tensor) -> torch.Tensor:
        """Class probabilities after temperature scaling (TEMPERATURE, fitted
        on validation). Monotonic per photo, so it never changes which side
        of a cut-off a single prediction falls on; it makes the numbers
        closer to observed frequencies."""
        return F.softmax(logits / settings.TEMPERATURE, dim=1)

    def _consensus_score(self, image: Image.Image) -> float:
        """Mean P(cancer) over the STABILITY_EDITS of the photo.

        Deliberately uncalibrated: the triage thresholds were set on this
        score by conformal risk control, whose guarantee holds for any score.
        Re-deriving them on temperature-scaled scores gave the same guarantee
        but missed one more test cancer (ml/artifacts/conformal_triage_T1.62.json)."""
        batch = torch.stack([self._transform(edit(image)) for edit in STABILITY_EDITS])
        with torch.no_grad():
            p = F.softmax(self._model(batch), dim=1)[:, self._label_to_idx["Cancer"]]
        return float(p.mean().item())

    def _features(self, image: Image.Image) -> torch.Tensor:
        """Unit-length penultimate features of the cancer model."""
        captured: dict[str, torch.Tensor] = {}
        hook = self._model.avgpool.register_forward_hook(lambda m, i, o: captured.update(f=o.flatten(1)[0]))
        try:
            with torch.no_grad():
                self._model(self._transform(image).unsqueeze(0))
        finally:
            hook.remove()
        return captured["f"] / captured["f"].norm()

    def _assess(self, image: Image.Image, reference: Image.Image | None) -> tuple[str, str | None]:
        score = self._consensus_score(image)
        if score >= settings.TRIAGE_CANCER_AT:
            assessment = "cancer"
        elif score < settings.TRIAGE_NO_CANCER_BELOW:
            assessment = "no_cancer"
        else:
            # Not clearly safe across edits that should not matter: refer.
            assessment = "inconclusive"
        if reference is None:
            return assessment, None
        # Chewers often have lesions on both sides, so the opposite side is
        # flagged when the model does not see it as normal either. That check
        # uses the same model, which over-calls some normal sites (cheek
        # close-ups), so a "not_normal" reference still informs the decision
        # below rather than being discarded.
        status = "used" if self._consensus_score(reference) < settings.TRIAGE_NO_CANCER_BELOW else "not_normal"
        distance = float(1 - self._features(image) @ self._features(reference))
        if assessment == "cancer" and distance <= settings.REFERENCE_SAME_AS_NORMAL_MAX:
            # The lesion photo is no more different from this patient's own
            # opposite side than healthy mouths are between sides, so the
            # Cancer call is not specific to the lesion -- either the model
            # over-calls this site, or both sides are diseased. Refer.
            # The reference never turns a result into "no_cancer".
            assessment = "inconclusive"
        return assessment, status

    def looks_like_oral_photo(self, image_path: Path) -> bool:
        """True when no photo check is configured, or the check accepts it."""
        return self.gate is None or self.gate.accepts(_open_photo(image_path))

    def predict(
        self, image_path: Path, heatmap_output_path: Path, reference_path: Path | None = None
    ) -> InferenceResult:
        """Runs cancer detection + Grad-CAM and, if configured, dysplasia
        grading. Writes the heatmap overlay PNG to heatmap_output_path.
        `reference_path` is an optional photo of the same site on the same
        patient's healthy opposite side.

        Only call this when `self.enabled` is True.
        """
        assert self._model is not None and self._transform is not None

        image = _open_photo(image_path)
        input_tensor = self._transform(image).unsqueeze(0)

        activations: dict[str, torch.Tensor] = {}
        gradients: dict[str, torch.Tensor] = {}

        def forward_hook(module, inp, out):
            activations["value"] = out.detach()

        def backward_hook(module, grad_in, grad_out):
            gradients["value"] = grad_out[0].detach()

        layer = self._model.layer4
        fh = layer.register_forward_hook(forward_hook)
        bh = layer.register_full_backward_hook(backward_hook)

        try:
            output = self._model(input_tensor)
            # The label uses the uncalibrated probability, against the
            # cut-off validated on it; the stored confidence is calibrated.
            probs = F.softmax(output, dim=1)[0]
            calibrated = self._calibrated(output.detach())[0]
            # The Cancer/Non-Cancer cut-off is a clinical operating-point
            # decision (missed cancers vs. false alarms), not a fixed 0.5 --
            # see the threshold table in ml/artifacts/model_card.md.
            # Confidence is always the probability of the label returned.
            cancer_idx = self._label_to_idx["Cancer"]
            if probs[cancer_idx].item() >= settings.CANCER_THRESHOLD:
                predicted_idx = cancer_idx
            else:
                predicted_idx = self._label_to_idx["Non-Cancer"]
            confidence = float(calibrated[predicted_idx].item())

            self._model.zero_grad()
            output[0, predicted_idx].backward()

            acts = activations["value"][0]
            grads = gradients["value"][0]
            weights = grads.mean(dim=(1, 2))
            cam = torch.relu((weights[:, None, None] * acts).sum(dim=0))
            cam = cam / (cam.max() + 1e-8)
            cam_np = cam.numpy()
        finally:
            fh.remove()
            bh.remove()

        heatmap = Image.fromarray(np.uint8(255 * cam_np)).resize(image.size, Image.BILINEAR)
        overlay = self._overlay(image, heatmap)
        heatmap_output_path.parent.mkdir(parents=True, exist_ok=True)
        overlay.convert("RGB").save(heatmap_output_path)

        assert self._idx_to_label is not None
        reference = _open_photo(reference_path) if reference_path is not None else None
        assessment, reference_status = self._assess(image, reference)
        return InferenceResult(
            label=self._idx_to_label[predicted_idx],
            confidence=confidence,
            dysplasia_grade=self._grade(image, cancer=predicted_idx == cancer_idx),
            assessment=assessment,
            reference_status=reference_status,
        )

    @staticmethod
    def _overlay(image: Image.Image, heatmap: Image.Image) -> Image.Image:
        """Red-yellow overlay matching the visual language the frontend's
        mock heatmaps already use (frontend/src/api/mocks/fixtures.ts), so
        real Grad-CAM output slots in with no frontend change needed."""
        heat_arr = np.array(heatmap, dtype=np.float32) / 255.0
        colored = np.zeros((*heat_arr.shape, 4), dtype=np.uint8)
        colored[..., 0] = 255
        colored[..., 1] = np.uint8(255 * (1 - heat_arr))
        colored[..., 3] = np.uint8(255 * _GRADCAM_ALPHA * heat_arr)

        overlay = Image.fromarray(colored, mode="RGBA")
        return Image.alpha_composite(image.convert("RGBA"), overlay)


# One instance, loaded once at import time (i.e. once per process), reused
# for every request -- loading a ResNet-50 checkpoint per request would add
# real latency and is unnecessary since the model is stateless across calls.
inference_service = InferenceService()
