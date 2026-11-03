"""Locating FFmpeg and probing media.  FFmpeg is never bundled: it is found on
PATH, next to the executable, or via the SLIDESHOW_FFMPEG environment variable.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

FFMPEG_DOWNLOAD_URL = "https://ffmpeg.org/download.html"


def _no_window() -> dict:
    """Keep console windows from flashing when launched from the GUI exe on Windows."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _candidates(name: str) -> list[str]:
    env = os.environ.get("SLIDESHOW_FFMPEG")
    out = []
    if env:
        out.append(env if name == "ffmpeg" else os.path.join(os.path.dirname(env), name))
    exe_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0] or "."))
    out.append(os.path.join(exe_dir, name))
    found = shutil.which(name)
    if found:
        out.append(found)
    return out


def find_tool(name: str = "ffmpeg") -> str | None:
    for cand in _candidates(name):
        exe = cand if cand.lower().endswith(".exe") or sys.platform != "win32" else cand + ".exe"
        for p in (cand, exe):
            if os.path.isfile(p):
                return p
    return None


def find_ffmpeg() -> str | None:
    return find_tool("ffmpeg")


def find_ffprobe() -> str | None:
    """ffprobe, preferring the one that ships next to the ffmpeg we use."""
    ffm = find_ffmpeg()
    if ffm:
        sibling = os.path.join(os.path.dirname(ffm), "ffprobe" + (".exe" if sys.platform == "win32" else ""))
        if os.path.isfile(sibling):
            return sibling
    return find_tool("ffprobe")


def ffmpeg_version(path: str | None = None) -> str | None:
    path = path or find_ffmpeg()
    if not path:
        return None
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=10, **_no_window())
        return out.stdout.splitlines()[0] if out.stdout else None
    except (OSError, subprocess.SubprocessError):
        return None


def probe(path: str) -> dict | None:
    """ffprobe-style dict: {"format": {"duration"}, "streams": [{codec_type, width, height}]}.

    Uses ffprobe when available, otherwise parses `ffmpeg -i` output so a bare
    ffmpeg.exe is enough for the app to work.
    """
    ffprobe = find_ffprobe()
    if ffprobe:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                capture_output=True, text=True, timeout=30, **_no_window())
            if out.returncode == 0:
                return json.loads(out.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return _probe_with_ffmpeg(path)


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_RE = re.compile(r"Stream #\d+:\d+.*?: Video:.*?,\s*(\d{2,5})x(\d{2,5})")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+.*?: Audio:")


def _probe_with_ffmpeg(path: str) -> dict | None:
    ffm = find_ffmpeg()
    if not ffm or not os.path.isfile(path):
        return None
    try:
        out = subprocess.run([ffm, "-hide_banner", "-i", path], capture_output=True, text=True,
                             timeout=30, **_no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    text = out.stderr or ""
    m = _DURATION_RE.search(text)
    if not m:
        return None
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    streams: list[dict] = []
    for line in text.splitlines():
        v = _VIDEO_RE.search(line)
        if v:
            streams.append({"codec_type": "video", "width": int(v.group(1)), "height": int(v.group(2))})
        elif _AUDIO_RE.search(line):
            streams.append({"codec_type": "audio"})
    return {"format": {"duration": str(duration)}, "streams": streams}


def media_duration(path: str) -> float | None:
    info = probe(path)
    try:
        return float(info["format"]["duration"])  # type: ignore[index]
    except (TypeError, KeyError, ValueError):
        return None
