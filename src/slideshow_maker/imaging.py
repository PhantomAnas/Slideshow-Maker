"""Pixel work: loading, fitting to the canvas, Ken Burns motion, logo overlay.

Everything returns numpy uint8 arrays of shape (H, W, 3) in RGB, which is what
the renderer streams straight into FFmpeg.
"""

from __future__ import annotations

import math
import os
import random

import numpy as np
from PIL import Image, ImageFilter, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def is_image_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def list_images(folder: str) -> list[str]:
    """Image files directly inside `folder`, sorted naturally (2 before 10)."""
    try:
        names = [n for n in os.listdir(folder) if is_image_file(n)]
    except OSError:
        return []

    def natural(s: str):
        import re
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

    return [os.path.join(folder, n) for n in sorted(names, key=natural)]


def load_image(path: str) -> Image.Image:
    """Open as RGB with EXIF rotation applied.  Raises OSError on bad files."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def load_rgba(path: str) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGBA")


# ------------------------------------------------------------------ fitting

def fit_image(img: Image.Image, width: int, height: int, mode: str = "blur",
              background=(12, 12, 16)) -> Image.Image:
    """Return a `width` x `height` RGB image.

    blur    - image scaled to fit inside, over a blurred, darkened, zoomed copy
              of itself (the Instagram/TikTok look; no black bars)
    crop    - image scaled to cover the canvas and centre-cropped
    contain - image scaled to fit inside, letterboxed with `background`
    """
    if width <= 0 or height <= 0:
        raise ValueError("canvas must be positive")
    src_w, src_h = img.size
    scale_cover = max(width / src_w, height / src_h)
    scale_fit = min(width / src_w, height / src_h)

    if mode == "crop":
        return _cover(img, width, height, scale_cover)

    fitted_w = max(1, round(src_w * scale_fit))
    fitted_h = max(1, round(src_h * scale_fit))
    fitted = img.resize((fitted_w, fitted_h), Image.Resampling.LANCZOS)

    if mode == "contain":
        canvas = Image.new("RGB", (width, height), tuple(background))
    elif mode == "blur":
        # Blur a small cover-scaled copy (cheap) then upscale: looks like a
        # heavy gaussian blur at full size for a fraction of the cost.
        small_w = max(8, width // 8)
        small_h = max(8, height // 8)
        canvas = _cover(img, small_w, small_h, max(small_w / src_w, small_h / src_h))
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=6))
        canvas = canvas.resize((width, height), Image.Resampling.BILINEAR)
        canvas = Image.eval(canvas, lambda v: int(v * 0.55))  # darken so the photo pops
    else:
        raise ValueError(f"unknown fit mode '{mode}'")

    if fitted_w == width and fitted_h == height:
        return fitted
    canvas.paste(fitted, ((width - fitted_w) // 2, (height - fitted_h) // 2))
    return canvas


def _cover(img: Image.Image, width: int, height: int, scale: float) -> Image.Image:
    src_w, src_h = img.size
    new_w = max(width, math.ceil(src_w * scale))
    new_h = max(height, math.ceil(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


# --------------------------------------------------------------- ken burns

class KenBurns:
    """A slow zoom + drift over one fitted image.

    The image is fitted to an oversized canvas once; every frame crops a
    window that shrinks (zoom in) or grows (zoom out) while its centre drifts,
    then resizes the window to the output size.  `seed` makes the motion of
    image N reproducible between preview and render.
    """

    OVERSCAN = 1.25

    def __init__(self, img: Image.Image, width: int, height: int, fit: str,
                 background, strength: float = 0.12, seed: int = 0) -> None:
        self.width, self.height = width, height
        big_w = round(width * self.OVERSCAN)
        big_h = round(height * self.OVERSCAN)
        self.big = fit_image(img, big_w, big_h, fit, background)
        self.big_w, self.big_h = big_w, big_h

        rng = random.Random(seed)
        strength = max(0.0, min(1.0, strength))
        zoom_in = (seed % 2 == 0)
        z0, z1 = (1.0, 1.0 + strength) if zoom_in else (1.0 + strength, 1.0)
        self.z0, self.z1 = z0, z1
        # Drift direction: a random unit-ish vector, scaled so the window
        # never leaves the oversized canvas.
        ang = rng.uniform(0, 2 * math.pi)
        self.dx, self.dy = math.cos(ang), math.sin(ang)

    def frame(self, progress: float) -> Image.Image:
        p = _ease_in_out(min(1.0, max(0.0, progress)))
        z = self.z0 + (self.z1 - self.z0) * p
        # Window in the big canvas that maps to the output at zoom z.
        win_w = self.width * self.OVERSCAN / z
        win_h = self.height * self.OVERSCAN / z
        free_x = (self.big_w - win_w) / 2
        free_y = (self.big_h - win_h) / 2
        cx = self.big_w / 2 + self.dx * free_x * (2 * p - 1)
        cy = self.big_h / 2 + self.dy * free_y * (2 * p - 1)
        left = int(round(cx - win_w / 2))
        top = int(round(cy - win_h / 2))
        left = max(0, min(self.big_w - int(win_w), left))
        top = max(0, min(self.big_h - int(win_h), top))
        box = (left, top, left + int(win_w), top + int(win_h))
        return self.big.resize((self.width, self.height), Image.Resampling.BILINEAR, box=box)


def _ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------- logos

class LogoOverlay:
    """A logo pre-scaled and positioned once; `apply` blends it per frame."""

    def __init__(self, logo_path: str, width: int, height: int, scale: float = 0.18,
                 position: str = "bottom-right", margin: float = 0.03,
                 opacity: float = 0.9) -> None:
        logo = load_rgba(logo_path)
        target_w = max(1, round(width * scale))
        ratio = target_w / logo.width
        target_h = max(1, round(logo.height * ratio))
        if target_h > height * 0.5:          # very tall logos: bound by height instead
            target_h = round(height * 0.5)
            target_w = max(1, round(logo.width * target_h / logo.height))
        logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
        arr = np.asarray(logo, dtype=np.float32) / 255.0
        self.rgb = arr[:, :, :3]
        self.alpha = arr[:, :, 3:4] * max(0.0, min(1.0, opacity))
        m = round(width * margin)
        positions = {
            "bottom-right": (width - target_w - m, height - target_h - m),
            "bottom-left": (m, height - target_h - m),
            "top-right": (width - target_w - m, m),
            "top-left": (m, m),
            "center": ((width - target_w) // 2, (height - target_h) // 2),
        }
        x, y = positions[position]
        self.x = max(0, min(width - target_w, x))
        self.y = max(0, min(height - target_h, y))
        self.w, self.h = target_w, target_h

    def apply(self, frame: np.ndarray) -> np.ndarray:
        region = frame[self.y:self.y + self.h, self.x:self.x + self.w].astype(np.float32) / 255.0
        blended = region * (1 - self.alpha) + self.rgb * self.alpha
        frame[self.y:self.y + self.h, self.x:self.x + self.w] = (blended * 255).astype(np.uint8)
        return frame


# ------------------------------------------------------------- transitions

def blend_frames(a: np.ndarray, b: np.ndarray, kind: str, t: float) -> np.ndarray:
    """Combine the outgoing frame `a` and incoming `b` at transition progress t in [0, 1]."""
    t = min(1.0, max(0.0, t))
    if kind == "crossfade":
        return (a.astype(np.float32) * (1 - t) + b.astype(np.float32) * t).astype(np.uint8)
    if kind == "fade_black":
        if t < 0.5:
            return (a.astype(np.float32) * (1 - 2 * t)).astype(np.uint8)
        return (b.astype(np.float32) * (2 * t - 1)).astype(np.uint8)
    if kind == "slide":
        w = a.shape[1]
        offset = int(round(w * _ease_in_out(t)))   # how far `a` has moved left
        out = np.empty_like(a)
        if offset < w:
            out[:, :w - offset] = a[:, offset:]
        if offset > 0:
            out[:, w - offset:] = b[:, :offset]
        return out
    return b if t >= 0.5 else a


def to_array(img: Image.Image) -> np.ndarray:
    return np.asarray(img, dtype=np.uint8)
