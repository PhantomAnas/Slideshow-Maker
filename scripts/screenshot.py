"""Render the main window with sample photos and save docs/screenshot.png.

    python scripts/screenshot.py

Uses a throw-away settings file so the real user config is untouched.  On
Windows the real platform is used (offscreen has no system fonts), so the
window appears for a moment.
"""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import slideshow_maker.settings as settings_mod  # noqa: E402

tmp = tempfile.mkdtemp(prefix="slideshow-shot-")
settings_mod.config_path = lambda: os.path.join(tmp, "settings.json")  # type: ignore[assignment]

import make_samples  # noqa: E402

samples = os.path.join(tmp, "samples")
make_samples.main(samples)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slideshow_maker.app.main_window import MainWindow  # noqa: E402
from slideshow_maker.app.theme import STYLESHEET  # noqa: E402
from slideshow_maker.imaging import list_images  # noqa: E402

app = QApplication(sys.argv)
app.setStyleSheet(STYLESHEET)
s = settings_mod.RenderSettings(music_path=os.path.join(tmp, "chill_track.mp3"), output_folder=os.path.join(tmp, "out"))
open(s.music_path, "wb").close()
win = MainWindow(s)
win.resize(1400, 900)
win.thumbs.add_paths(list_images(samples))
win.scrub.setValue(380)
win._log("ready: 6 photos, 9:16, Ken Burns, crossfade")
win.show()


def shoot() -> None:
    out = os.path.join(ROOT, "docs", "screenshot.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    win.grab().save(out)
    print("wrote", out)
    app.quit()


QTimer.singleShot(2500, shoot)   # let thumbnails and the preview frame arrive
app.exec()
