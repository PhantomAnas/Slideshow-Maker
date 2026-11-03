"""The renderer: composes every frame in Python and streams raw RGB into FFmpeg.

Why not a giant FFmpeg filter graph?  Exact progress, instant cancel, one code
path for preview and output, and no 400-node graph that falls over at 150
images.  A 1080x1920 frame is ~6 MB; at 30 fps that is well within what a pipe
and libx264 handle.
"""

from __future__ import annotations

import os
import random
import shlex
import subprocess
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image

from . import ffmpeg as ff
from .imaging import (
    KenBurns,
    LogoOverlay,
    blend_frames,
    fit_image,
    is_image_file,
    load_image,
    to_array,
)
from .settings import RenderSettings
from .timeline import Timeline, build_timeline, per_image_seconds

ProgressFn = Callable[[int, int], None]      # frames done, frames total
LogFn = Callable[[str], None]
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}


class RenderCancelled(Exception):
    pass


class RenderError(Exception):
    pass


@dataclass
class Plan:
    """Everything decided before the first frame: slots, sizes, overlays."""
    images: list[str]
    end_card: str | None
    timeline: Timeline
    width: int
    height: int
    fps: int
    music: str | None

    @property
    def total_frames(self) -> int:
        return max(1, int(round(self.timeline.total * self.fps)))

    @property
    def slot_paths(self) -> list[str]:
        return self.images + ([self.end_card] if self.end_card else [])


def pick_music(path: str, rng: random.Random | None = None) -> str | None:
    """A music file, or a random track from a folder.  None if nothing usable."""
    if not path:
        return None
    if os.path.isfile(path):
        return path
    if os.path.isdir(path):
        tracks = sorted(n for n in os.listdir(path)
                        if os.path.splitext(n)[1].lower() in AUDIO_EXTENSIONS)
        if tracks:
            return os.path.join(path, (rng or random).choice(tracks))
    return None


def make_plan(images: list[str], settings: RenderSettings, rng: random.Random | None = None) -> Plan:
    images = [p for p in images if is_image_file(p) and os.path.isfile(p)]
    if not images:
        raise RenderError("no usable images")
    width, height = settings.even_size
    end_card = settings.end_card_path or None
    per = per_image_seconds(len(images), settings.seconds_per_image, settings.total_seconds,
                            settings.transition_seconds if settings.transition != "none" else 0.0,
                            settings.end_card_seconds, bool(end_card))
    durations = [per] * len(images)
    if end_card:
        durations.append(max(0.5, settings.end_card_seconds))
    trans = settings.transition_seconds if settings.transition != "none" else 0.0
    tl = build_timeline(durations, trans)
    return Plan(images, end_card, tl, width, height, settings.fps, pick_music(settings.music_path, rng))


class FrameComposer:
    """Produces the frame at any time t.  Keeps the two or three most recently
    used images prepared so a transition never reloads anything."""

    def __init__(self, plan: Plan, settings: RenderSettings) -> None:
        self.plan = plan
        self.s = settings
        self.w, self.h = plan.width, plan.height
        self._cache: OrderedDict[int, object] = OrderedDict()
        self.logo = None
        if settings.logo_path:
            try:
                self.logo = LogoOverlay(settings.logo_path, self.w, self.h, settings.logo_scale,
                                        settings.logo_position, settings.logo_margin, settings.logo_opacity)
            except (OSError, ValueError) as exc:
                raise RenderError(f"cannot read the logo {os.path.basename(settings.logo_path)}: {exc}") from exc

    def _prepared(self, index: int):
        hit = self._cache.get(index)
        if hit is not None:
            self._cache.move_to_end(index)
            return hit
        path = self.plan.slot_paths[index]
        is_end_card = self.plan.end_card is not None and index == len(self.plan.slot_paths) - 1
        try:
            img = load_image(path)
        except (OSError, ValueError, SyntaxError) as exc:   # Pillow raises all three for junk files
            raise RenderError(f"cannot read image {os.path.basename(path)}: {exc}") from exc
        if self.s.motion == "kenburns" and not is_end_card:
            prepared = KenBurns(img, self.w, self.h, self.s.fit, self.s.background_rgb,
                                self.s.motion_strength, seed=index)
        else:
            prepared = to_array(fit_image(img, self.w, self.h, self.s.fit, self.s.background_rgb))
        self._cache[index] = prepared
        while len(self._cache) > 3:
            self._cache.popitem(last=False)
        return prepared

    def _slot_frame(self, index: int, progress: float) -> np.ndarray:
        prepared = self._prepared(index)
        if isinstance(prepared, KenBurns):
            return to_array(prepared.frame(progress))
        return prepared

    def frame_at(self, t: float) -> np.ndarray:
        st = self.plan.timeline.state_at(t)
        frame = self._slot_frame(st.current, st.progress)
        if st.incoming is not None and st.blend > 0:
            nxt = self._slot_frame(st.incoming, st.incoming_progress)
            frame = blend_frames(frame, nxt, self.s.transition, st.blend)
        else:
            frame = frame.copy()
        if self.logo is not None:
            is_end_card = (self.plan.end_card is not None
                           and st.current == len(self.plan.slot_paths) - 1)
            if not is_end_card:
                frame = self.logo.apply(frame)
        return frame

    def preview(self, t: float) -> Image.Image:
        return Image.fromarray(self.frame_at(t))


