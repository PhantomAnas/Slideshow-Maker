"""The Slideshow Maker window."""

from __future__ import annotations

import ctypes
import os
import sys

from .. import __version__
from ..settings import ASPECT_PRESETS, APP_NAME, RenderSettings


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    for attempt in (
        lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
        lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
        lambda: ctypes.windll.user32.SetProcessDPIAware(),
    ):
        try:
            attempt()
            return
        except Exception:  # noqa: BLE001
            continue


enable_dpi_awareness()

from PySide6.QtCore import QThread, QThreadPool, QTimer, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import ffmpeg as ff  # noqa: E402
from ..downloader import read_links_file  # noqa: E402
from ..imaging import IMAGE_EXTENSIONS, list_images  # noqa: E402
from ..render import estimate_total_seconds  # noqa: E402
from . import icons  # noqa: E402
from .theme import STYLESHEET  # noqa: E402
from .widgets import (  # noqa: E402
    Backdrop,
    FilePicker,
    GlassCard,
    LabeledSlider,
    Segmented,
    ThumbStrip,
    pill,
    round_button,
)
from .worker import PreviewJob, PreviewSignals, RenderWorker  # noqa: E402

IMAGE_FILTER = "Images (" + " ".join(f"*{e}" for e in sorted(IMAGE_EXTENSIONS)) + ")"
AUDIO_FILTER = "Audio (*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.opus)"


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"))
    return os.path.join(base, name)


def app_icon() -> QIcon:
    for name in ("icon.ico", "icon.png"):
        p = resource_path(name)
        if os.path.exists(p):
            return QIcon(p)
    return icons.icon("film")


def fmt_seconds(s: float) -> str:
    m, sec = divmod(int(round(s)), 60)
    return f"{m}:{sec:02d}" if m else f"{sec}s"


