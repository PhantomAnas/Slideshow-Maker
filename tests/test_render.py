import os
import subprocess

import numpy as np
import pytest

from conftest import make_image
from slideshow_maker import batch, ffmpeg, render
from slideshow_maker.settings import RenderSettings

HAS_FFMPEG = ffmpeg.find_ffmpeg() is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not on PATH")


def small_settings(**kw) -> RenderSettings:
    base = dict(width=96, height=160, fps=10, seconds_per_image=0.6, transition_seconds=0.2,
                motion="kenburns", crf=30, preset="ultrafast")
    base.update(kw)
    return RenderSettings(**base)


def test_make_plan_and_composer_frames(images):
    s = small_settings()
    plan = render.make_plan(images, s)
    assert len(plan.slot_paths) == 3 and plan.end_card is None
    assert plan.timeline.total == pytest.approx(3 * 0.6 - 2 * 0.2)
    comp = render.FrameComposer(plan, s)
    for t in (0.0, 0.5, 0.9, 1.3):
        f = comp.frame_at(t)
        assert f.shape == (160, 96, 3) and f.dtype == np.uint8
    # Preview is a Pillow image of the same frame.
    assert comp.preview(0.5).size == (96, 160)


def test_make_plan_with_end_card_and_logo(images, tmp_path):
    end = make_image(str(tmp_path / "end.png"), 100, 100, (0, 0, 0))
    logo = make_image(str(tmp_path / "logo.png"), 60, 30, (255, 255, 0))
    s = small_settings(end_card_path=end, end_card_seconds=1.0, logo_path=logo, total_seconds=5.0)
    plan = render.make_plan(images, s)
    assert plan.end_card == end and plan.timeline.total == pytest.approx(5.0)
    comp = render.FrameComposer(plan, s)
    # Logo drawn on a normal slot (bottom-right corner is yellowish) ...
    f = comp.frame_at(0.3)
    assert f[-5, -5, 0] > 200 and f[-5, -5, 2] < 60
    # ... but not on the end card.
    f = comp.frame_at(plan.timeline.total - 0.1)
    assert tuple(f[-5, -5]) == (0, 0, 0)


def test_make_plan_rejects_empty(tmp_path):
    with pytest.raises(render.RenderError):
        render.make_plan([str(tmp_path / "nope.jpg")], small_settings())


def test_pick_music(tmp_path):
    assert render.pick_music("") is None
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.wav").write_bytes(b"x")
    (tmp_path / "readme.txt").write_bytes(b"x")
    import random
    picked = render.pick_music(str(tmp_path), random.Random(1))
    assert picked.endswith((".mp3", ".wav"))
    assert render.pick_music(str(tmp_path / "a.mp3")) == str(tmp_path / "a.mp3")


def test_build_ffmpeg_command(images, tmp_path):
    s = small_settings(music_path="", crf=23)
    plan = render.make_plan(images, s)
    cmd = render.build_ffmpeg_command("ffmpeg", plan, s, str(tmp_path / "o.mp4"))
    assert "-an" in cmd and "libx264" in cmd and "96x160" in cmd
    music = tmp_path / "m.mp3"
    music.write_bytes(b"")
    s.music_path = str(music)
    plan = render.make_plan(images, s)
    cmd = render.build_ffmpeg_command("ffmpeg", plan, s, str(tmp_path / "o.mp4"))
    assert "-stream_loop" in cmd and "afade=t=out" in " ".join(cmd) and "[a]" in cmd


def _make_tone(path: str, seconds: float) -> None:
    subprocess.run([ffmpeg.find_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac", path], check=True)


@needs_ffmpeg
@pytest.mark.parametrize("transition", ["crossfade", "slide", "fade_black", "none"])
def test_render_produces_playable_video(images, tmp_path, transition):
    s = small_settings(transition=transition)
    out = str(tmp_path / "out.mp4")
    prog = []
    plan = render.render(images, s, out, progress=lambda d, t: prog.append((d, t)))
    assert os.path.getsize(out) > 1000
    assert prog[-1][0] == prog[-1][1] == plan.total_frames
    info = ffmpeg.probe(out)
    v = next(st for st in info["streams"] if st["codec_type"] == "video")
    assert (v["width"], v["height"]) == (96, 160)
    assert ffmpeg.media_duration(out) == pytest.approx(plan.timeline.total, abs=0.25)


@needs_ffmpeg
def test_render_with_music_shorter_than_video_loops(images, tmp_path):
    tone = str(tmp_path / "tone.m4a")
    _make_tone(tone, 0.5)
    s = small_settings(music_path=tone, seconds_per_image=1.0, transition="none")
    out = str(tmp_path / "music.mp4")
    plan = render.render(images, s, out)
    info = ffmpeg.probe(out)
    kinds = {st["codec_type"] for st in info["streams"]}
    assert kinds == {"video", "audio"}
    assert ffmpeg.media_duration(out) == pytest.approx(plan.timeline.total, abs=0.3)


@needs_ffmpeg
def test_render_cancel_removes_partial_file(images, tmp_path):
    out = str(tmp_path / "cancel.mp4")
    calls = [0]

    def cancelled():
        calls[0] += 1
        return calls[0] > 3

    with pytest.raises(render.RenderCancelled):
        render.render(images, small_settings(), out, cancelled=cancelled)
    assert not os.path.exists(out)


def test_render_without_ffmpeg_gives_clear_error(images, tmp_path, monkeypatch):
    monkeypatch.setattr(ffmpeg, "find_ffmpeg", lambda: None)
    with pytest.raises(render.RenderError, match="FFmpeg not found"):
        render.render(images, small_settings(), str(tmp_path / "x.mp4"))


@needs_ffmpeg
def test_batch_job_splits_into_videos(images, tmp_path):
    s = small_settings(source_folder=os.path.dirname(images[0]), output_folder=str(tmp_path / "out"),
                       videos_count=2, transition="none")
    stages = []
    outputs = batch.run_job(s, stage=stages.append)
    assert len(outputs) == 2 and all(os.path.getsize(p) > 500 for p in outputs)
    assert any("Rendering video 2 of 2" in st for st in stages)


def test_estimate_total_seconds():
    s = small_settings(seconds_per_image=2.0, transition_seconds=0.5)
    assert render.estimate_total_seconds(4, s) == pytest.approx(6.5)
    s.end_card_path = __file__  # any existing file
    s.end_card_seconds = 1.0
    assert render.estimate_total_seconds(4, s) == pytest.approx(7.0)
    assert render.estimate_total_seconds(0, s) == 0.0
