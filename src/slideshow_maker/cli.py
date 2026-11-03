"""Command line: `slideshow-maker --cli ...`.

    slideshow-maker --cli --images ./photos --out ./videos --aspect 9:16 --per-image 2.5
    slideshow-maker --cli --links links.txt --videos 3 --music ./tracks --logo logo.png
"""

from __future__ import annotations

import argparse
import sys

from . import batch, ffmpeg
from .render import RenderCancelled, RenderError
from .settings import ASPECT_PRESETS, FIT_MODES, LOGO_POSITIONS, MOTIONS, TRANSITIONS, RenderSettings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="slideshow-maker --cli",
                                description="Render slideshow videos from images or image URLs.")
    src = p.add_argument_group("sources")
    src.add_argument("--images", help="folder of images")
    src.add_argument("--links", help="text file with one image URL per line")
    src.add_argument("--out", help="output folder (default: ~/Videos/Slideshow Maker)")
    src.add_argument("--videos", type=int, help="split the images into this many videos")
    src.add_argument("--shuffle", action="store_true")
    src.add_argument("--min-size", type=int, metavar="PX", help="skip downloaded images smaller than PX on either side")

    look = p.add_argument_group("look")
    look.add_argument("--aspect", choices=["9:16", "1:1", "16:9", "4:5", "4:3"], help="canvas preset")
    look.add_argument("--size", metavar="WxH", help="custom canvas, e.g. 1280x720")
    look.add_argument("--fps", type=int)
    look.add_argument("--per-image", type=float, metavar="SEC")
    look.add_argument("--total", type=float, metavar="SEC", help="total video length (overrides --per-image)")
    look.add_argument("--transition", choices=TRANSITIONS)
    look.add_argument("--transition-seconds", type=float)
    look.add_argument("--motion", choices=MOTIONS)
    look.add_argument("--fit", choices=FIT_MODES)
    look.add_argument("--logo"); look.add_argument("--logo-position", choices=LOGO_POSITIONS)
    look.add_argument("--logo-scale", type=float)
    look.add_argument("--end-card"); look.add_argument("--end-card-seconds", type=float)
    look.add_argument("--music", help="audio file or folder (random track)")
    look.add_argument("--crf", type=int)
    p.add_argument("--no-saved-settings", action="store_true", help="start from defaults instead of the GUI's saved settings")
    p.add_argument("--check", action="store_true", help="only report whether FFmpeg was found")
    return p


def apply_args(s: RenderSettings, a: argparse.Namespace) -> RenderSettings:
    if a.images: s.source_folder, s.links_file = a.images, ""
    if a.links: s.links_file, s.source_folder = a.links, ""
    if a.out: s.output_folder = a.out
    if a.videos: s.videos_count = a.videos
    if a.shuffle: s.shuffle = True
    if a.min_size is not None: s.min_image_width = s.min_image_height = a.min_size
    if a.aspect:
        key = next(k for k in ASPECT_PRESETS if k.startswith(a.aspect + " "))
        s.width, s.height = ASPECT_PRESETS[key]
    if a.size:
        w, h = a.size.lower().split("x")
        s.width, s.height = int(w), int(h)
    if a.fps: s.fps = a.fps
    if a.per_image: s.seconds_per_image, s.total_seconds = a.per_image, 0.0
    if a.total: s.total_seconds = a.total
    if a.transition: s.transition = a.transition
    if a.transition_seconds is not None: s.transition_seconds = a.transition_seconds
    if a.motion: s.motion = a.motion
    if a.fit: s.fit = a.fit
    if a.logo is not None: s.logo_path = a.logo
    if a.logo_position: s.logo_position = a.logo_position
    if a.logo_scale: s.logo_scale = a.logo_scale
    if a.end_card is not None: s.end_card_path = a.end_card
    if a.end_card_seconds: s.end_card_seconds = a.end_card_seconds
    if a.music is not None: s.music_path = a.music
    if a.crf is not None: s.crf = a.crf
    return s


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.check:
        v = ffmpeg.ffmpeg_version()
        print(v or f"FFmpeg not found. Install it from {ffmpeg.FFMPEG_DOWNLOAD_URL}")
        return 0 if v else 1
    s = RenderSettings() if a.no_saved_settings else RenderSettings.load()
    s = apply_args(s, a)
    if not (s.source_folder or s.links_file):
        print("error: give --images FOLDER or --links FILE", file=sys.stderr)
        return 2
    problems = s.validate()
    if problems:
        print("error: " + "; ".join(problems), file=sys.stderr)
        return 2

    last = [-1]

    def progress(done: int, total: int) -> None:
        pct = int(done * 100 / max(1, total))
        if pct != last[0]:
            last[0] = pct
            print(f"\r  {pct:3d}%", end="", flush=True)

    try:
        outputs = batch.run_job(s, log=lambda m: print(m), stage=lambda st: print(f"\n== {st}"),
                                progress=progress)
    except RenderError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except (RenderCancelled, KeyboardInterrupt):
        print("\ncancelled", file=sys.stderr)
        return 130
    print("\n" + "\n".join(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