# ------------------------------------------------------------------ ffmpeg

def build_ffmpeg_command(ffmpeg_path: str, plan: Plan, settings: RenderSettings, out_path: str) -> list[str]:
    total = plan.timeline.total
    cmd = [ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{plan.width}x{plan.height}",
           "-r", str(plan.fps), "-i", "pipe:0"]
    if plan.music:
        cmd += ["-stream_loop", "-1", "-i", plan.music]
        fade = max(0.0, min(settings.music_fade_out, total))
        afilter = f"volume={settings.music_volume:.3f}"
        if fade > 0:
            afilter += f",afade=t=out:st={max(0.0, total - fade):.3f}:d={fade:.3f}"
        cmd += ["-filter_complex", f"[1:a]{afilter}[a]", "-map", "0:v", "-map", "[a]",
                "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-map", "0:v", "-an"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(settings.crf),
            "-preset", settings.preset, "-movflags", "+faststart",
            "-t", f"{total:.3f}", out_path]
    return cmd


def render(images: list[str], settings: RenderSettings, out_path: str,
           progress: ProgressFn | None = None, log: LogFn | None = None,
           cancelled: Callable[[], bool] = lambda: False,
           rng: random.Random | None = None) -> Plan:
    """Render one video.  Raises RenderCancelled / RenderError."""
    log = log or (lambda _m: None)
    problems = settings.validate()
    if problems:
        raise RenderError("; ".join(problems))
    ffmpeg_path = ff.find_ffmpeg()
    if not ffmpeg_path:
        raise RenderError(f"FFmpeg not found. Install it from {ff.FFMPEG_DOWNLOAD_URL} and make sure it is on PATH.")

    plan = make_plan(images, settings, rng)
    composer = FrameComposer(plan, settings)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cmd = build_ffmpeg_command(ffmpeg_path, plan, settings, out_path)
    log("ffmpeg " + " ".join(shlex.quote(c) for c in cmd[1:]))

    stderr_lines: list[str] = []
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, **ff._no_window())

    def drain() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_lines.append(line.decode("utf-8", "replace").rstrip())

    threading.Thread(target=drain, daemon=True).start()

    total_frames = plan.total_frames
    assert proc.stdin is not None
    try:
        for n in range(total_frames):
            if cancelled():
                raise RenderCancelled()
            t = n / plan.fps
            frame = composer.frame_at(t)
            try:
                proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError) as exc:
                raise RenderError("FFmpeg stopped accepting frames: " + _tail(stderr_lines)) from exc
            if progress and (n % 5 == 0 or n == total_frames - 1):
                progress(n + 1, total_frames)
        proc.stdin.close()
        rc = proc.wait()
        if rc != 0:
            raise RenderError(f"FFmpeg exited with code {rc}: {_tail(stderr_lines)}")
    except RenderCancelled:
        _kill(proc)
        try:
            os.remove(out_path)
        except OSError:
            pass
        raise
    except Exception:
        _kill(proc)
        raise
    if progress:
        progress(total_frames, total_frames)
    return plan


def _kill(proc: subprocess.Popen) -> None:
    try:
        if proc.stdin:
            proc.stdin.close()
    except OSError:
        pass
    try:
        proc.kill()
        proc.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def _tail(lines: list[str], n: int = 5) -> str:
    return " | ".join(lines[-n:]) if lines else "(no output)"


def estimate_total_seconds(n_images: int, settings: RenderSettings) -> float:
    """Duration the GUI shows before rendering."""
    if n_images <= 0:
        return 0.0
    trans = settings.transition_seconds if settings.transition != "none" else 0.0
    has_end = bool(settings.end_card_path)
    per = per_image_seconds(n_images, settings.seconds_per_image, settings.total_seconds,
                            trans, settings.end_card_seconds, has_end)
    durations = [per] * n_images + ([max(0.5, settings.end_card_seconds)] if has_end else [])
    return build_timeline(durations, trans).total
