"""Prototipo funcional de editor de escenas con persistencia JSON."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QSlider, QSpinBox, QSplitter,
    QVBoxLayout, QWidget, QLineEdit, QFormLayout, QCheckBox, QComboBox, QScrollBar,
    QProgressDialog,
)

from manim_editor.models.project import new_project
from manim_editor.services.project_io import load_project, save_project
from manim_editor.ui.preview import Preview
from manim_editor.ui.timeline import Timeline

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.state=new_project(); self.path=None; self.playing=False
        self.setWindowTitle('Manim Editor'); self.resize(1360,850)
        self._undo_stack=[]; self._redo_stack=[]; self._last_snapshot=json.dumps(self.state,sort_keys=True)
        root=QWidget(); root.setObjectName('root'); outer=QVBoxLayout(root); outer.setContentsMargins(8,8,8,8)
        bar=QHBoxLayout(); title=QLabel('✦  MANIM EDITOR'); title.setStyleSheet('font-size:18px;font-weight:700'); bar.addWidget(title); self.project_label=QLabel(self.state['name']); bar.addWidget(self.project_label); bar.addStretch()
        bar.addWidget(QLabel('Formato')); self.format_box=QComboBox(); self.format_box.addItem('YouTube · 16:9',('youtube',1920,1080)); self.format_box.addItem('Reels / Shorts · 9:16',('vertical',1080,1920)); self.format_box.currentIndexChanged.connect(self.change_format); bar.addWidget(self.format_box)
        for text,fn in [('↶',self.undo),('↷',self.redo),('Nuevo',self.new_project),('Abrir',self.open_project)]:
            b=QPushButton(text); b.clicked.connect(fn); bar.addWidget(b)
        save_actions=QVBoxLayout(); save_actions.setSpacing(2)
        save_button=QPushButton('Guardar'); save_button.clicked.connect(self.save_project); save_actions.addWidget(save_button)
        export_button=QPushButton('Exportar MP4'); export_button.clicked.connect(self.export_video); save_actions.addWidget(export_button)
        bar.addLayout(save_actions)
        outer.addLayout(bar)
        body=QHBoxLayout(); center=QVBoxLayout(); self.preview=Preview(self.state)
        self.play_btn=QPushButton('▶'); self.play_btn.setToolTip('Reproducir'); self.play_btn.setFixedWidth(32); self.play_btn.clicked.connect(self.toggle_play)
        self.slider=QSlider(Qt.Orientation.Horizontal); self.slider.setRange(0,100); self.slider.setValue(38); self.slider.valueChanged.connect(self.seek)
        self.timecode=QLabel('00:00:03:24 / 00:00:10:00'); self.timecode.setMinimumWidth(190)
        self.trim_button=QPushButton('✂ Trim'); self.trim_button.setToolTip('Dividir el clip seleccionado en el cabezal'); self.trim_button.clicked.connect(self.trim_clip)
        timeline_row=QHBoxLayout(); self.timeline=Timeline(self.state, self.seek, self.update_views); timeline_row.addWidget(self.timeline,1)
        self.track_scroll=QScrollBar(Qt.Orientation.Vertical); self.track_scroll.valueChanged.connect(self.timeline.set_row_offset); self.track_scroll.setSingleStep(1); timeline_row.addWidget(self.track_scroll)
        self.timeline_area=QWidget(); self.timeline_area.setLayout(timeline_row)
        self.vertical_split=QSplitter(Qt.Orientation.Vertical); self.vertical_split.setChildrenCollapsible(False); self.vertical_split.addWidget(self.preview); self.vertical_split.addWidget(self.timeline_area); self.vertical_split.setStretchFactor(0,1); self.vertical_split.setSizes([560,190]); center.addWidget(self.vertical_split,1)
        zoom_row=QHBoxLayout(); add_track=QPushButton('+ Pista'); add_track.clicked.connect(self.add_track); zoom_row.addWidget(add_track); remove_track=QPushButton('− Pista'); remove_track.clicked.connect(self.remove_track); zoom_row.addWidget(remove_track); zoom_row.addWidget(QLabel('Zoom'))
        for label,factor in [('−',1.25),('+',0.8)]:
            button=QPushButton(label); button.clicked.connect(lambda _=False,f=factor:self.timeline.zoom(f)); zoom_row.addWidget(button)
        zoom_row.addStretch(); center.addLayout(zoom_row)
        transport=QHBoxLayout(); transport.addWidget(self.play_btn); transport.addWidget(self.slider,1); transport.addWidget(self.timecode); transport.addWidget(self.trim_button); center.addLayout(transport)
        self.timeline_scroll=QScrollBar(Qt.Orientation.Horizontal); self.timeline_scroll.valueChanged.connect(self.timeline.set_scroll_offset); center.addWidget(self.timeline_scroll)
        self._update_timeline_scroll(); body.addLayout(center,1)
        side=QVBoxLayout(); side.addWidget(QLabel('AÑADIR ELEMENTO'))
        self.element_list=QListWidget(); self.element_list.addItems(['Gráficas: seno, coseno, tangente, x², exponencial, logaritmo','Texto y ecuación LaTeX','Punto','Vector','Recta','Círculo','Elipse','Polígono','Flecha','Ejes cartesianos','Plano cartesiano','Llaves y etiquetas','Imagen','Tabla','Grupo'])
        side.addWidget(self.element_list); add_btn=QPushButton('+ Añadir elemento'); add_btn.clicked.connect(self.add_selected_element); side.addWidget(add_btn)
        side.addWidget(QLabel('OBJETOS')); self.objects=QListWidget(); self.objects.currentRowChanged.connect(self.select_object); side.addWidget(self.objects)
        object_actions=QHBoxLayout(); delete_btn=QPushButton('Eliminar objeto'); delete_btn.clicked.connect(self.delete_object); object_actions.addWidget(delete_btn); side.addLayout(object_actions)
        form=QFormLayout(); self.name=QLineEdit(); self.expr=QLineEdit(); self.start=QSpinBox(); self.start.setRange(0,999); self.length=QSpinBox(); self.length.setRange(1,999); self.color_btn=QPushButton('Elegir color'); self.color_btn.clicked.connect(self.choose_color)
        self.visible=QCheckBox('Visible en la escena'); self.visible.stateChanged.connect(self.visibility_changed)
        for label,w in [('Nombre',self.name),('Expresión / texto',self.expr),('Inicio (s)',self.start),('Duración (s)',self.length),('Color',self.color_btn),('',self.visible)]: form.addRow(label,w)
        side.addLayout(form); self.apply_btn=QPushButton('Aplicar cambios'); self.apply_btn.clicked.connect(self.apply_properties); side.addWidget(self.apply_btn); side.addStretch(); body.addLayout(side)
        outer.addLayout(body,1); self.setCentralWidget(root)
        self.setStyleSheet("QWidget#root{background:#111317;color:#e7e7e7;font-family:'Segoe UI',sans-serif} QFrame,QListWidget,QLineEdit,QSpinBox,QComboBox{border-radius:7px} QPushButton,QLineEdit,QSpinBox,QListWidget,QComboBox{background:#202226;color:#eee;border:1px solid #363a40;border-radius:7px;padding:5px} QPushButton:hover{background:#30343b} QSplitter::handle:vertical{background:#34363a;height:5px;border-radius:3px} QSplitter::handle:vertical:hover{background:#777} QScrollBar:vertical{background:transparent;width:8px;margin:0} QScrollBar::handle:vertical{background:#52565c;min-height:24px;border-radius:4px} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0} QScrollBar:horizontal{background:#1b1d21;height:8px} QScrollBar::handle:horizontal{background:#52565c;min-width:24px;border-radius:4px} QSlider::groove:horizontal{height:3px;background:#464646;border-radius:2px} QSlider::handle:horizontal{background:#f5bd32;width:11px;margin:-4px 0;border-radius:6px}")
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
    def add_selected_element(self):
        row=self.element_list.currentRow()
        if row<0: return
        definitions=[('Gráfica seno','graph','sin(x)','#65d6ff'),('Gráfica coseno','graph','cos(x)','#65d6ff'),('Gráfica tangente','graph','tan(x)','#65d6ff'),('Parábola','graph','x^2','#65d6ff'),('Exponencial','graph','exp(x)','#65d6ff'),('Logaritmo','graph','log(x)','#65d6ff'),('Texto','text','Nuevo texto','#f1f4fa'),('Ejes','axes','','#8290a5'),('Punto','point','A','#ffbd69'),('Vector','vector','v','#ffbd69'),('Recta','line','y=x','#65d6ff'),('Círculo','circle','','#65d6ff'),('Elipse','ellipse','','#65d6ff'),('Polígono','polygon','','#65d6ff'),('Flecha','arrow','','#ffbd69'),('Plano cartesiano','axes','','#8290a5'),('Llaves y etiquetas','text','Etiqueta','#f1f4fa'),('Imagen','image','','#65d6ff'),('Tabla','table','','#65d6ff'),('Grupo','group','','#65d6ff')]
        name,kind,expression,color=definitions[row]; track=self.timeline.selected_track or self.state['tracks'][0]
        self.state['objects'].append({'name':name,'kind':kind,'expression':expression,'color':color,'start':round(self.timeline.position),'duration':max(1,self.state['duration']-round(self.timeline.position)),'visible':True,'track':track})
        self.refresh_objects(len(self.state['objects'])-1)
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
        snapshot=json.dumps(self.state,sort_keys=True)
        if snapshot != self._last_snapshot:
            self._undo_stack.append(self._last_snapshot); self._undo_stack=self._undo_stack[-100:]; self._redo_stack.clear(); self._last_snapshot=snapshot
        self.state['duration']=max([self.state['duration']]+[o['start']+o['duration'] for o in self.state['objects']])
        self.preview.update(); self.timeline.update(); self._update_timeline_scroll()
    def _restore_history(self, source, destination):
        if not source:return
        destination.append(json.dumps(self.state)); self.state=json.loads(source.pop()); self._last_snapshot=json.dumps(self.state,sort_keys=True)
        self.preview.state=self.state; self.timeline.state=self.state; self.refresh_objects()
    def undo(self): self._restore_history(self._undo_stack,self._redo_stack)
    def redo(self): self._restore_history(self._redo_stack,self._undo_stack)
    def _update_timeline_scroll(self):
        self.timeline_scroll.setRange(0,1000000); self.timeline_scroll.setPageStep(self.timeline.visible_seconds)
        self.timeline.tracks=self.state.setdefault('tracks',['Pista 1'])
        maximum=max(0,len(self.timeline.tracks)*36-self.timeline.height()+42)
        self.track_scroll.setRange(0,maximum); self.track_scroll.setPageStep(max(36,self.timeline.height())); self.track_scroll.setSingleStep(18)
        self.timeline.set_row_offset(min(self.track_scroll.value(),maximum))
    def add_track(self):
        self.timeline.add_track()
        self._update_timeline_scroll()
    def remove_track(self):
        if not self.timeline.remove_selected_track():
            QMessageBox.information(self,'Eliminar pista','Selecciona una pista. Debe quedar al menos una pista en el proyecto.')
        self._update_timeline_scroll()
    def resize_timeline(self, value):
        total=max(1,self.vertical_split.height()); bottom=round(total*value/100)
        self.vertical_split.setSizes([total-bottom,bottom])
    def trim_clip(self):
        if not self.timeline.trim_at_playhead():
            QMessageBox.information(self,'Trim','Selecciona un bloque y coloca el cabezal dentro del clip para dividirlo.')
        else:
            self.refresh_objects(min(self.timeline._selected_index+1,len(self.state['objects'])-1))
    def seek(self,v):
        seconds=v if isinstance(v,float) else self.state['duration']*v/100
        seconds=max(0,min(self.state['duration'],seconds)); self.slider.blockSignals(True); self.slider.setValue(round(seconds/max(1,self.state['duration'])*100)); self.slider.blockSignals(False)
        self.preview.progress=seconds/max(1,self.state['duration']); self.timeline.position=seconds; self.update_views()
        frame=round(seconds*30); total=round(self.state['duration']*30)
        def tc(n):
            s,f=divmod(n,30); h,s=divmod(s,3600); m,s=divmod(s,60); return f'{h:02d}:{m:02d}:{s:02d}:{f:02d}'
        self.timecode.setText(f'{tc(frame)} / {tc(total)}')
    def toggle_play(self):
        self.playing=not self.playing; self.play_btn.setText('❚❚' if self.playing else '▶'); self.play_btn.setToolTip('Pausar' if self.playing else 'Reproducir'); self.timer.start() if self.playing else self.timer.stop()
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

    def export_video(self):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            QMessageBox.warning(self,'Exportar MP4','No se encontró ffmpeg. Instálalo y vuelve a intentarlo.')
            return

        output_path,_=QFileDialog.getSaveFileName(self,'Exportar video MP4','video.mp4','Video MP4 (*.mp4)')
        if not output_path:return
        if not output_path.lower().endswith('.mp4'):
            output_path += '.mp4'

        width=max(1,int(self.state.get('width',1920)))
        height=max(1,int(self.state.get('height',1080)))
        duration=max(0.1,float(self.state.get('duration',10)))
        fps=30
        frame_count=max(1,int(round(duration*fps)))
        temp_path=None
        process=None
        canceled=False
        error_message=None
        was_playing=self.timer.isActive()
        self.timer.stop()
        progress=QProgressDialog('Renderizando fotogramas…','Cancelar',0,frame_count,self)
        progress.setWindowTitle('Exportar video MP4')
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        try:
            output_directory=os.path.dirname(os.path.abspath(output_path))
            with tempfile.NamedTemporaryFile(prefix='.manim-editor-',suffix='.mp4',dir=output_directory,delete=False) as temporary:
                temp_path=temporary.name

            command=[
                ffmpeg,'-hide_banner','-loglevel','error','-y',
                '-f','rawvideo','-pixel_format','rgba','-video_size',f'{width}x{height}',
                '-framerate',str(fps),'-i','pipe:0','-an','-c:v','libx264',
                '-preset','ultrafast','-crf','18','-pix_fmt','yuv420p',
                '-movflags','+faststart',temp_path,
            ]
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)

            render_preview=Preview(self.state)
            render_preview.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True)
            render_preview.resize(width+36,height+48)
            render_preview.selected_index=None
            render_preview.size_button.hide()
            render_preview.text_button.hide()
            render_preview.show()
            QApplication.processEvents()

            for frame_number in range(frame_count):
                if progress.wasCanceled():
                    canceled=True
                    break

                render_preview.progress=frame_number/max(1,frame_count-1)
                image=QImage(width+36,height+48,QImage.Format.Format_RGBA8888)
                image.fill(QColor('#000000'))
                painter=QPainter(image)
                try:
                    render_preview.render(painter,QPoint(0,0))
                finally:
                    painter.end()
                frame=image.copy(18,0,width,height)
                process.stdin.write(frame.bits().tobytes())
                progress.setValue(frame_number+1)
                QApplication.processEvents()

            if canceled:
                process.stdin.close()
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            else:
                process.stdin.close()
                error_output=process.stderr.read().decode('utf-8',errors='replace').strip()
                return_code=process.wait()
                if return_code:
                    raise RuntimeError(error_output or f'ffmpeg terminó con código {return_code}.')
                os.replace(temp_path,output_path)
                temp_path=None
        except (OSError,RuntimeError,ValueError) as error:
            error_message=str(error)
            if process and process.poll() is None:
                process.kill(); process.wait()
        finally:
            progress.close()
            if was_playing:
                self.timer.start()
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

        if error_message:
            QMessageBox.critical(self,'No se pudo exportar el video',error_message)
        elif canceled:
            QMessageBox.information(self,'Exportación cancelada','Se canceló la exportación.')
        else:
            QMessageBox.information(self,'Video exportado',f'El video se guardó en:\n{output_path}')

def main():
    app=QApplication(sys.argv); app.setApplicationName('Manim Editor'); w=MainWindow(); w.show(); return app.exec()
if __name__=='__main__': raise SystemExit(main())
