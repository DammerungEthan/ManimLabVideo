"""Línea de tiempo con movimiento y redimensionado de clips."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Timeline(QWidget):
    EDGE = 7

    def __init__(self, state, on_seek, on_change=None):
        super().__init__()
        self.state, self.on_seek = state, on_seek
        self.on_change = on_change or (lambda: None)
        self.position = 38
        self._drag_index = None
        self._drag_mode = None
        self._offset = 0
        self._fixed_end = 0
        self.setMinimumHeight(170)
        self.setMouseTracking(True)

    def _geometry(self):
        return 130, 34, max(1, self.width()-150), max(1, self.state["duration"])

    def _clip_rect(self, i, obj):
        left, top, width, duration = self._geometry()
        return (left + width*obj["start"]/duration, top+8+i*36,
                max(4, width*obj["duration"]/duration), 24)

    def paintEvent(self, _event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#151922"))
        left,top,width,duration=self._geometry(); p.setFont(QFont("Sans Serif",9))
        for sec in range(duration+1):
            x=left+width*sec/duration; p.setPen(QColor("#343d4b")); p.drawLine(int(x),top,int(x),self.height()-8)
            p.setPen(QColor("#8490a2")); p.drawText(int(x-6),22,str(sec))
        for i,obj in enumerate(self.state["objects"]):
            x,y,w,h=self._clip_rect(i,obj); p.setPen(QColor("#c7d0dd")); p.drawText(12,int(y+18),obj["name"][:14])
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(obj["color"])); p.drawRoundedRect(int(x),int(y),int(w),h,5,5)
            p.setPen(QPen(QColor("#ffffff"),2)); p.drawLine(int(x+4),int(y+5),int(x+4),int(y+19)); p.drawLine(int(x+w-4),int(y+5),int(x+w-4),int(y+19))
        x=left+width*self.position/100; p.setPen(QPen(QColor("#ffbd69"),2)); p.drawLine(int(x),28,int(x),self.height()-5)

    def _hit(self,x,y):
        for i,obj in enumerate(self.state["objects"]):
            bx,by,bw,bh=self._clip_rect(i,obj)
            if by <= y <= by+bh and bx <= x <= bx+bw:
                mode="left" if x-bx <= self.EDGE else "right" if bx+bw-x <= self.EDGE else "move"
                return i,mode,(x-bx if mode=="move" else bx+bw-x if mode=="right" else x-bx)
        return None,None,0

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        i,mode,offset=self._hit(event.position().x(),event.position().y())
        if i is None:self._seek_at(event.position().x()); return
        self._drag_index,self._drag_mode,self._offset=i,mode,offset
        obj=self.state["objects"][i]; self._fixed_end=obj["start"]+obj["duration"]

    def mouseMoveEvent(self,event):
        x,y=event.position().x(),event.position().y()
        if self._drag_index is None:
            i,mode,_=self._hit(x,y); self.setCursor(Qt.CursorShape.SizeHorCursor if i is not None and mode in ("left","right") else Qt.CursorShape.OpenHandCursor if i is not None else Qt.CursorShape.ArrowCursor)
            if event.buttons() & Qt.MouseButton.LeftButton:self._seek_at(x)
            return
        left,_,width,duration=self._geometry(); obj=self.state["objects"][self._drag_index]
        if self._drag_mode=="move":
            obj["start"]=max(0,min(duration-obj["duration"],round((x-self._offset-left)*duration/width)))
        elif self._drag_mode=="right":
            end=round((x+self._offset-left)*duration/width); obj["duration"]=max(1,min(duration-obj["start"],end-obj["start"]))
        else:
            start=max(0,min(self._fixed_end-1,round((x-self._offset-left)*duration/width)))
            obj["start"],obj["duration"]=start,self._fixed_end-start
        self.update(); self.on_change()

    def mouseReleaseEvent(self,event):
        if self._drag_index is not None:
            self._drag_index=None; self._drag_mode=None; self.on_change()

    def leaveEvent(self,event): self.unsetCursor()
    def _seek_at(self,x):
        left,_,width,_=self._geometry(); self.position=max(0,min(100,round((x-left)/width*100))); self.update(); self.on_seek(self.position)
