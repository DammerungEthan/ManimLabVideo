"""Widget de vista previa para escenas matemáticas."""
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Preview(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.progress = 0.38
        self.setMinimumSize(420, 270)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#10131a"))
        w, h = self.width(), self.height()
        aspect = self.state.get("width", 16) / max(1, self.state.get("height", 9))
        cw = min(w - 36, (h - 54) * aspect)
        ch = cw / aspect
        if ch > h - 54:
            ch, cw = h - 54, (h - 54) * aspect
        ox, oy = (w - cw) / 2, (h - ch) / 2
        p.fillRect(int(ox), int(oy), int(cw), int(ch), QColor("#10131a"))
        p.save()
        p.setClipRect(int(ox), int(oy), int(cw), int(ch))
        p.translate(ox, oy)
        p.scale(cw / w, ch / h)
        p.setPen(QPen(QColor("#1d2532"), 1))
        for x in range(24, w, 36): p.drawLine(x, 0, x, h)
        for y in range(18, h, 36): p.drawLine(0, y, w, y)
        cx, cy, scale = w * .52, h * .54, min(w, h) * .30
        now = self.progress * self.state["duration"]
        active = {o["kind"]: o for o in self.state["objects"]
                  if o.get("visible", True) and o["start"] <= now <= o["start"] + o["duration"]}
        if "axes" in active:
            p.setPen(QPen(QColor(active["axes"]["color"]), 1))
            p.drawLine(int(cx-scale*1.3), int(cy), int(cx+scale*1.3), int(cy))
            p.drawLine(int(cx), int(cy-scale*1.15), int(cx), int(cy+scale*1.15))
        if "graph" in active:
            graph = active["graph"]
            funcs = {"sin(x)": math.sin, "cos(x)": math.cos,
                     "tan(x)": lambda x: math.sin(x)*.5,
                     "x^2": lambda x: ((x-math.pi)**2/5)-1}
            fn = funcs.get(graph["expression"].strip().lower(), math.sin)
            points = [(cx-scale+2*scale*i/219,
                       cy-scale*.48*fn(i/219*math.tau*1.5))
                      for i in range(max(2, int(220*self.progress)))]
            p.setPen(QPen(QColor(graph["color"]), 3))
            for a, b in zip(points, points[1:]): p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
        if "text" in active:
            obj = active["text"]
            p.setPen(QColor(obj["color"])); p.setFont(QFont("Sans Serif", 16, QFont.Weight.DemiBold))
            p.drawText(24, 36, obj["expression"])
        p.setPen(QColor("#8290a5")); p.setFont(QFont("Sans Serif", 9))
        p.drawText(24, h-20, "VISTA PREVIA · PROTOTIPO")
        p.restore(); p.setPen(QPen(QColor("#536174"), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(int(ox), int(oy), int(cw), int(ch))
