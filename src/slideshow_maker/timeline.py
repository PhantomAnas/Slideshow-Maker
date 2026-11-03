"""Timing math: which image is on screen at time t, and how far into a transition.

Pure functions, no I/O, so the GUI's preview scrubber, the duration label and
the renderer all agree.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    index: int
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(frozen=True)
class FrameState:
    """What to draw at a given time."""
    current: int                 # image index on screen
    progress: float              # 0..1 through that image's slot (drives motion)
    incoming: int | None = None  # next image during a transition
    incoming_progress: float = 0.0
    blend: float = 0.0           # 0 = fully current, 1 = fully incoming


@dataclass(frozen=True)
class Timeline:
    slots: tuple[Slot, ...]
    transition: float

    @property
    def total(self) -> float:
        return self.slots[-1].end if self.slots else 0.0

    def state_at(self, t: float) -> FrameState:
        if not self.slots:
            raise ValueError("empty timeline")
        t = min(max(0.0, t), max(0.0, self.total - 1e-9))
        # The first slot that has not ended yet owns the time; during an
        # overlap that is the *outgoing* image, and the next one blends in.
        idx = len(self.slots) - 1
        for i, s in enumerate(self.slots):
            if t < s.end:
                idx = i
                break
        cur = self.slots[idx]
        prog = (t - cur.start) / cur.duration if cur.duration > 0 else 1.0
        # Transition into the next slot occupies the last `transition`
        # seconds of this slot (slots overlap by that much).
        if idx + 1 < len(self.slots) and self.transition > 0:
            nxt = self.slots[idx + 1]
            if t >= nxt.start:
                blend = (t - nxt.start) / self.transition
                nxt_prog = (t - nxt.start) / nxt.duration if nxt.duration > 0 else 0.0
                return FrameState(idx, min(1.0, prog), idx + 1, min(1.0, nxt_prog), min(1.0, blend))
        return FrameState(idx, min(1.0, prog))


def per_image_seconds(n_images: int, seconds_per_image: float, total_seconds: float,
                      transition: float, end_card_seconds: float = 0.0,
                      has_end_card: bool = False) -> float:
    """Seconds each regular image stays on screen.

    With `total_seconds` set, the per-image time is solved so the whole video
    (including transitions overlap and the end card) lasts exactly that long.
    """
    if n_images <= 0:
        return 0.0
    if total_seconds and total_seconds > 0:
        n_slots = n_images + (1 if has_end_card else 0)
        overlap = transition * max(0, n_slots - 1)
        budget = total_seconds + overlap - (end_card_seconds if has_end_card else 0.0)
        per = budget / n_images
        # Never shorter than the transition itself, or slots would overlap twice.
        return max(per, transition + 0.05)
    return max(seconds_per_image, transition + 0.05) if transition else seconds_per_image


def build_timeline(durations: list[float], transition: float) -> Timeline:
    """Lay slots back to back, each overlapping the previous by `transition`."""
    slots: list[Slot] = []
    t = 0.0
    for i, d in enumerate(durations):
        d = max(0.05, float(d))
        slots.append(Slot(i, t, d))
        t += d - (transition if i < len(durations) - 1 else 0.0)
    return Timeline(tuple(slots), transition if len(durations) > 1 else 0.0)
