"""Widget de vista previa para escenas matemáticas."""
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QWidget


class Preview(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.progress = 0.38
        self.setMinimumSize(420, 270)
        self._expanded = False
        self._original_parent = None
        self._original_layout = None
        self._original_index = -1
        self._original_window_flags = self.windowFlags()

        self.size_button = QPushButton("⛶", self)
        self.size_button.setToolTip("Ampliar vista previa")
        self.size_button.setAccessibleName("Ampliar vista previa")
        self.size_button.setFixedSize(36, 32)
        self.size_button.setStyleSheet(
            "QPushButton { background: #202735; color: #e7ebf2; "
            "border: 1px solid #536174; border-radius: 5px; font-size: 18px; }"
            "QPushButton:hover { background: #354052; }"
        )
        self.size_button.clicked.connect(self.toggle_size)
        self._position_size_button()

    def _position_size_button(self):
        self.size_button.move(self.width() - self.size_button.width() - 10, 10)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_size_button()

    def _find_containing_layout(self, layout):
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is self:
                return layout, index
            child_layout = item.layout()
            if child_layout is not None:
                result = self._find_containing_layout(child_layout)
                if result is not None:
                    return result
        return None

    def toggle_size(self):
        if self._expanded:
            self._restore_size()
        else:
            self._expand_size()

    def _expand_size(self):
        parent = self.parentWidget()
        result = self._find_containing_layout(parent.layout()) if parent and parent.layout() else None
        if result is None:
            return

        self._original_parent = parent
        self._original_layout, self._original_index = result
        self._original_layout.removeWidget(self)
        self._original_window_flags = self.windowFlags()
        self.setParent(parent, Qt.WindowType.Window)
        self.setWindowTitle("Vista previa · Manim Editor")
        self._expanded = True
        self.size_button.setText("❐")
        self.size_button.setToolTip("Volver al tamaño original")
        self.size_button.setAccessibleName("Volver al tamaño original")
        self.showMaximized()

    def _restore_size(self):
        parent = self._original_parent
        layout = self._original_layout
        if parent is None or layout is None:
            return

        self.setParent(parent, self._original_window_flags)
        layout.insertWidget(self._original_index, self, 1)
        self._expanded = False
        self.size_button.setText("⛶")
        self.size_button.setToolTip("Ampliar vista previa")
        self.size_button.setAccessibleName("Ampliar vista previa")
        self.show()
        self.update()

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
        p.restore(); p.setPen(QPen(QColor("#536174"), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(int(ox), int(oy), int(cw), int(ch))
