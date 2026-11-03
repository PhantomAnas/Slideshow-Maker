"""Reusable pieces: wallpaper backdrop, glass card, pill buttons, segmented
control, labelled slider, file picker row, thumbnail strip."""

from __future__ import annotations

import os
import random

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import icons


# ----------------------------------------------------------------- backdrop

def generate_wallpaper(width: int, height: int, seed: int = 7) -> QPixmap:
    """A soft, dark 'aurora' wallpaper: gradient base plus blurred colour blobs."""
    pm = QPixmap(max(16, width), max(16, height))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    base = QLinearGradient(0, 0, width, height)
    base.setColorAt(0.0, QColor("#141a33"))
    base.setColorAt(0.5, QColor("#1a1230"))
    base.setColorAt(1.0, QColor("#0b1a2b"))
    p.fillRect(pm.rect(), QBrush(base))
    rng = random.Random(seed)
    palette = ["#4f46e5", "#0ea5e9", "#a855f7", "#ec4899", "#14b8a6", "#f59e0b"]
    for i in range(6):
        cx, cy = rng.uniform(0, width), rng.uniform(0, height)
        r = rng.uniform(0.25, 0.55) * max(width, height)
        g = QRadialGradient(cx, cy, r)
        c = QColor(palette[i % len(palette)])
        c.setAlphaF(0.32)
        g.setColorAt(0.0, c)
        c2 = QColor(c)
        c2.setAlphaF(0.0)
        g.setColorAt(1.0, c2)
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
    p.end()
    return pm


class Backdrop(QWidget):
    """Paints a wallpaper (user image or generated) scaled to cover; children sit on top."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: QPixmap | None = None
        self._scaled: QPixmap | None = None
        self._dim = 0.35
        self.setAutoFillBackground(False)

    def set_image(self, path: str | None) -> bool:
        if path and os.path.isfile(path):
            pm = QPixmap(path)
            if not pm.isNull():
                self._source = pm
                self._scaled = None
                self.update()
                return True
        self._source = None
        self._scaled = None
        self.update()
        return False

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        if self._source is None:
            if self._scaled is None or self._scaled.size() != self.size():
                self._scaled = generate_wallpaper(w, h)
            p.drawPixmap(0, 0, self._scaled)
        else:
            if self._scaled is None or self._scaled.size() != self.size():
                scaled = self._source.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                             Qt.TransformationMode.SmoothTransformation)
                x = (scaled.width() - w) // 2
                y = (scaled.height() - h) // 2
                self._scaled = scaled.copy(x, y, w, h)
            p.drawPixmap(0, 0, self._scaled)
            p.fillRect(self.rect(), QColor(0, 0, 0, int(255 * self._dim)))
        p.end()


# ---------------------------------------------------------------------- card

class GlassCard(QFrame):
    def __init__(self, title: str | None = None, icon_name: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 18)
        self.body.setSpacing(12)
        if title:
            head = QHBoxLayout()
            head.setSpacing(8)
            if icon_name:
                ic = QLabel()
                ic.setPixmap(icons.pixmap(icon_name, 18, "#ffffff", dpr=self.devicePixelRatioF()))
                head.addWidget(ic)
            lbl = QLabel(title)
            lbl.setObjectName("CardTitle")
            head.addWidget(lbl)
            head.addStretch(1)
            self.head = head
            self.body.addLayout(head)


# ------------------------------------------------------------------- buttons

def pill(text: str, icon_name: str | None = None, kind: str = "", tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    if icon_name:
        color = "#06230f" if kind == "Go" else "#ffffff"
        b.setIcon(icons.icon(icon_name, color, filled=(icon_name == "play")))
        b.setIconSize(icons.ICON_SIZE)
    if kind:
        b.setObjectName(kind)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def round_button(icon_name: str, tooltip: str = "") -> QPushButton:
    b = QPushButton()
    b.setObjectName("Round")
    b.setIcon(icons.icon(icon_name))
    b.setIconSize(QSize(18, 18))
    b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class Segmented(QFrame):
    """iOS segmented control.  `changed(str)` emits the selected key."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SegGroup")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            b = QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b)
            lay.addWidget(b)
            self._buttons[key] = b
            b.toggled.connect(lambda on, k=key: on and self.changed.emit(k))

    def set_value(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def value(self) -> str:
        for k, b in self._buttons.items():
            if b.isChecked():
                return k
        return next(iter(self._buttons))


class LabeledSlider(QWidget):
    """Slider with a caption and a live value label.  Works in float units."""

    valueChanged = Signal(float)

    def __init__(self, caption: str, lo: float, hi: float, step: float, fmt: str = "{:.1f}",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lo, self.step, self.fmt = lo, step, fmt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        self.caption = QLabel(caption)
        self.caption.setObjectName("Hint")
        self.value_lbl = QLabel()
        self.value_lbl.setObjectName("Hint")
        top.addWidget(self.caption)
        top.addStretch(1)
        top.addWidget(self.value_lbl)
        lay.addLayout(top)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, int(round((hi - lo) / step)))
        self.slider.valueChanged.connect(self._on_change)
        lay.addWidget(self.slider)

    def _on_change(self, raw: int) -> None:
        v = self.value()
        self.value_lbl.setText(self.fmt.format(v))
        self.valueChanged.emit(v)

    def value(self) -> float:
        return self.lo + self.slider.value() * self.step

    def set_value(self, v: float) -> None:
        self.slider.setValue(int(round((v - self.lo) / self.step)))
        self.value_lbl.setText(self.fmt.format(self.value()))


class FilePicker(QWidget):
    """[icon] caption / filename ........ (Choose) (x)"""

    changed = Signal(str)

    def __init__(self, caption: str, icon_name: str, mode: str = "file", filter_: str = "",
                 placeholder: str = "None", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode, self.filter_, self.placeholder = mode, filter_, placeholder
        self._path = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 18, "#ffffff", dpr=self.devicePixelRatioF()))
        lay.addWidget(ic)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.cap = QLabel(caption)
        self.cap.setObjectName("Hint")
        self.name = QLabel(placeholder)
        self.name.setObjectName("Faint")
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.addWidget(self.cap)
        text.addWidget(self.name)
        lay.addLayout(text, 1)
        self.choose = pill("Choose")
        self.clear_btn = round_button("x", "Clear")
        self.clear_btn.setVisible(False)
        lay.addWidget(self.choose)
        lay.addWidget(self.clear_btn)
        self.choose.clicked.connect(self._pick)
        self.clear_btn.clicked.connect(lambda: self.set_path(""))

    def _pick(self) -> None:
        start = os.path.dirname(self._path) if self._path else os.path.expanduser("~")
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, self.cap.text(), start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self.cap.text(), start, self.filter_)
        if path:
            self.set_path(os.path.normpath(path))

    def set_path(self, path: str) -> None:
        self._path = path or ""
        if self._path:
            self.name.setText(os.path.basename(self._path) or self._path)
            self.name.setObjectName("Hint")
            self.name.setToolTip(self._path)
        else:
            self.name.setText(self.placeholder)
            self.name.setObjectName("Faint")
            self.name.setToolTip("")
        self.name.style().unpolish(self.name)
        self.name.style().polish(self.name)
        self.clear_btn.setVisible(bool(self._path))
        self.changed.emit(self._path)

    def path(self) -> str:
        return self._path