class MainWindow(QMainWindow):
    def __init__(self, settings: RenderSettings) -> None:
        super().__init__()
        self.s = settings
        self.setWindowTitle("Slideshow Maker")
        self.setWindowIcon(app_icon())
        self.resize(1380, 860)
        self.setMinimumSize(1100, 700)
        self._loading = True
        self._preview_id = 0
        self._preview_signals = PreviewSignals()
        self._preview_signals.ready.connect(self._preview_ready)
        self._preview_signals.failed.connect(self._preview_failed)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._request_preview)
        self._outputs: list[str] = []

        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)
        self.setAcceptDrops(True)
        self.backdrop.set_image(self.s.extra.get("wallpaper"))
        self._build()
        self._build_worker()
        self._apply_settings()
        self._loading = False
        self._refresh_summary()
        self._check_ffmpeg()

    # ------------------------------------------------------------- layout
    def _build(self) -> None:
        root = QHBoxLayout(self.backdrop)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(18)

        # Left: scrollable settings column
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        col = QWidget()
        left = QVBoxLayout(col)
        left.setContentsMargins(0, 0, 8, 0)
        left.setSpacing(14)
        scroll.setWidget(col)
        root.addWidget(scroll, 5)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.pixmap("film", 28, "#ffffff", dpr=self.devicePixelRatioF()))
        title = QLabel("Slideshow Maker")
        title.setObjectName("Title")
        header.addWidget(logo)
        header.addSpacing(6)
        header.addWidget(title)
        header.addStretch(1)
        self.wallpaper_btn = round_button("settings", "Change wallpaper")
        self.wallpaper_btn.clicked.connect(self._pick_wallpaper)
        header.addWidget(self.wallpaper_btn)
        left.addLayout(header)

        left.addWidget(self._photos_card())
        left.addWidget(self._look_card())
        left.addWidget(self._branding_card())
        left.addWidget(self._music_card())
        left.addWidget(self._output_card())
        left.addStretch(1)

        # Right: preview + render
        right = QVBoxLayout()
        right.setSpacing(14)
        right.addWidget(self._preview_card(), 1)
        right.addWidget(self._render_card())
        root.addLayout(right, 4)

    def _photos_card(self) -> GlassCard:
        card = GlassCard("Photos", "photo")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.add_btn = pill("Add photos", "photo")
        self.add_folder_btn = pill("Add folder", "folder")
        self.links_btn = pill("From URL list", "link", tooltip="A .txt with one image URL per line; downloaded when you render")
        self.remove_btn = round_button("x", "Remove selected (Delete)")
        self.clear_btn = round_button("trash", "Clear all")
        for b in (self.add_btn, self.add_folder_btn, self.links_btn):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.remove_btn)
        row.addWidget(self.clear_btn)
        card.body.addLayout(row)

        self.links_banner = QWidget()
        lb = QHBoxLayout(self.links_banner)
        lb.setContentsMargins(0, 0, 0, 0)
        self.links_label = QLabel()
        self.links_label.setObjectName("Hint")
        self.links_clear = round_button("x", "Stop using the URL list")
        lb.addWidget(self.links_label, 1)
        lb.addWidget(self.links_clear)
        self.links_banner.setVisible(False)
        card.body.addWidget(self.links_banner)

        self.thumbs = ThumbStrip()
        self.thumbs.setMinimumHeight(190)
        card.body.addWidget(self.thumbs)
        self.photos_hint = QLabel("Drag thumbnails to reorder. Delete removes the selection.")
        self.photos_hint.setObjectName("Faint")
        card.body.addWidget(self.photos_hint)

        self.add_btn.clicked.connect(self._add_photos)
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.links_btn.clicked.connect(self._pick_links)
        self.links_clear.clicked.connect(lambda: self._set_links(""))
        self.remove_btn.clicked.connect(self.thumbs.remove_selected)
        self.clear_btn.clicked.connect(self.thumbs.clear_all)
        self.thumbs.changed.connect(self._on_photos_changed)
        self.thumbs.unreadable.connect(lambda p: self._log(f"removed {os.path.basename(p)}: not a readable image"))
        return card

    def _look_card(self) -> GlassCard:
        card = GlassCard("Look", "wand")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        grid.addWidget(self._hint("Canvas"), 0, 0)
        self.aspect = QComboBox()
        for k in ASPECT_PRESETS:
            self.aspect.addItem(k)
        self.aspect.addItem("Custom...")
        grid.addWidget(self.aspect, 1, 0)
        size_row = QHBoxLayout()
        self.width_spin = QSpinBox(); self.width_spin.setRange(64, 7680); self.width_spin.setSuffix(" px")
        self.height_spin = QSpinBox(); self.height_spin.setRange(64, 7680); self.height_spin.setSuffix(" px")
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(1, 120); self.fps_spin.setSuffix(" fps")
        for w in (self.width_spin, self.height_spin, self.fps_spin):
            size_row.addWidget(w)
        grid.addLayout(size_row, 1, 1)

        grid.addWidget(self._hint("Fill"), 2, 0)
        self.fit = Segmented([("blur", "Blur fill"), ("crop", "Crop"), ("contain", "Letterbox")])
        grid.addWidget(self.fit, 3, 0)
        grid.addWidget(self._hint("Transition"), 2, 1)
        self.transition = Segmented([("crossfade", "Fade"), ("slide", "Slide"), ("fade_black", "Dip"), ("none", "Cut")])
        grid.addWidget(self.transition, 3, 1)

        self.motion_chk = QCheckBox("Ken Burns motion (slow zoom and drift)")
        grid.addWidget(self.motion_chk, 4, 0, 1, 2)
        self.motion_slider = LabeledSlider("Motion strength", 0.02, 0.4, 0.01, "{:.0%}")
        grid.addWidget(self.motion_slider, 5, 0)
        self.transition_slider = LabeledSlider("Transition length", 0.1, 2.0, 0.05, "{:.2f} s")
        grid.addWidget(self.transition_slider, 5, 1)

        grid.addWidget(self._hint("Timing"), 6, 0, 1, 2)
        timing = QHBoxLayout()
        self.timing_mode = Segmented([("per", "Per photo"), ("total", "Total length")])
        self.per_image = QDoubleSpinBox(); self.per_image.setRange(0.3, 60); self.per_image.setSuffix(" s each"); self.per_image.setDecimals(1)
        self.total = QDoubleSpinBox(); self.total.setRange(1, 3600); self.total.setSuffix(" s total"); self.total.setDecimals(1)
        timing.addWidget(self.timing_mode)
        timing.addWidget(self.per_image)
        timing.addWidget(self.total)
        timing.addStretch(1)
        grid.addLayout(timing, 7, 0, 1, 2)
        card.body.addLayout(grid)

        self.aspect.currentIndexChanged.connect(self._on_aspect)
        for w in (self.width_spin, self.height_spin, self.fps_spin):
            w.valueChanged.connect(self._on_size_edit)
        self.fit.changed.connect(self._settings_edited)
        self.transition.changed.connect(self._settings_edited)
        self.motion_chk.toggled.connect(self._settings_edited)
        self.motion_slider.valueChanged.connect(self._settings_edited)
        self.transition_slider.valueChanged.connect(self._settings_edited)
        self.timing_mode.changed.connect(self._on_timing_mode)
        self.per_image.valueChanged.connect(self._settings_edited)
        self.total.valueChanged.connect(self._settings_edited)
        return card

    def _branding_card(self) -> GlassCard:
        card = GlassCard("Logo & end card", "tag")
        self.logo_pick = FilePicker("Logo overlay (PNG with transparency works best)", "tag", "file", IMAGE_FILTER)
        card.body.addWidget(self.logo_pick)
        row = QHBoxLayout()
        self.logo_pos = QComboBox()
        for k, label in (("bottom-right", "Bottom right"), ("bottom-left", "Bottom left"),
                         ("top-right", "Top right"), ("top-left", "Top left"), ("center", "Center")):
            self.logo_pos.addItem(label, k)
        self.logo_size = LabeledSlider("Logo size", 0.05, 0.6, 0.01, "{:.0%} of width")
        self.logo_opacity = LabeledSlider("Opacity", 0.1, 1.0, 0.05, "{:.0%}")
        row.addWidget(self.logo_pos)
        row.addWidget(self.logo_size, 1)
        row.addWidget(self.logo_opacity, 1)
        card.body.addLayout(row)
        self.end_pick = FilePicker("End card shown after the last photo", "image", "file", IMAGE_FILTER)
        card.body.addWidget(self.end_pick)
        self.end_seconds = QDoubleSpinBox(); self.end_seconds.setRange(0.5, 30); self.end_seconds.setSuffix(" s on screen"); self.end_seconds.setDecimals(1)
        self.end_seconds.setFixedWidth(160)
        card.body.addWidget(self.end_seconds, 0, Qt.AlignmentFlag.AlignLeft)

        self.logo_pick.changed.connect(self._settings_edited)
        self.logo_pos.currentIndexChanged.connect(self._settings_edited)
        self.logo_size.valueChanged.connect(self._settings_edited)
        self.logo_opacity.valueChanged.connect(self._settings_edited)
        self.end_pick.changed.connect(self._settings_edited)
        self.end_seconds.valueChanged.connect(self._settings_edited)
        return card

    def _music_card(self) -> GlassCard:
        card = GlassCard("Music", "music")
        row = QHBoxLayout()
        self.music_pick = FilePicker("Track, or a folder to pick a random track from", "music", "file", AUDIO_FILTER)
        self.music_folder_btn = pill("Folder", "folder", tooltip="Pick a folder: each video gets a random track")
        row.addWidget(self.music_pick, 1)
        row.addWidget(self.music_folder_btn)
        card.body.addLayout(row)
        row2 = QHBoxLayout()
        self.volume = LabeledSlider("Volume", 0.0, 1.5, 0.05, "{:.0%}")
        self.fade = LabeledSlider("Fade out at the end", 0.0, 6.0, 0.5, "{:.1f} s")
        row2.addWidget(self.volume, 1)
        row2.addWidget(self.fade, 1)
        card.body.addLayout(row2)
        self.music_folder_btn.clicked.connect(self._pick_music_folder)
        self.music_pick.changed.connect(self._settings_edited)
        self.volume.valueChanged.connect(self._settings_edited)
        self.fade.valueChanged.connect(self._settings_edited)
        return card

    def _output_card(self) -> GlassCard:
        card = GlassCard("Output", "folder")
        self.out_pick = FilePicker("Save videos to", "folder", "dir", placeholder="~/Videos/Slideshow Maker")
        card.body.addWidget(self.out_pick)
        row = QHBoxLayout()
        row.addWidget(self._hint("Split the photos into"))
        self.videos_spin = QSpinBox(); self.videos_spin.setRange(1, 200); self.videos_spin.setSuffix(" video(s)")
        row.addWidget(self.videos_spin)
        self.shuffle_chk = QCheckBox("Shuffle order")
        row.addSpacing(16)
        row.addWidget(self.shuffle_chk)
        row.addStretch(1)
        card.body.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(self._hint("Skip downloaded images smaller than"))
        self.min_size = QSpinBox(); self.min_size.setRange(0, 4000); self.min_size.setSuffix(" px")
        row2.addWidget(self.min_size)
        row2.addStretch(1)
        self.quality = QComboBox()
        for label, crf in (("Best quality", 17), ("Balanced", 20), ("Small file", 26)):
            self.quality.addItem(label, crf)
        row2.addWidget(self._hint("Quality"))
        row2.addWidget(self.quality)
        card.body.addLayout(row2)
        self.out_pick.changed.connect(self._settings_edited)
        self.videos_spin.valueChanged.connect(self._settings_edited)
        self.shuffle_chk.toggled.connect(self._settings_edited)
        self.min_size.valueChanged.connect(self._settings_edited)
        self.quality.currentIndexChanged.connect(self._settings_edited)
        return card

    def _preview_card(self) -> GlassCard:
        card = GlassCard("Preview", "image")
        self.refresh_btn = round_button("refresh", "Refresh preview")
        card.head.addWidget(self.refresh_btn)
        self.preview = QLabel("Add photos to see a preview")
        self.preview.setObjectName("Hint")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 320)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.body.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setRange(0, 1000)
        self.time_lbl = QLabel("0:00")
        self.time_lbl.setObjectName("Hint")
        self.time_lbl.setFixedWidth(80)
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(self.scrub, 1)
        row.addWidget(self.time_lbl)
        card.body.addLayout(row)
        self.summary = QLabel()
        self.summary.setObjectName("Hint")
        self.summary.setWordWrap(True)
        card.body.addWidget(self.summary)
        self.scrub.valueChanged.connect(self._on_scrub)
        self.refresh_btn.clicked.connect(self._request_preview)
        return card

    def _render_card(self) -> GlassCard:
        card = GlassCard()
        row = QHBoxLayout()
        self.render_btn = pill("Render video", "play", "Go")
        self.cancel_btn = pill("Cancel", "stop", "Danger")
        self.cancel_btn.setEnabled(False)
        self.open_btn = pill("Open output folder", "open")
        row.addWidget(self.render_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        row.addWidget(self.open_btn)
        card.body.addLayout(row)
        self.stage_lbl = QLabel("Ready")
        self.stage_lbl.setObjectName("Hint")
        card.body.addWidget(self.stage_lbl)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFixedHeight(10)
        card.body.addWidget(self.progress)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setFixedHeight(120)
        card.body.addWidget(self.log_view)
        self.render_btn.clicked.connect(self._render)
        self.cancel_btn.clicked.connect(self._cancel)
        self.open_btn.clicked.connect(self._open_output)
        return card

    @staticmethod
    def _hint(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Hint")
        return lbl

    # ------------------------------------------------------------- worker
    def _build_worker(self) -> None:
        self.thread = QThread(self)
        self.worker = RenderWorker()
        self.worker.moveToThread(self.thread)
        self.worker.log.connect(self._log)
        self.worker.stage.connect(self._on_stage)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.thread.started.connect(self.worker.run)

    # ------------------------------------------------------- settings I/O
    def _apply_settings(self) -> None:
        s = self.s
        self.thumbs.add_paths([p for p in s.extra.get("photos", []) if os.path.isfile(p)])
        self._set_links(s.links_file, quiet=True)
        preset = next((k for k, v in ASPECT_PRESETS.items() if v == (s.width, s.height)), "Custom...")
        self.aspect.setCurrentText(preset)
        self.width_spin.setValue(s.width)
        self.height_spin.setValue(s.height)
        self.fps_spin.setValue(s.fps)
        self.fit.set_value(s.fit)
        self.transition.set_value(s.transition)
        self.motion_chk.setChecked(s.motion == "kenburns")
        self.motion_slider.set_value(s.motion_strength)
        self.transition_slider.set_value(s.transition_seconds)
        self.timing_mode.set_value("total" if s.total_seconds > 0 else "per")
        self.per_image.setValue(s.seconds_per_image)
        self.total.setValue(s.total_seconds or 30.0)
        self._on_timing_mode(self.timing_mode.value())
        self.logo_pick.set_path(s.logo_path)
        self.logo_pos.setCurrentIndex(max(0, self.logo_pos.findData(s.logo_position)))
        self.logo_size.set_value(s.logo_scale)
        self.logo_opacity.set_value(s.logo_opacity)
        self.end_pick.set_path(s.end_card_path)
        self.end_seconds.setValue(s.end_card_seconds)
        self.music_pick.set_path(s.music_path)
        self.volume.set_value(s.music_volume)
        self.fade.set_value(s.music_fade_out)
        self.out_pick.set_path(s.output_folder)
        self.videos_spin.setValue(s.videos_count)
        self.shuffle_chk.setChecked(s.shuffle)
        self.min_size.setValue(s.min_image_width)
        idx = self.quality.findData(s.crf)
        self.quality.setCurrentIndex(idx if idx >= 0 else 1)

    def _collect_settings(self) -> RenderSettings:
        s = self.s
        s.width, s.height, s.fps = self.width_spin.value(), self.height_spin.value(), self.fps_spin.value()
        s.fit = self.fit.value()
        s.transition = self.transition.value()
        s.motion = "kenburns" if self.motion_chk.isChecked() else "none"
        s.motion_strength = self.motion_slider.value()
        s.transition_seconds = self.transition_slider.value()
        s.seconds_per_image = self.per_image.value()
        s.total_seconds = self.total.value() if self.timing_mode.value() == "total" else 0.0
        s.logo_path = self.logo_pick.path()
        s.logo_position = self.logo_pos.currentData()
        s.logo_scale = self.logo_size.value()
        s.logo_opacity = self.logo_opacity.value()
        s.end_card_path = self.end_pick.path()
        s.end_card_seconds = self.end_seconds.value()
        s.music_path = self.music_pick.path()
        s.music_volume = self.volume.value()
        s.music_fade_out = self.fade.value()
        s.output_folder = self.out_pick.path()
        s.videos_count = self.videos_spin.value()
        s.shuffle = self.shuffle_chk.isChecked()
        s.min_image_width = s.min_image_height = self.min_size.value()
        s.crf = self.quality.currentData() or 20
        s.extra["photos"] = self.thumbs.paths()
        return s

    def _save_settings(self) -> None:
        try:
            self._collect_settings().save()
        except OSError as exc:
            self._log(f"could not save settings: {exc}")

    # ----------------------------------------------------------- handlers
    def _settings_edited(self, *_args) -> None:
        if self._loading:
            return
        self._collect_settings()
        self._refresh_summary()
        self._preview_timer.start()

    def _on_aspect(self, _idx: int) -> None:
        key = self.aspect.currentText()
        custom = key == "Custom..."
        if not custom and key in ASPECT_PRESETS:
            w, h = ASPECT_PRESETS[key]
            self._loading, was = True, self._loading
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)
            self._loading = was
        self.width_spin.setEnabled(custom)
        self.height_spin.setEnabled(custom)
        self._settings_edited()

    def _on_size_edit(self, _v: int) -> None:
        self._settings_edited()

    def _on_timing_mode(self, key: str) -> None:
        self.per_image.setVisible(key == "per")
        self.total.setVisible(key == "total")
        self._settings_edited()

    def _on_photos_changed(self) -> None:
        n = self.thumbs.count()
        self.photos_hint.setText(f"{n} photo(s). Drag thumbnails to reorder. Delete removes the selection."
                                 if n else "Drag thumbnails to reorder. Delete removes the selection.")
        self._settings_edited()

    def _add_photos(self) -> None:
        start = self.s.source_folder or os.path.expanduser("~")
        files, _ = QFileDialog.getOpenFileNames(self, "Add photos", start, IMAGE_FILTER)
        if files:
            self.s.source_folder = os.path.dirname(files[0])
            self.thumbs.add_paths([os.path.normpath(f) for f in files])

    def _add_folder(self) -> None:
        start = self.s.source_folder or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Add every image in a folder", start)
        if folder:
            self.s.source_folder = folder
            n = self.thumbs.add_paths(list_images(folder))
            self._log(f"added {n} image(s) from {folder}")

    def _pick_links(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Text file with image URLs", os.path.expanduser("~"), "Text (*.txt);;All files (*)")
        if path:
            self._set_links(os.path.normpath(path))

    def _set_links(self, path: str, quiet: bool = False) -> None:
        self.s.links_file = path
        if path and os.path.isfile(path):
            try:
                n = len(read_links_file(path))
            except OSError:
                n = 0
            self.links_label.setText(f"URL list: {os.path.basename(path)} ({n} links). Downloaded when you render; "
                                     "photos above are ignored while a list is set.")
            self.links_banner.setVisible(True)
            if not quiet:
                self._log(f"using URL list {path} ({n} links)")
        else:
            self.s.links_file = ""
            self.links_banner.setVisible(False)
        self._settings_edited()

    def _pick_music_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder of music tracks", os.path.expanduser("~"))
        if folder:
            self.music_pick.set_path(os.path.normpath(folder))

    def _pick_wallpaper(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Wallpaper image (Cancel to reset)", os.path.expanduser("~"), IMAGE_FILTER)
        self.s.extra["wallpaper"] = path or ""
        self.backdrop.set_image(path)
        self._save_settings()

    def _check_ffmpeg(self) -> None:
        v = ff.ffmpeg_version()
        if v:
            self._log(v)
        else:
            self._log(f"FFmpeg was not found on PATH. Install it from {ff.FFMPEG_DOWNLOAD_URL} and restart.")
            self.stage_lbl.setText("FFmpeg not found - rendering is disabled until it is installed")

    # ------------------------------------------------------------ summary
    def _refresh_summary(self) -> None:
        n = self.thumbs.count()
        s = self.s
        if s.links_file:
            try:
                n = len(read_links_file(s.links_file))
            except OSError:
                n = 0
        groups = max(1, min(s.videos_count, max(1, n)))
        per_group = -(-n // groups) if n else 0
        total = estimate_total_seconds(per_group, s)
        parts = [f"{s.width}x{s.height} @ {s.fps} fps"]
        if n:
            parts.append(f"{n} photos" + (f" in {groups} videos" if groups > 1 else ""))
            parts.append(f"about {fmt_seconds(total)} each" if groups > 1 else f"about {fmt_seconds(total)}")
        if s.music_path:
            parts.append("music " + os.path.basename(s.music_path))
        self.summary.setText("  ·  ".join(parts))
        self._preview_total = total

    def _on_scrub(self, _v: int) -> None:
        t = self._scrub_time()
        self.time_lbl.setText(fmt_seconds(t))
        self._preview_timer.start()

    def _scrub_time(self) -> float:
        return self.scrub.value() / 1000.0 * max(0.0, getattr(self, "_preview_total", 0.0))

    def _request_preview(self) -> None:
        paths = self.thumbs.paths()
        if not paths or self.s.links_file:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Add photos to see a preview" if not paths else "Preview is unavailable for URL lists until they are downloaded")
            return
        s = self._collect_settings()
        groups = max(1, min(s.videos_count, len(paths)))
        first_group = paths[: -(-len(paths) // groups)]
        self._preview_id += 1
        side = max(200, min(self.preview.width(), self.preview.height()))
        QThreadPool.globalInstance().start(
            PreviewJob(self._preview_id, first_group, s, self._scrub_time(), side, self._preview_signals))

    def _preview_ready(self, request_id: int, img) -> None:
        if request_id != self._preview_id:
            return
        pm = QPixmap.fromImage(img)
        self.preview.setText("")
        self.preview.setPixmap(pm.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))

    def _preview_failed(self, request_id: int, msg: str) -> None:
        if request_id == self._preview_id:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(f"Preview failed: {msg}")

    # Drag-and-drop: image files, folders of images, a .txt of URLs, audio.
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and not self.thread.isRunning():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        images, folders, texts, audio = [], [], [], []
        for url in event.mimeData().urls():
            p = os.path.normpath(url.toLocalFile())
            if not p:
                continue
            ext = os.path.splitext(p)[1].lower()
            if os.path.isdir(p):
                folders.append(p)
            elif ext in IMAGE_EXTENSIONS:
                images.append(p)
            elif ext == ".txt":
                texts.append(p)
            elif ext in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}:
                audio.append(p)
        for f in folders:
            images.extend(list_images(f))
        if images:
            n = self.thumbs.add_paths(images)
            self._log(f"added {n} image(s) by drag and drop")
        if texts:
            self._set_links(texts[0])
        if audio:
            self.music_pick.set_path(audio[0])
        if not (images or texts or audio):
            self._log("dropped items contained no images, folders, .txt lists or audio")
        event.acceptProposedAction()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._loading:
            self._preview_timer.start()

    # ------------------------------------------------------------- render
    def _render(self) -> None:
        s = self._collect_settings()
        photos = self.thumbs.paths()
        if not photos and not s.links_file:
            QMessageBox.information(self, "Slideshow Maker", "Add some photos (or a URL list) first.")
            return
        problems = s.validate()
        if problems:
            QMessageBox.warning(self, "Slideshow Maker", "Please fix:\n- " + "\n- ".join(problems))
            return
        if not ff.find_ffmpeg():
            QMessageBox.warning(self, "Slideshow Maker",
                                f"FFmpeg was not found.\n\nInstall it from {ff.FFMPEG_DOWNLOAD_URL} and make sure "
                                "'ffmpeg' works in a terminal, then restart the app.")
            return
        if s.links_file and not os.path.isfile(s.links_file):
            QMessageBox.warning(self, "Slideshow Maker", f"The URL list no longer exists:\n{s.links_file}")
            return
        missing = [p for p in photos if not os.path.isfile(p)]
        if missing and not s.links_file:
            self._log(f"{len(missing)} photo(s) no longer exist and were skipped")
            photos = [p for p in photos if os.path.isfile(p)]
            if not photos:
                QMessageBox.warning(self, "Slideshow Maker", "None of the photos exist on disk any more.")
                return
        if s.videos_count > len(photos) and not s.links_file:
            self._log(f"only {len(photos)} photos: rendering {len(photos)} video(s) instead of {s.videos_count}")
        self._save_settings()
        self.worker.start(s, None if s.links_file else photos)
        self._set_busy(True)
        self.progress.setValue(0)
        self.log_view.clear()
        self.thread.start()

    def _cancel(self) -> None:
        self.worker.cancel()
        self.stage_lbl.setText("Cancelling...")
        self.cancel_btn.setEnabled(False)

    def _set_busy(self, busy: bool) -> None:
        self.render_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        for w in (self.add_btn, self.add_folder_btn, self.links_btn, self.clear_btn, self.remove_btn):
            w.setEnabled(not busy)

    def _on_stage(self, text: str) -> None:
        self.stage_lbl.setText(text)
        self.progress.setValue(0)

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(int(done * 1000 / max(1, total)))

    def _finish_thread(self) -> None:
        self.thread.quit()
        self.thread.wait(5000)
        self._set_busy(False)

    def _on_finished(self, outputs: list) -> None:
        self._finish_thread()
        self._outputs = outputs
        self.progress.setValue(1000)
        self.stage_lbl.setText(f"Done: {len(outputs)} video(s) written")
        if outputs:
            self._log("finished: " + ", ".join(os.path.basename(p) for p in outputs))

    def _on_failed(self, msg: str) -> None:
        self._finish_thread()
        self.stage_lbl.setText("Failed")
        self._log("error: " + msg)
        QMessageBox.critical(self, "Render failed", msg)

    def _on_cancelled(self) -> None:
        self._finish_thread()
        self.stage_lbl.setText("Cancelled")
        self.progress.setValue(0)
        self._log("cancelled")

    def _open_output(self) -> None:
        folder = self.s.output_folder or os.path.join(os.path.expanduser("~"), "Videos", "Slideshow Maker")
        if self._outputs and os.path.isdir(os.path.dirname(self._outputs[-1])):
            folder = os.path.dirname(self._outputs[-1])
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.thread.isRunning():
            if QMessageBox.question(self, "Slideshow Maker", "A render is running. Cancel it and quit?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait(10000)
        self._save_settings()
        event.accept()


def main(argv: list[str] | None = None) -> int:
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())
    win = MainWindow(RenderSettings.load())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
