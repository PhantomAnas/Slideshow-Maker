"""Generate the app icon (PNG + ICO) with Qt only:  python scripts/make_icon.py"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "slideshow_maker", "assets")


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
    g = QLinearGradient(0, 0, s, s)
    g.setColorAt(0, QColor("#4f46e5"))
    g.setColorAt(1, QColor("#0ea5e9"))
    p.fillPath(tile, g)
    # Three stacked "photo" cards
    for i, (dx, dy, rot) in enumerate(((-0.08, 0.06, -12), (0.0, 0.0, 0), (0.08, -0.06, 12))):
        p.save()
        p.translate(s * (0.5 + dx), s * (0.5 + dy))
        p.rotate(rot)
        card = QPainterPath()
        card.addRoundedRect(QRectF(-s * 0.26, -s * 0.2, s * 0.52, s * 0.4), s * 0.05, s * 0.05)
        p.fillPath(card, QColor(255, 255, 255, 235 if i == 2 else 150))
        p.restore()
    # Play triangle
    tri = QPainterPath()
    tri.moveTo(QPointF(s * 0.44, s * 0.38))
    tri.lineTo(QPointF(s * 0.64, s * 0.50))
    tri.lineTo(QPointF(s * 0.44, s * 0.62))
    tri.closeSubpath()
    p.setPen(QPen(QColor("#1e1b4b"), max(1.0, s * 0.02), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.fillPath(tri, QColor("#1e1b4b"))
    p.drawPath(tri)
    p.end()
    return img


def main() -> None:
    QGuiApplication(sys.argv)
    os.makedirs(OUT, exist_ok=True)
    draw(256).save(os.path.join(OUT, "icon.png"))
    draw(256).save(os.path.join(OUT, "icon.ico"), "ICO")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
