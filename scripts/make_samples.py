"""Generate a few colourful sample photos (gradients + shapes) for demos and the
screenshot, so no real photographs ship with the repo.

    python scripts/make_samples.py [out_dir]
"""

from __future__ import annotations

import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw

PALETTES = [
    ((255, 94, 98), (255, 195, 113)),
    ((67, 198, 172), (248, 255, 174)),
    ((131, 58, 180), (253, 29, 29)),
    ((0, 114, 255), (0, 198, 255)),
    ((255, 154, 158), (250, 208, 196)),
    ((35, 37, 38), (65, 67, 69)),
]


def gradient(w: int, h: int, c0, c1, angle: float) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (xx * math.cos(angle) + yy * math.sin(angle))
    t = (t - t.min()) / max(1e-6, (t.max() - t.min()))
    arr = np.stack([(c0[i] + (c1[i] - c0[i]) * t) for i in range(3)], axis=-1)
    return Image.fromarray(arr.astype(np.uint8))


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(3)
    sizes = [(1600, 1000), (900, 1400), (1200, 1200), (1800, 900), (1000, 1500), (1400, 1000)]
    for i, (w, h) in enumerate(sizes):
        c0, c1 = PALETTES[i % len(PALETTES)]
        img = gradient(w, h, c0, c1, rng.uniform(0, math.pi))
        d = ImageDraw.Draw(img, "RGBA")
        for _ in range(6):
            r = rng.randint(min(w, h) // 10, min(w, h) // 3)
            x, y = rng.randint(0, w), rng.randint(0, h)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rng.randint(30, 90)))
        d.text((40, h - 70), f"sample {i + 1}", fill=(255, 255, 255, 200))
        img.save(os.path.join(out_dir, f"sample_{i + 1}.jpg"), quality=90)
    print("wrote", len(sizes), "images to", out_dir)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples"))
