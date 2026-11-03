"""Render settings and their JSON persistence.

`RenderSettings` describes *how* a video looks; the list of images is passed
separately so the same settings can render many videos.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

from platformdirs import user_config_dir

APP_NAME = "SlideshowMaker"

ASPECT_PRESETS: dict[str, tuple[int, int]] = {
    "9:16 Portrait (1080x1920)": (1080, 1920),
    "1:1 Square (1080x1080)": (1080, 1080),
    "16:9 Landscape (1920x1080)": (1920, 1080),
    "4:5 Portrait (1080x1350)": (1080, 1350),
    "4:3 Landscape (1440x1080)": (1440, 1080),
}

TRANSITIONS = ("crossfade", "slide", "fade_black", "none")
MOTIONS = ("kenburns", "none")
FIT_MODES = ("blur", "crop", "contain")
LOGO_POSITIONS = ("bottom-right", "bottom-left", "top-right", "top-left", "center")


def config_path() -> str:
    return os.path.join(user_config_dir(APP_NAME, appauthor=False), "settings.json")


@dataclass
class RenderSettings:
    # Canvas
    width: int = 1080
    height: int = 1920
    fps: int = 30

    # Timing: `total_seconds` > 0 wins over `seconds_per_image`.
    seconds_per_image: float = 3.0
    total_seconds: float = 0.0

    # Look
    transition: str = "crossfade"
    transition_seconds: float = 0.6
    motion: str = "kenburns"
    motion_strength: float = 0.12       # max zoom, 0.12 = 12 %
    fit: str = "blur"
    background_rgb: tuple[int, int, int] = (12, 12, 16)

    # Overlays
    logo_path: str = ""
    logo_position: str = "bottom-right"
    logo_scale: float = 0.18            # fraction of the canvas width
    logo_opacity: float = 0.9
    logo_margin: float = 0.03           # fraction of the canvas width
    end_card_path: str = ""
    end_card_seconds: float = 2.0

    # Audio
    music_path: str = ""                # file, or folder to pick a random track from
    music_volume: float = 1.0
    music_fade_out: float = 1.5

    # Encoding
    crf: int = 20
    preset: str = "medium"

    # Sources / batch (GUI + CLI convenience, not used by the renderer itself)
    source_folder: str = ""
    links_file: str = ""
    output_folder: str = ""
    videos_count: int = 1
    min_image_width: int = 300
    min_image_height: int = 300
    shuffle: bool = False
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------ helpers
    def validate(self) -> list[str]:
        problems = []
        if self.width < 64 or self.height < 64:
            problems.append("canvas must be at least 64x64")
        if self.fps < 1 or self.fps > 120:
            problems.append("fps must be between 1 and 120")
        if self.total_seconds <= 0 and self.seconds_per_image <= 0:
            problems.append("seconds per image must be positive")
        if self.transition not in TRANSITIONS:
            problems.append(f"unknown transition '{self.transition}'")
        if self.motion not in MOTIONS:
            problems.append(f"unknown motion '{self.motion}'")
        if self.fit not in FIT_MODES:
            problems.append(f"unknown fit mode '{self.fit}'")
        if self.logo_position not in LOGO_POSITIONS:
            problems.append(f"unknown logo position '{self.logo_position}'")
        if self.transition_seconds < 0:
            problems.append("transition length cannot be negative")
        if not 0 <= self.motion_strength <= 1:
            problems.append("motion strength must be between 0 and 1")
        if self.logo_path and not os.path.isfile(self.logo_path):
            problems.append("logo file does not exist")
        if self.end_card_path and not os.path.isfile(self.end_card_path):
            problems.append("end card file does not exist")
        if self.music_path and not os.path.exists(self.music_path):
            problems.append("music file or folder does not exist")
        if not 0 <= self.crf <= 51:
            problems.append("crf must be between 0 and 51")
        return problems

    @property
    def even_size(self) -> tuple[int, int]:
        """H.264 needs even dimensions."""
        return (self.width // 2) * 2, (self.height // 2) * 2

    # -------------------------------------------------------- persistence
    @classmethod
    def from_dict(cls, data: dict) -> "RenderSettings":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        if "background_rgb" in clean and isinstance(clean["background_rgb"], list):
            clean["background_rgb"] = tuple(int(c) for c in clean["background_rgb"][:3])
        try:
            return cls(**clean)
        except TypeError:
            return cls()

    @classmethod
    def load(cls, path: str | None = None) -> "RenderSettings":
        path = path or config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return cls()
        return cls.from_dict(data) if isinstance(data, dict) else cls()

    def save(self, path: str | None = None) -> None:
        path = path or config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
        os.replace(tmp, path)
