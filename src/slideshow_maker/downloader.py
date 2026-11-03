"""Fetch images from a list of URLs (the original workflow of this tool).

Only `http(s)` lines count; blank lines and `#` comments are skipped.  Each
download is verified with Pillow, tiny or broken files are discarded, and the
caller gets the list of files that survived, in the original order.
"""

from __future__ import annotations

import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from PIL import Image

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SlideshowMaker/0.1"
ProgressFn = Callable[[int, int], None]
LogFn = Callable[[str], None]

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def parse_links(text: str) -> list[str]:
    links = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _URL_RE.match(line):
            links.append(line)
    return links


def read_links_file(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_links(fh.read())


def chunk(items: list, n_groups: int) -> list[list]:
    """Split into `n_groups` groups as evenly as possible, keeping order.

    Unlike the old integer-division approach, no item is ever dropped.
    """
    n_groups = max(1, min(n_groups, len(items))) if items else 1
    base, extra = divmod(len(items), n_groups)
    out, start = [], 0
    for g in range(n_groups):
        size = base + (1 if g < extra else 0)
        out.append(items[start:start + size])
        start += size
    return [g for g in out if g]


def _fetch(url: str, dest: str, timeout: float) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
        while True:
            block = resp.read(64 * 1024)
            if not block:
                break
            fh.write(block)


def _verify(path: str, min_w: int, min_h: int) -> tuple[bool, str]:
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            w, h = img.size
            fmt = (img.format or "").lower()
    except Exception as exc:  # noqa: BLE001 - any decode failure means "not an image"
        return False, f"not an image ({exc.__class__.__name__})"
    if w < min_w or h < min_h:
        return False, f"too small ({w}x{h})"
    return True, fmt


def download_images(urls: list[str], folder: str, min_w: int = 0, min_h: int = 0,
                    workers: int = 4, timeout: float = 20.0,
                    progress: ProgressFn | None = None, log: LogFn | None = None,
                    cancelled: Callable[[], bool] = lambda: False) -> list[str]:
    """Download `urls` into `folder` as 001.ext, 002.ext ... and return the kept files."""
    log = log or (lambda _m: None)
    os.makedirs(folder, exist_ok=True)
    results: dict[int, str | None] = {}
    done = 0

    def job(i: int, url: str) -> tuple[int, str | None, str]:
        if cancelled():
            return i, None, "cancelled"
        tmp = os.path.join(folder, f"{i + 1:03d}.part")
        try:
            _fetch(url, tmp, timeout)
        except Exception as exc:  # noqa: BLE001
            _rm(tmp)
            return i, None, f"download failed: {exc}"
        ok, info = _verify(tmp, min_w, min_h)
        if not ok:
            _rm(tmp)
            return i, None, info
        ext = {"jpeg": ".jpg", "png": ".png", "webp": ".webp", "gif": ".gif", "bmp": ".bmp"}.get(info, ".jpg")
        final = os.path.join(folder, f"{i + 1:03d}{ext}")
        os.replace(tmp, final)
        return i, final, "ok"

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(job, i, u) for i, u in enumerate(urls)]
        for fut in as_completed(futures):
            i, path, info = fut.result()
            results[i] = path
            done += 1
            if path is None:
                log(f"skipped {urls[i]}: {info}")
            if progress:
                progress(done, len(urls))
            if cancelled():
                for f in futures:
                    f.cancel()
                break
    return [results[i] for i in sorted(results) if results[i]]


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
