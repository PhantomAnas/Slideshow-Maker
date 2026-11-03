"""One job = settings + sources -> N videos.  Shared by the GUI worker and the CLI."""

from __future__ import annotations

import os
import random
import tempfile
from datetime import datetime
from typing import Callable

from . import downloader, render
from .imaging import list_images
from .settings import RenderSettings

LogFn = Callable[[str], None]
StageFn = Callable[[str], None]           # human-readable stage name
ProgressFn = Callable[[int, int], None]


def collect_images(settings: RenderSettings, explicit: list[str] | None,
                   work_dir: str, log: LogFn, stage: StageFn, progress: ProgressFn,
                   cancelled: Callable[[], bool]) -> list[str]:
    """Images from (in priority order) an explicit list, a links file, or a folder."""
    if explicit:
        return list(explicit)
    if settings.links_file:
        try:
            links = downloader.read_links_file(settings.links_file)
        except OSError as exc:
            raise render.RenderError(f"cannot read the links file: {exc}") from exc
        log(f"{len(links)} links in {os.path.basename(settings.links_file)}")
        if not links:
            raise render.RenderError("the links file contains no http(s) URLs")
        stage("Downloading images")
        cache = os.path.join(work_dir, "downloads_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        files = downloader.download_images(links, cache, settings.min_image_width,
                                           settings.min_image_height, progress=progress,
                                           log=log, cancelled=cancelled)
        log(f"{len(files)} of {len(links)} images downloaded and kept")
        return files
    if settings.source_folder:
        return list_images(settings.source_folder)
    return []


def output_name(prefix: str, index: int, count: int) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{prefix}_{stamp}_{index + 1}.mp4" if count > 1 else f"{prefix}_{stamp}.mp4"


def run_job(settings: RenderSettings, explicit_images: list[str] | None = None,
            log: LogFn = lambda m: None, stage: StageFn = lambda s: None,
            progress: ProgressFn = lambda a, b: None,
            cancelled: Callable[[], bool] = lambda: False,
            seed: int | None = None) -> list[str]:
    """Render `settings.videos_count` videos.  Returns the output paths."""
    out_dir = settings.output_folder or os.path.join(os.path.expanduser("~"), "Videos", "Slideshow Maker")
    try:
        os.makedirs(out_dir, exist_ok=True)
        probe = os.path.join(out_dir, ".write_test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
    except OSError as exc:
        raise render.RenderError(f"cannot write to the output folder {out_dir}: {exc}") from exc
    work_dir = os.path.join(out_dir, ".cache")
    rng = random.Random(seed)

    stage("Collecting images")
    images = collect_images(settings, explicit_images, work_dir, log, stage, progress, cancelled)
    images = [p for p in images if os.path.isfile(p)]
    if not images:
        raise render.RenderError("no images to render")
    if settings.shuffle:
        rng.shuffle(images)

    groups = downloader.chunk(images, max(1, settings.videos_count))
    outputs = []
    for gi, group in enumerate(groups):
        if cancelled():
            raise render.RenderCancelled()
        stage(f"Rendering video {gi + 1} of {len(groups)} ({len(group)} images)")
        out_path = os.path.join(out_dir, output_name("slideshow", gi, len(groups)))
        if settings.music_path and render.pick_music(settings.music_path, random.Random(0)) is None:
            log(f"warning: no audio tracks found in {settings.music_path}; rendering without music")
        plan = render.render(group, settings, out_path, progress=progress, log=log,
                             cancelled=cancelled, rng=rng)
        log(f"wrote {out_path} ({plan.timeline.total:.1f}s, {plan.total_frames} frames"
            + (f", music: {os.path.basename(plan.music)}" if plan.music else "") + ")")
        outputs.append(out_path)
    return outputs


def temp_dir() -> str:
    return tempfile.gettempdir()
