from __future__ import annotations

import os

import numpy as np
import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Never read or write the real user settings during tests."""
    monkeypatch.setattr("slideshow_maker.settings.config_path",
                        lambda: str(tmp_path / "cfg" / "settings.json"))


def make_image(path: str, w: int, h: int, color=(200, 80, 40)) -> str:
    """A flat-colour test image with a lighter square in the top-left corner."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:] = color
    arr[: max(1, h // 4), : max(1, w // 4)] = (255, 255, 255)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(arr).save(path)
    return path


@pytest.fixture
def images(tmp_path) -> list[str]:
    folder = tmp_path / "imgs"
    return [
        make_image(str(folder / "1.jpg"), 400, 300, (200, 80, 40)),
        make_image(str(folder / "2.png"), 300, 500, (40, 160, 90)),
        make_image(str(folder / "3.jpg"), 640, 640, (30, 60, 200)),
    ]