# --------------------------------------------------------------- thumbnails

class _ThumbSignals(QObject):
    done = Signal(str, QImage)


class _ThumbJob(QRunnable):
    def __init__(self, path: str, size: int, signals: _ThumbSignals) -> None:
        super().__init__()
        self.path, self.size, self.signals = path, size, signals

    def run(self) -> None:
        reader = QImageReader(self.path)
        reader.setAutoTransform(True)
        src = reader.size()
        if src.isValid():
            scale = max(self.size / max(1, src.width()), self.size / max(1, src.height()))
            reader.setScaledSize(QSize(max(1, int(src.width() * scale)), max(1, int(src.height() * scale))))
        img = reader.read()
        if not img.isNull():
            # centre-crop to a square
            s = min(img.width(), img.height())
            img = img.copy((img.width() - s) // 2, (img.height() - s) // 2, s, s)
        self.signals.done.emit(self.path, img)


class ThumbStrip(QListWidget):
    """Reorderable thumbnail grid of the chosen photos."""

    changed = Signal()
    unreadable = Signal(str)        # a file that could not be decoded was dropped
    THUMB = 96

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(self.THUMB, self.THUMB))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(6)
        self.setUniformItemSizes(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self._signals = _ThumbSignals()
        self._signals.done.connect(self._thumb_ready)
        self._pool = QThreadPool.globalInstance()
        self.model().rowsMoved.connect(lambda *_: self.changed.emit())
        self.model().rowsRemoved.connect(lambda *_: self.changed.emit())

    def paths(self) -> list[str]:
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]

    def add_paths(self, paths: list[str]) -> int:
        existing = set(self.paths())
        added = 0
        for p in paths:
            if p in existing:
                continue
            existing.add(p)
            item = QListWidgetItem(os.path.basename(p))
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(p)
            item.setSizeHint(QSize(self.THUMB + 12, self.THUMB + 30))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setIcon(icons.icon("image", "#9aa0b4"))
            self.addItem(item)
            self._pool.start(_ThumbJob(p, self.THUMB * 2, self._signals))
            added += 1
        if added:
            self.changed.emit()
        return added

    def remove_selected(self) -> None:
        for item in self.selectedItems():
            self.takeItem(self.row(item))
        self.changed.emit()

    def clear_all(self) -> None:
        self.clear()
        self.changed.emit()

    def _thumb_ready(self, path: str, img: QImage) -> None:
        if img.isNull():
            for i in range(self.count()):
                if self.item(i).data(Qt.ItemDataRole.UserRole) == path:
                    self.takeItem(i)
                    break
            self.unreadable.emit(path)
            self.changed.emit()
            return
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(2.0)
        for i in range(self.count()):
            it = self.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == path:
                it.setIcon(QPixmap(pm))
                break

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_selected()
            return
        super().keyPressEvent(event)
