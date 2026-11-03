"""Background workers: the render job and the preview frame."""

from __future__ import annotations

import copy
import threading
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage

from .. import batch, render
from ..settings import RenderSettings


class RenderWorker(QObject):
    """Runs `batch.run_job` on a QThread.  All signals are delivered on the GUI thread."""

    log = Signal(str)
    stage = Signal(str)
    progress = Signal(int, int)
    finished = Signal(list)          # output paths
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._cancel = threading.Event()
        self.settings = RenderSettings()
        self.images: list[str] | None = None

    def cancel(self) -> None:
        self._cancel.set()

    def start(self, settings: RenderSettings, images: list[str] | None) -> None:
        self._cancel.clear()
        self.settings = copy.deepcopy(settings)
        self.images = list(images) if images else None

    def run(self) -> None:
        try:
            outputs = batch.run_job(self.settings, self.images, log=self.log.emit,
                                    stage=self.stage.emit, progress=self.progress.emit,
                                    cancelled=self._cancel.is_set)
        except render.RenderCancelled:
            self.cancelled.emit()
            return
        except render.RenderError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:  # noqa: BLE001 - surface anything else in the log
            self.failed.emit("unexpected error:\n" + traceback.format_exc())
            return
        self.finished.emit(outputs)


class PreviewSignals(QObject):
    ready = Signal(int, QImage)      # request id, frame
    failed = Signal(int, str)


class PreviewJob(QRunnable):
    """Composes one frame at reduced size on the thread pool."""

    def __init__(self, request_id: int, images: list[str], settings: RenderSettings,
                 t: float, max_side: int, signals: PreviewSignals) -> None:
        super().__init__()
        self.request_id, self.images, self.t, self.max_side, self.signals = request_id, images, t, max_side, signals
        self.settings = copy.deepcopy(settings)

    def run(self) -> None:
        try:
            s = self.settings
            w, h = s.even_size
            scale = min(1.0, self.max_side / max(w, h))
            s.width = max(32, int(w * scale) // 2 * 2)
            s.height = max(32, int(h * scale) // 2 * 2)
            plan = render.make_plan(self.images, s)
            composer = render.FrameComposer(plan, s)
            frame = composer.frame_at(min(self.t, plan.timeline.total))
            img = QImage(frame.data, frame.shape[1], frame.shape[0], frame.shape[1] * 3,
                         QImage.Format.Format_RGB888).copy()
            self.signals.ready.emit(self.request_id, img)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.request_id, str(exc))
