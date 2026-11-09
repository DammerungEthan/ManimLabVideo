"""Línea de tiempo con movimiento y redimensionado de clips."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget, QInputDialog


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
        self.track_scroll_px = 0
        self.tracks = []
        self.selected_track = None
        self.on_scroll = on_scroll or (lambda value: None)
        self.position = 38
        self._drag_index = None
        self._drag_mode = None
        self._offset = 0
        self._fixed_end = 0
        self._target_track = 0
        self.setMaximumWidth(1000)
        self.setMinimumHeight(155)
        self.setMouseTracking(True)
        self._scroll_timer=QTimer(self); self._scroll_timer.setInterval(16); self._scroll_timer.timeout.connect(self._animate_scroll)
        self._scroll_target=0

    def _geometry(self):
        return 130, 34, max(1, self.width()-150), max(1, self.visible_seconds)

    def _clip_rect(self, i, obj):
        left, top, width, duration = self._geometry()
        row = self.tracks.index(obj.get("track", "Pista 1")) if obj.get("track", "Pista 1") in self.tracks else 0
        return (left + width*(obj["start"]-self.scroll_offset)/duration, top+8+row*36-self.track_scroll_px,
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
            hours, remainder = divmod(sec, 3600); minutes, seconds = divmod(remainder, 60)
            label=f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            p.setPen(QColor("#8490a2")); p.drawText(int(x-28),22,label)
        p.save(); p.setClipRect(0,top,self.width(),self.height()-top)
        for track_index in range(len(self.tracks)):
            track=self.tracks[track_index]; y=top+8+track_index*36-self.track_scroll_px
            meta=self.state.setdefault("track_meta",{}).setdefault(track,{"visible":True})
            if track == self.selected_track:
                p.fillRect(0,int(y),126,32,QColor("#26303d"))
                p.setPen(QPen(QColor("#f0b72f"),2)); p.drawLine(0,int(y),0,int(y+32))
            p.setPen(QColor("#c7d0dd")); p.drawText(12,int(y+18),track[:14])
            p.setPen(QColor("#93a0b2")); p.drawText(100,int(y+18),"◉" if meta.get("visible",True) else "○")
            for obj in self.state["objects"]:
                if obj.get("track", "Pista 1") != track: continue
                x,clip_y,w,h=self._clip_rect(track_index,obj)
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(obj["color"])); p.drawRoundedRect(int(x),int(clip_y),int(w),h,5,5)
                if not meta.get("visible",True): p.fillRect(int(x),int(clip_y),int(w),h,QColor(17,19,23,150))
                p.setPen(QColor("#ffffff")); p.drawText(int(x+6),int(clip_y+17),obj["name"][:12])
                p.setPen(QPen(QColor("#ffffff"),2)); p.drawLine(int(x+4),int(clip_y+5),int(x+4),int(clip_y+19)); p.drawLine(int(x+w-4),int(clip_y+5),int(x+w-4),int(clip_y+19))
        p.restore()
        current=self.position
        if self.scroll_offset <= current <= self.scroll_offset+scale:
            x=left+width*(current-self.scroll_offset)/scale; p.setPen(QPen(QColor("#ffbd69"),2)); p.drawLine(int(x),28,int(x),self.height()-5)

    def _hit(self,x,y):
        for i,obj in enumerate(self.state["objects"]):
            track=obj.get("track", "Pista 1")
            if track not in self.tracks: continue
            row=self.tracks.index(track)
            bx,by,bw,bh=self._clip_rect(row,obj)
            if by <= y <= by+bh and bx <= x <= bx+bw:
                mode="left" if x-bx <= self.EDGE else "right" if bx+bw-x <= self.EDGE else "move"
                return i,mode,(x-bx if mode=="move" else bx+bw-x if mode=="right" else x-bx)
        return None,None,0

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        _,top,_,_=self._geometry()
        row=round((event.position().y()-top-8+self.track_scroll_px)/36)
        row_y=top+8+row*36-self.track_scroll_px
        if 0 <= row < len(self.tracks) and row_y <= event.position().y() <= row_y+32 and event.position().x()<130:
            track=self.tracks[row]
            if event.position().x()>=96:
                meta=self.state.setdefault("track_meta",{}).setdefault(track,{"visible":True}); meta["visible"]=not meta.get("visible",True)
            else: self.selected_track=track
            self.update(); self.on_change(); return
        left,_,width,scale=self._geometry()
        playhead_x=left+width*(self.position-self.scroll_offset)/scale
        if abs(event.position().x()-playhead_x) <= 8:
            self._drag_mode="playhead"; self._seek_at(event.position().x()); return
        i,mode,offset=self._hit(event.position().x(),event.position().y())
        if i is None:self._seek_at(event.position().x()); return
        self._drag_index,self._drag_mode,self._offset=i,mode,offset
        self._selected_index=i
        obj=self.state["objects"][i]; self._fixed_end=obj["start"]+obj["duration"]

    def mouseDoubleClickEvent(self, event):
        _,top,_,_=self._geometry()
        row=round((event.position().y()-top-8+self.track_scroll_px)/36)
        row_y=top+8+row*36-self.track_scroll_px
        if not (0 <= row < len(self.tracks) and row_y <= event.position().y() <= row_y+32 and event.position().x()<96):
            return
        old=self.tracks[row]
        new,ok=QInputDialog.getText(self,"Renombrar pista","Nombre de la pista:",text=old)
        new=new.strip()
        if not ok or not new or (new in self.tracks and new != old): return
        self.tracks[row]=new
        for obj in self.state["objects"]:
            if obj.get("track","Pista 1")==old: obj["track"]=new
        meta=self.state.setdefault("track_meta",{}).pop(old,{"visible":True})
        self.state["track_meta"][new]=meta
        if self.selected_track==old:self.selected_track=new
        self.update(); self.on_change()

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
        self._scroll_target=max(0,min(max(0,len(self.tracks)*36-self.height()+50),value))
        self._scroll_timer.start()
    def wheelEvent(self,event):
        delta=event.angleDelta().y()
        self._scroll_target=max(0,min(max(0,len(self.tracks)*36-self.height()+50),self._scroll_target-delta*0.35))
        self._scroll_timer.start(); event.accept()
    def _animate_scroll(self):
        diff=self._scroll_target-self.track_scroll_px
        if abs(diff)<1:
            self.track_scroll_px=self._scroll_target; self._scroll_timer.stop()
        else: self.track_scroll_px += diff*0.28
        self.row_offset=int(self.track_scroll_px//36); self.update()
    def add_track(self):
        number=1
        while f"Pista {number}" in self.tracks: number+=1
        self.tracks.append(f"Pista {number}")
        self.state["tracks"]=self.tracks
        self.update(); self.on_change()
    def remove_selected_track(self):
        track=self.selected_track
        if track not in self.tracks or len(self.tracks)<=1:return False
        replacement=next(name for name in self.tracks if name!=track)
        for obj in self.state["objects"]:
            if obj.get("track","Pista 1")==track: obj["track"]=replacement
        self.tracks.remove(track); self.state["track_meta"].pop(track,None)
        self.state["objects"]=[obj for obj in self.state["objects"] if obj.get("track","Pista 1") != track]
        self.selected_track=replacement; self.update(); self.on_change(); return True
    def zoom(self, factor):
        self.visible_seconds=max(2,min(300,round(self.visible_seconds*factor))); self.update()
    def trim_at_playhead(self):
        index=self._selected_index if hasattr(self, "_selected_index") else None
        if index is None or not 0 <= index < len(self.state["objects"]): return False
        obj=self.state["objects"][index]; cut=round(self.position)
        start,end=obj["start"],obj["start"]+obj["duration"]
        if not start < cut < end: return False
        import copy
        right=copy.deepcopy(obj); right["name"] += " (copia)"; right["start"]=cut; right["duration"]=end-cut
        obj["duration"]=cut-start; self.state["objects"].insert(index+1,right)
        self.update(); self.on_change(); return True
    def _seek_at(self,x):
        left,_,width,scale=self._geometry(); seconds=self.scroll_offset+(x-left)*scale/width
        self.position=max(0,round(seconds*30)/30); self.update(); self.on_seek(self.position)
