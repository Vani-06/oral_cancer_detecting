"""
Loads the trained ResNet-50 checkpoint (see ml/scripts/train.py) once at
startup and runs inference + Grad-CAM per upload.

Self-contained: does not import anything from ml/ (a separate, training-only
environment that isn't part of the deployed backend) -- the model
architecture and Grad-CAM logic are small enough to duplicate here rather
than couple the runtime service to the training toolchain's layout.

If MODEL_PATH is unset or the checkpoint file doesn't exist, `enabled` is
False and `predict()` is never called -- PredictionService leaves the record
Pending exactly as it did before real inference existed. This is a
deliberate fallback so local dev and any environment without the (large,
model-specific) weights file keeps working.
"""

from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from torchvision import transforms
from torchvision.models import resnet50

from app.core.config import settings

_GRADCAM_ALPHA = 0.45


class InferenceService:
    def __init__(self) -> None:
        self.enabled = False
        self._model: torch.nn.Module | None = None
        self._transform: transforms.Compose | None = None
        self._idx_to_label: dict[int, str] | None = None

        model_path = settings.MODEL_PATH
        if not model_path:
            return

        checkpoint_path = Path(model_path)
        if not checkpoint_path.is_file():
            return

        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)

        model = resnet50(weights=None)
        model.fc = torch.nn.Linear(model.fc.in_features, 2)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()

        self._model = model
        self._transform = transforms.Compose(
            [
                transforms.Resize((checkpoint["img_size"], checkpoint["img_size"])),
                transforms.ToTensor(),
                transforms.Normalize(checkpoint["mean"], checkpoint["std"]),
            ]
        )
        self._label_to_idx: dict[str, int] = dict(checkpoint["class_to_idx"])
        self._idx_to_label = {v: k for k, v in self._label_to_idx.items()}
        self.enabled = True

    def predict(self, image_path: Path, heatmap_output_path: Path) -> tuple[str, float]:
        """Runs classification + Grad-CAM, writes the heatmap overlay PNG to
        heatmap_output_path, and returns (label, confidence).

        Only call this when `self.enabled` is True.
        """
        assert self._model is not None and self._transform is not None

        # Phone photos often store pixels sideways plus an EXIF "rotate" tag.
        # Browsers honour the tag when displaying the original, so without
        # this the model sees a rotated lesion and the heatmap overlay renders
        # rotated relative to the photo next to it.
        image = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
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
            probs = F.softmax(output, dim=1)[0]
            # The Cancer/Non-Cancer cut-off is a clinical operating-point
            # decision (missed cancers vs. false alarms), not a fixed 0.5 --
            # see the threshold table in ml/artifacts/model_card.md.
            # Confidence is always the probability of the label returned.
            cancer_idx = self._label_to_idx["Cancer"]
            if probs[cancer_idx].item() >= settings.CANCER_THRESHOLD:
                predicted_idx = cancer_idx
            else:
                predicted_idx = self._label_to_idx["Non-Cancer"]
            confidence = float(probs[predicted_idx].item())

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
        return self._idx_to_label[predicted_idx], confidence

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
