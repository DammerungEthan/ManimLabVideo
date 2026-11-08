"""Línea de tiempo con movimiento y redimensionado de clips."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Timeline(QWidget):
    EDGE = 7

    def __init__(self, state, on_seek, on_change=None, on_scroll=None):
        super().__init__()
        self.state, self.on_seek = state, on_seek
        self.on_change = on_change or (lambda: None)
        self.scroll_offset = 0
        self.visible_seconds = 20
        self.visible_rows = 2
        self.row_offset = 0
        self.tracks = []
        self.on_scroll = on_scroll or (lambda value: None)
        self.position = 38
        self._drag_index = None
        self._drag_mode = None
        self._offset = 0
        self._fixed_end = 0
        self._target_track = 0
        self.setMinimumHeight(125)
        self.setMaximumWidth(1000)
        self.setMaximumHeight(155)
        self.setMouseTracking(True)

    def _geometry(self):
        return 130, 34, max(1, self.width()-150), max(1, self.visible_seconds)

    def _clip_rect(self, i, obj):
        left, top, width, duration = self._geometry()
        row = self.tracks.index(obj.get("track", "Pista 1")) if obj.get("track", "Pista 1") in self.tracks else 0
        return (left + width*(obj["start"]-self.scroll_offset)/duration, top+8+(row-self.row_offset)*36,
                max(4, width*obj["duration"]/duration), 24)

    def paintEvent(self, _event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#151922"))
        self.tracks=self.state.setdefault("tracks", ["Pista 1"])
        # Repair malformed/legacy projects before drawing: a clip always belongs
        # to exactly one existing track, and track names are unique.
        self.tracks[:] = list(dict.fromkeys(self.tracks)) or ["Pista 1"]
        for obj in self.state["objects"]:
            if obj.get("track") not in self.tracks:
                obj["track"] = self.tracks[0]
        left,top,width,scale=self._geometry(); p.setFont(QFont("Sans Serif",9))
        end=self.scroll_offset+scale
        tick_step = max(1, round(scale / max(2, width / 70)))
        first_tick = ((self.scroll_offset + tick_step - 1) // tick_step) * tick_step
        for sec in range(first_tick,end+1,tick_step):
            x=left+width*(sec-self.scroll_offset)/scale; p.setPen(QColor("#343d4b")); p.drawLine(int(x),top,int(x),self.height()-8)
            p.setPen(QColor("#8490a2")); p.drawText(int(x-6),22,str(sec))
        for track_index in range(self.row_offset,min(len(self.tracks),self.row_offset+self.visible_rows)):
            track=self.tracks[track_index]; y=top+8+(track_index-self.row_offset)*36
            p.setPen(QColor("#c7d0dd")); p.drawText(12,int(y+18),track[:14])
            for obj in self.state["objects"]:
                if obj.get("track", "Pista 1") != track: continue
                x,y,w,h=self._clip_rect(track_index-self.row_offset,obj)
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(obj["color"])); p.drawRoundedRect(int(x),int(y),int(w),h,5,5)
                p.setPen(QColor("#ffffff")); p.drawText(int(x+6),int(y+17),obj["name"][:12])
                p.setPen(QPen(QColor("#ffffff"),2)); p.drawLine(int(x+4),int(y+5),int(x+4),int(y+19)); p.drawLine(int(x+w-4),int(y+5),int(x+w-4),int(y+19))
        current=self.position
        if self.scroll_offset <= current <= self.scroll_offset+scale:
            x=left+width*(current-self.scroll_offset)/scale; p.setPen(QPen(QColor("#ffbd69"),2)); p.drawLine(int(x),28,int(x),self.height()-5)

    def _hit(self,x,y):
        for i,obj in enumerate(self.state["objects"]):
            track=obj.get("track", "Pista 1")
            if track not in self.tracks: continue
            row=self.tracks.index(track)
            if not self.row_offset <= row < self.row_offset+self.visible_rows: continue
            bx,by,bw,bh=self._clip_rect(row,obj)
            if by <= y <= by+bh and bx <= x <= bx+bw:
                mode="left" if x-bx <= self.EDGE else "right" if bx+bw-x <= self.EDGE else "move"
                return i,mode,(x-bx if mode=="move" else bx+bw-x if mode=="right" else x-bx)
        return None,None,0

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        left,_,width,scale=self._geometry()
        playhead_x=left+width*(self.position-self.scroll_offset)/scale
        if abs(event.position().x()-playhead_x) <= 8:
            self._drag_mode="playhead"; self._seek_at(event.position().x()); return
        i,mode,offset=self._hit(event.position().x(),event.position().y())
        if i is None:self._seek_at(event.position().x()); return
        self._drag_index,self._drag_mode,self._offset=i,mode,offset
        obj=self.state["objects"][i]; self._fixed_end=obj["start"]+obj["duration"]

    def mouseMoveEvent(self,event):
        x,y=event.position().x(),event.position().y()
        if self._drag_mode=="playhead":
            self._seek_at(x); return
        if self._drag_index is None:
            i,mode,_=self._hit(x,y); self.setCursor(Qt.CursorShape.SizeHorCursor if i is not None and mode in ("left","right") else Qt.CursorShape.OpenHandCursor if i is not None else Qt.CursorShape.ArrowCursor)
            if event.buttons() & Qt.MouseButton.LeftButton:self._seek_at(x)
            return
        left,_,width,scale=self._geometry(); obj=self.state["objects"][self._drag_index]
        row_height=36; first_y=42
        target=max(0,min(len(self.tracks)-1,int((y-first_y)/row_height)+self.row_offset))
        if self._drag_mode=="move" and self.tracks:
            obj["track"]=self.tracks[target]
        x += self.scroll_offset*width/scale
        if self._drag_mode=="move":
            obj["start"]=max(0,round((x-self._offset-left)*scale/width)+self.scroll_offset)
        elif self._drag_mode=="right":
            end=round((x+self._offset-left)*scale/width)+self.scroll_offset; obj["duration"]=max(1,end-obj["start"])
        else:
            start=max(0,min(self._fixed_end-1,round((x-self._offset-left)*scale/width)+self.scroll_offset))
            obj["start"],obj["duration"]=start,self._fixed_end-start
        self.state["duration"]=max(self.state["duration"],obj["start"]+obj["duration"])
        self.update(); self.on_change()

    def mouseReleaseEvent(self,event):
        if self._drag_mode=="playhead":
            self._drag_mode=None; return
        if self._drag_index is not None:
            self._drag_index=None; self._drag_mode=None; self.on_change()

    def leaveEvent(self,event): self.unsetCursor()
    def set_scroll_offset(self, value):
        self.scroll_offset=max(0,value); self.update()
    def set_row_offset(self, value):
        value=max(0,min(max(0,len(self.tracks)-self.visible_rows),value))
        if value != self.row_offset:
            self.row_offset=value
            self.update()
    def add_track(self):
        number=1
        while f"Pista {number}" in self.tracks: number+=1
        self.tracks.append(f"Pista {number}")
        self.state["tracks"]=self.tracks
        self.update(); self.on_change()
    def zoom(self, factor):
        self.visible_seconds=max(2,min(300,round(self.visible_seconds*factor))); self.update()
    def _seek_at(self,x):
        left,_,width,scale=self._geometry(); seconds=self.scroll_offset+(x-left)*scale/width
        self.position=max(0,round(seconds*30)/30); self.update(); self.on_seek(self.position)
