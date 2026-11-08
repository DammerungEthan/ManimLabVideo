"""Línea de tiempo visual con cursor de reproducción."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Timeline(QWidget):
    def __init__(self, state, on_seek, on_change=None):
        super().__init__()
        self.state, self.on_seek = state, on_seek
        self.on_change = on_change or (lambda: None)
        self.position = 38
        self._drag_index = None
        self._drag_offset = 0
        self.setMinimumHeight(170)
        self.setMouseTracking(True)

    def paintEvent(self, _event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#151922"))
        left, top, width = 130, 34, max(1, self.width()-150)
        duration = max(1, self.state["duration"]); p.setFont(QFont("Sans Serif", 9))
        for sec in range(duration+1):
            x = left+width*sec/duration
            p.setPen(QColor("#343d4b")); p.drawLine(int(x), top, int(x), self.height()-8)
            p.setPen(QColor("#8490a2")); p.drawText(int(x-6), 22, str(sec))
        for i, obj in enumerate(self.state["objects"]):
            y=top+8+i*36; p.setPen(QColor("#c7d0dd")); p.drawText(12,y+18,obj["name"][:14])
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(obj["color"]))
            x=left+width*obj["start"]/duration; ww=max(4,width*obj["duration"]/duration)
            p.drawRoundedRect(int(x),y,int(ww),24,5,5)
        x=left+width*self.position/100; p.setPen(QPen(QColor("#ffbd69"),2))
        p.drawLine(int(x),28,int(x),self.height()-5)

    def _geometry(self):
        return 130, 34, max(1, self.width()-150), max(1, self.state["duration"])

    def _block_at(self, x, y):
        left, top, width, duration = self._geometry()
        for i, obj in enumerate(self.state["objects"]):
            block_x = left + width * obj["start"] / duration
            block_w = max(4, width * obj["duration"] / duration)
            block_y = top + 8 + i * 36
            if block_x <= x <= block_x + block_w and block_y <= y <= block_y + 24:
                return i, x - block_x
        return None, 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index, offset = self._block_at(event.position().x(), event.position().y())
            if index is not None:
                self._drag_index, self._drag_offset = index, offset
            else:
                self._move(event.position().x())

    def mouseReleaseEvent(self, event):
        if self._drag_index is not None:
            self._drag_index = None
            self.on_change()

    def leaveEvent(self, event):
        self.unsetCursor()

    def mouseMoveEvent(self, event):
        if self._drag_index is None and not (event.buttons() & Qt.MouseButton.LeftButton):
            index, _ = self._block_at(event.position().x(), event.position().y())
            self.setCursor(Qt.CursorShape.SizeHorCursor if index is not None else Qt.CursorShape.ArrowCursor)
        if self._drag_index is not None and event.buttons() & Qt.MouseButton.LeftButton:
            left, _, width, duration = self._geometry()
            obj = self.state["objects"][self._drag_index]
            pixel_x = event.position().x() - self._drag_offset
            start = round((pixel_x-left) / width * duration)
            obj["start"] = max(0, min(duration-obj["duration"], start))
            self.update()
            self.on_change()
        elif event.buttons() & Qt.MouseButton.LeftButton:
            self._move(event.position().x())
    def _move(self, x):
        self.position=max(0,min(100,round((x-130)/max(1,self.width()-150)*100)))
        self.update(); self.on_seek(self.position)
