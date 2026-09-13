"""
Grad-CAM for the fine-tuned ResNet-50 oral lesion classifier.

Targets resnet.layer4 -- the standard, well-documented Grad-CAM target for a
ResNet: the last convolutional block, right before global pooling, so its
activations still carry spatial layout (which pixels) while being deep enough
to reflect class-discriminative features (not just edges/color).

Can be run standalone for a quick visual check, or imported as
`generate_heatmap(model, image_path, target_class)` by the backend's
inference service.

Usage:
    .venv/Scripts/python.exe scripts/gradcam.py <checkpoint.pt> <image.jpg> <output.png>
"""

import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.models import resnet50


def load_model(checkpoint_path: Path):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = resnet50(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, 2)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model, checkpoint


def generate_heatmap(model: torch.nn.Module, image: Image.Image, checkpoint: dict, target_class: int | None = None):
    """Returns (heatmap as a PIL Image sized to the input, predicted_class, confidence)."""
    img_size = checkpoint["img_size"]
    tf = transforms.Compose(
        [
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(checkpoint["mean"], checkpoint["std"]),
        ]
    )
    input_tensor = tf(image).unsqueeze(0)

    activations = {}
    gradients = {}

    def forward_hook(module, inp, out):
        activations["value"] = out.detach()

    def backward_hook(module, grad_in, grad_out):
        gradients["value"] = grad_out[0].detach()

    layer = model.layer4
    fh = layer.register_forward_hook(forward_hook)
    bh = layer.register_full_backward_hook(backward_hook)

    try:
        output = model(input_tensor)
        probs = F.softmax(output, dim=1)[0]
        predicted_class = int(probs.argmax().item()) if target_class is None else target_class
        confidence = float(probs[predicted_class].item())

        model.zero_grad()
        output[0, predicted_class].backward()

        acts = activations["value"][0]       # (C, H, W)
        grads = gradients["value"][0]         # (C, H, W)
        weights = grads.mean(dim=(1, 2))      # (C,) -- global average pool of gradients

        cam = torch.relu((weights[:, None, None] * acts).sum(dim=0))
        cam = cam / (cam.max() + 1e-8)
        cam_np = cam.numpy()
    finally:
        fh.remove()
        bh.remove()

    heatmap = Image.fromarray(np.uint8(255 * cam_np)).resize(image.size, Image.BILINEAR)
    return heatmap, predicted_class, confidence


def overlay_heatmap(image: Image.Image, heatmap: Image.Image, alpha: float = 0.45) -> Image.Image:
    """Composite a grayscale CAM heatmap onto the source image using a
    red-yellow colormap, matching the visual language of the frontend's mock
    heatmaps (fixtures.ts) so the transition from mock to real is seamless."""
    heat_arr = np.array(heatmap, dtype=np.float32) / 255.0
    colored = np.zeros((*heat_arr.shape, 4), dtype=np.uint8)
    colored[..., 0] = 255                              # red channel full
    colored[..., 1] = np.uint8(255 * (1 - heat_arr))   # less green where hotter -> more red/orange
    colored[..., 3] = np.uint8(255 * alpha * heat_arr)  # transparent where cold

    overlay = Image.fromarray(colored, mode="RGBA")
    base = image.convert("RGBA")
    return Image.alpha_composite(base, overlay)


def main():
    if len(sys.argv) != 4:
        print("Usage: gradcam.py <checkpoint.pt> <image.jpg> <output.png>")
        sys.exit(1)

    checkpoint_path, image_path, output_path = (Path(p) for p in sys.argv[1:4])

    model, checkpoint = load_model(checkpoint_path)
    image = Image.open(image_path).convert("RGB")

    heatmap, predicted_class, confidence = generate_heatmap(model, image, checkpoint)

    idx_to_label = {v: k for k, v in checkpoint["class_to_idx"].items()}
    print(f"Prediction: {idx_to_label[predicted_class]} (confidence {confidence:.3f})")

    overlay = overlay_heatmap(image, heatmap)
    overlay.convert("RGB").save(output_path)
    print(f"Heatmap overlay saved to {output_path}")


if __name__ == "__main__":
    main()
