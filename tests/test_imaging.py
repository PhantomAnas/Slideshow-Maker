import numpy as np
import pytest
from PIL import Image

from conftest import make_image
from slideshow_maker import imaging


@pytest.mark.parametrize("mode", ["blur", "crop", "contain"])
@pytest.mark.parametrize("src", [(400, 300), (300, 500), (640, 640), (50, 20)])
def test_fit_image_always_returns_canvas_size(mode, src):
    img = Image.new("RGB", src, (100, 50, 25))
    out = imaging.fit_image(img, 216, 384, mode)
    assert out.size == (216, 384) and out.mode == "RGB"


def test_fit_contain_uses_background_and_centres():
    img = Image.new("RGB", (400, 100), (255, 0, 0))
    out = np.asarray(imaging.fit_image(img, 200, 200, "contain", (0, 0, 0)))
    assert tuple(out[0, 0]) == (0, 0, 0)          # letterbox bar
    assert tuple(out[100, 100]) == (255, 0, 0)    # picture in the middle


def test_fit_crop_fills_with_picture():
    img = Image.new("RGB", (400, 100), (255, 0, 0))
    out = np.asarray(imaging.fit_image(img, 200, 200, "crop"))
    assert tuple(out[0, 0]) == (255, 0, 0) and tuple(out[199, 199]) == (255, 0, 0)


def test_fit_blur_background_is_darker_than_picture():
    img = Image.new("RGB", (400, 100), (200, 200, 200))
    out = np.asarray(imaging.fit_image(img, 200, 200, "blur"))
    assert out[100, 100].mean() > out[5, 100].mean() + 40


def test_kenburns_frames_have_canvas_size_and_move():
    img = Image.new("RGB", (800, 600), (10, 20, 30))
    arr = np.asarray(img).copy()
    arr[:50, :50] = 255
    kb = imaging.KenBurns(Image.fromarray(arr), 160, 120, "crop", (0, 0, 0), strength=0.2, seed=0)
    f0, f1 = kb.frame(0.0), kb.frame(1.0)
    assert f0.size == (160, 120) and f1.size == (160, 120)
    assert np.abs(np.asarray(f0).astype(int) - np.asarray(f1).astype(int)).sum() > 0
    # Out-of-range progress is clamped, never raises.
    assert kb.frame(5.0).size == (160, 120)


def test_logo_overlay_positions_and_blends(tmp_path):
    logo = Image.new("RGBA", (100, 50), (0, 255, 0, 255))
    logo_path = str(tmp_path / "logo.png")
    logo.save(logo_path)
    ov = imaging.LogoOverlay(logo_path, 400, 400, scale=0.25, position="top-left", margin=0.0, opacity=1.0)
    assert (ov.w, ov.h, ov.x, ov.y) == (100, 50, 0, 0)
    frame = np.zeros((400, 400, 3), dtype=np.uint8)
    out = ov.apply(frame)
    assert tuple(out[10, 10]) == (0, 255, 0) and tuple(out[300, 300]) == (0, 0, 0)

    half = imaging.LogoOverlay(logo_path, 400, 400, scale=0.25, position="bottom-right", margin=0.05, opacity=0.5)
    assert half.x == 400 - 100 - 20 and half.y == 400 - 50 - 20
    out = half.apply(np.zeros((400, 400, 3), dtype=np.uint8))
    assert 120 <= out[half.y + 5, half.x + 5][1] <= 135


def test_blend_frames_kinds():
    a = np.full((4, 10, 3), 0, dtype=np.uint8)
    b = np.full((4, 10, 3), 200, dtype=np.uint8)
    assert imaging.blend_frames(a, b, "crossfade", 0.5)[0, 0, 0] == 100
    assert imaging.blend_frames(a, b, "fade_black", 0.5)[0, 0, 0] == 0
    assert imaging.blend_frames(a, b, "fade_black", 1.0)[0, 0, 0] == 200
    s = imaging.blend_frames(a, b, "slide", 0.5)
    assert s[0, 0, 0] == 0 and s[0, 9, 0] == 200
    assert imaging.blend_frames(a, b, "slide", 0.0)[0, 9, 0] == 0
    assert imaging.blend_frames(a, b, "slide", 1.0)[0, 0, 0] == 200
    assert imaging.blend_frames(a, b, "none", 0.9)[0, 0, 0] == 200


def test_list_images_natural_order_and_filter(tmp_path):
    for n in ("10.jpg", "2.png", "1.jpg", "notes.txt", "x.JPG"):
        make_image(str(tmp_path / n), 8, 8) if n != "notes.txt" else (tmp_path / n).write_text("x")
    names = [p.split("\\")[-1].split("/")[-1] for p in imaging.list_images(str(tmp_path))]
    assert names == ["1.jpg", "2.png", "10.jpg", "x.JPG"]
    assert imaging.list_images(str(tmp_path / "missing")) == []
