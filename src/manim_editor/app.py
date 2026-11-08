"""Prototipo funcional de editor de escenas con persistencia JSON."""
import json
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QSlider, QSpinBox,
    QVBoxLayout, QWidget, QLineEdit, QFormLayout, QCheckBox, QComboBox, QScrollBar,
)

from manim_editor.models.project import new_project
from manim_editor.services.project_io import load_project, save_project
from manim_editor.ui.preview import Preview
from manim_editor.ui.timeline import Timeline

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.state=new_project(); self.path=None; self.playing=False
        self.setWindowTitle('Manim Editor'); self.resize(1360,850)
        root=QWidget(); root.setObjectName('root'); outer=QVBoxLayout(root); outer.setContentsMargins(8,8,8,8)
        bar=QHBoxLayout(); title=QLabel('✦  MANIM EDITOR'); title.setStyleSheet('font-size:18px;font-weight:700'); bar.addWidget(title); self.project_label=QLabel(self.state['name']); bar.addWidget(self.project_label); bar.addStretch()
        bar.addWidget(QLabel('Formato')); self.format_box=QComboBox(); self.format_box.addItem('YouTube · 16:9',('youtube',1920,1080)); self.format_box.addItem('Reels / Shorts · 9:16',('vertical',1080,1920)); self.format_box.currentIndexChanged.connect(self.change_format); bar.addWidget(self.format_box)
        for text,fn in [('Nuevo',self.new_project),('Abrir',self.open_project),('Guardar',self.save_project)]:
            b=QPushButton(text); b.clicked.connect(fn); bar.addWidget(b)
        outer.addLayout(bar)
        body=QHBoxLayout(); center=QVBoxLayout(); self.preview=Preview(self.state); center.addWidget(self.preview,1)
        controls=QHBoxLayout(); self.play_btn=QPushButton('▶ Reproducir'); self.play_btn.clicked.connect(self.toggle_play); controls.addWidget(self.play_btn)
        self.slider=QSlider(Qt.Orientation.Horizontal); self.slider.setRange(0,100); self.slider.setValue(38); self.slider.valueChanged.connect(self.seek); controls.addWidget(self.slider,1); center.addLayout(controls)
        self.timecode=QLabel('00:00:03:24 / 00:00:10:00'); self.timecode.setMinimumWidth(190); controls.addWidget(self.timecode)
        timeline_row=QHBoxLayout(); self.timeline=Timeline(self.state, self.seek, self.update_views); timeline_row.addWidget(self.timeline,1)
        self.track_scroll=QScrollBar(Qt.Orientation.Vertical); self.track_scroll.valueChanged.connect(self.timeline.set_row_offset); self.track_scroll.setSingleStep(1); timeline_row.addWidget(self.track_scroll)
        center.addLayout(timeline_row)
        zoom_row=QHBoxLayout(); add_track=QPushButton('+ Pista'); add_track.clicked.connect(self.add_track); zoom_row.addWidget(add_track); zoom_row.addWidget(QLabel('Zoom timeline'))
        for label,factor in [('−',1.25),('+',0.8)]:
            button=QPushButton(label); button.clicked.connect(lambda _=False,f=factor:self.timeline.zoom(f)); zoom_row.addWidget(button)
        zoom_row.addStretch(); center.addLayout(zoom_row)
        self.timeline_scroll=QScrollBar(Qt.Orientation.Horizontal); self.timeline_scroll.valueChanged.connect(self.timeline.set_scroll_offset); center.addWidget(self.timeline_scroll)
        self._update_timeline_scroll(); body.addLayout(center,1)
        side=QVBoxLayout(); side.addWidget(QLabel('OBJETOS')); self.objects=QListWidget(); self.objects.currentRowChanged.connect(self.select_object); side.addWidget(self.objects)
        object_actions=QHBoxLayout(); add_btn=QPushButton('+ Gráfica'); add_btn.clicked.connect(self.add_graph); object_actions.addWidget(add_btn); delete_btn=QPushButton('Eliminar'); delete_btn.clicked.connect(self.delete_object); object_actions.addWidget(delete_btn); side.addLayout(object_actions)
        form=QFormLayout(); self.name=QLineEdit(); self.expr=QLineEdit(); self.start=QSpinBox(); self.start.setRange(0,999); self.length=QSpinBox(); self.length.setRange(1,999); self.color_btn=QPushButton('Elegir color'); self.color_btn.clicked.connect(self.choose_color)
        self.visible=QCheckBox('Visible en la escena'); self.visible.stateChanged.connect(self.visibility_changed)
        for label,w in [('Nombre',self.name),('Expresión / texto',self.expr),('Inicio (s)',self.start),('Duración (s)',self.length),('Color',self.color_btn),('',self.visible)]: form.addRow(label,w)
        side.addLayout(form); self.apply_btn=QPushButton('Aplicar cambios'); self.apply_btn.clicked.connect(self.apply_properties); side.addWidget(self.apply_btn); side.addStretch(); body.addLayout(side)
        outer.addLayout(body,1); self.setCentralWidget(root)
        self.setStyleSheet("QWidget#root{background:#0e1117;color:#e7ebf2;font-family:'Segoe UI',sans-serif} QPushButton,QLineEdit,QSpinBox,QListWidget{background:#202735;color:#e7ebf2;border:1px solid #303949;border-radius:5px;padding:6px} QSlider::groove:horizontal{height:4px;background:#354052} QSlider::handle:horizontal{background:#65d6ff;width:12px;margin:-5px 0;border-radius:6px}")
        self.timer=QTimer(self); self.timer.setInterval(40); self.timer.timeout.connect(self.tick); self.set_format_control(); self.refresh_objects()

    def set_format_control(self):
        idx=1 if self.state.get('format')=='vertical' else 0
        self.format_box.blockSignals(True); self.format_box.setCurrentIndex(idx); self.format_box.blockSignals(False)
    def change_format(self,index):
        fmt,width,height=self.format_box.currentData(); self.state.update(format=fmt,width=width,height=height); self.update_views()

    def refresh_objects(self,select=0):
        self.objects.blockSignals(True); self.objects.clear(); self.objects.addItems([o['name'] for o in self.state['objects']]); self.objects.blockSignals(False)
        if self.state['objects']: self.objects.setCurrentRow(min(select,len(self.state['objects'])-1)); self.select_object(self.objects.currentRow())
        self.project_label.setText(self.path.name if self.path else self.state['name']); self.update_views()
    def select_object(self,row):
        if row<0 or row>=len(self.state['objects']): return
        o=self.state['objects'][row]; self.name.setText(o['name']); self.expr.setText(o['expression']); self.start.setValue(o['start']); self.length.setValue(o['duration']); self.color_btn.setText(o['color']); self.color_btn.setStyleSheet('background:'+o['color']); self.visible.blockSignals(True); self.visible.setChecked(o.get('visible',True)); self.visible.blockSignals(False)
    def add_graph(self):
        self.state['objects'].append({'name':'Nueva gráfica','kind':'graph','expression':'cos(x)','color':'#ffbd69','start':0,'duration':self.state['duration'],'visible':True}); self.refresh_objects(len(self.state['objects'])-1)
    def delete_object(self):
        row=self.objects.currentRow()
        if row<0:return
        self.state['objects'].pop(row); self.refresh_objects(max(0,row-1))
    def visibility_changed(self,_):
        row=self.objects.currentRow()
        if row>=0:self.state['objects'][row]['visible']=self.visible.isChecked(); self.update_views()
    def apply_properties(self):
        row=self.objects.currentRow()
        if row<0:return
        o=self.state['objects'][row]; o.update(name=self.name.text() or 'Objeto',expression=self.expr.text(),start=self.start.value(),duration=self.length.value())
        self.refresh_objects(row)
    def choose_color(self):
        row=self.objects.currentRow()
        if row>=0:
            c=QColorDialog.getColor(QColor(self.state['objects'][row]['color']),self)
            if c.isValid(): self.state['objects'][row]['color']=c.name(); self.select_object(row); self.update_views()
    def update_views(self):
        self.state['duration']=max([self.state['duration']]+[o['start']+o['duration'] for o in self.state['objects']])
        self.preview.update(); self.timeline.update(); self._update_timeline_scroll()
    def _update_timeline_scroll(self):
        self.timeline_scroll.setRange(0,1000000); self.timeline_scroll.setPageStep(self.timeline.visible_seconds)
        self.timeline.tracks=self.state.setdefault('tracks',['Pista 1'])
        maximum=max(0,len(self.timeline.tracks)-self.timeline.visible_rows)
        self.track_scroll.setRange(0,maximum); self.track_scroll.setPageStep(self.timeline.visible_rows); self.track_scroll.setSingleStep(1)
        self.timeline.set_row_offset(min(self.track_scroll.value(),maximum))
    def add_track(self):
        self.timeline.add_track()
        self._update_timeline_scroll()
    def seek(self,v):
        seconds=v if isinstance(v,float) else self.state['duration']*v/100
        seconds=max(0,min(self.state['duration'],seconds)); self.slider.blockSignals(True); self.slider.setValue(round(seconds/max(1,self.state['duration'])*100)); self.slider.blockSignals(False)
        self.preview.progress=seconds/max(1,self.state['duration']); self.timeline.position=seconds; self.update_views()
        frame=round(seconds*30); total=round(self.state['duration']*30)
        def tc(n):
            s,f=divmod(n,30); h,s=divmod(s,3600); m,s=divmod(s,60); return f'{h:02d}:{m:02d}:{s:02d}:{f:02d}'
        self.timecode.setText(f'{tc(frame)} / {tc(total)}')
    def toggle_play(self):
        self.playing=not self.playing; self.play_btn.setText('❚❚ Pausar' if self.playing else '▶ Reproducir'); self.timer.start() if self.playing else self.timer.stop()
    def tick(self): self.seek((self.slider.value()+1)%101)
    def new_project(self): self.state=new_project(); self.path=None; self.preview.state=self.state; self.timeline.state=self.state; self.timeline.set_scroll_offset(0); self._update_timeline_scroll(); self.refresh_objects()
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Abrir proyecto','','Manim Editor (*.manimproj);;JSON (*.json)')
        if not path:return
        try:
            data=load_project(path)
            self.state=data; self.path=Path(path); self.preview.state=self.state; self.timeline.state=self.state; self._update_timeline_scroll(); self.set_format_control(); self.refresh_objects()
        except (OSError,ValueError,AssertionError,KeyError) as e: QMessageBox.critical(self,'No se pudo abrir',str(e))
    def save_project(self):
        if not self.path:
            path,_=QFileDialog.getSaveFileName(self,'Guardar proyecto','proyecto.maniproj','Manim Editor (*.manimproj)')
            if not path:return
            self.path=Path(path)
        try:
            self.state['name']=self.path.stem; save_project(self.path,self.state); self.project_label.setText(self.path.name)
        except OSError as e: QMessageBox.critical(self,'No se pudo guardar',str(e))

def main():
    app=QApplication(sys.argv); app.setApplicationName('Manim Editor'); w=MainWindow(); w.show(); return app.exec()
if __name__=='__main__': raise SystemExit(main())
