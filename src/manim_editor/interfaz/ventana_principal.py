"""Editor de proyectos y escenas Manim con previsualización integrada."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton, QSlider, QDoubleSpinBox, QSplitter,
    QVBoxLayout, QWidget, QLineEdit, QFormLayout, QCheckBox, QComboBox, QScrollBar,
    QProgressDialog, QToolButton, QPlainTextEdit, QTabBar, QStackedWidget,
)

from manim_editor.modelos.proyecto import new_project
from manim_editor.servicios.archivos_proyecto import load_project, save_project
from manim_editor.interfaz.vista_previa import Preview
from manim_editor.interfaz.editor_codigo import PythonCodeEditor, PythonHighlighter
from manim_editor.interfaz.sincronizador_manim import SincronizadorManim
from manim_editor.interfaz.linea_tiempo import Timeline
from manim_editor.tipografia import MANIM_TEXT_FONT


class MainWindow(SincronizadorManim, QMainWindow):
    """Ventana principal que coordina la interfaz y el estado del proyecto."""

    def __init__(self):
        super().__init__(); self.state=new_project(); self.path=None; self.playing=False
        self._manim_render_frames=[]; self._manim_render_directory=None
        self._manim_video_path=None; self._manim_render_worker=None
        self._manim_frame_index=None; self._installing_manim_render=False
        self._render_generation=0
        self._timeline_preview_override=False
        self._pending_timeline_sync=False
        self._timeline_timing_snapshot=self._timeline_timing_signature()
        self.setWindowTitle('Manim Editor'); self.resize(1360,850)
        self._undo_stack=[]; self._redo_stack=[]; self._last_snapshot=json.dumps(self.state,sort_keys=True)
        # Barra superior: proyecto, pestañas, formato, historial y archivos.
        root=QWidget(); root.setObjectName('root'); outer=QVBoxLayout(root); outer.setContentsMargins(8,8,8,8)
        bar=QHBoxLayout()
        app_icon=QLabel(); app_icon.setFixedSize(28,28); app_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = Path(__file__).resolve().parent.parent / 'icons' / 'icon.png'
        icon_pixmap=QPixmap(str(icon_path))
        if not icon_pixmap.isNull():
            app_icon.setPixmap(icon_pixmap.scaled(28,28,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            bar.addWidget(app_icon)
        self.project_label=QLabel(self.state['name']); bar.addWidget(self.project_label); bar.addStretch()
        self.workspace_tab_bar=QTabBar(); self.workspace_tab_bar.setExpanding(False); self.workspace_tab_bar.setDrawBase(False); self.workspace_tab_bar.setMovable(False)
        self.workspace_tab_bar.addTab('▶  Video'); self.workspace_tab_bar.addTab('</>  Código Manim')
        self.workspace_tab_bar.setStyleSheet('QTabBar::tab{background:#1b1d21;color:#aeb4bd;padding:7px 14px;border:1px solid #30343a;border-bottom:0;border-top-left-radius:6px;border-top-right-radius:6px;margin-right:3px} QTabBar::tab:selected{background:#292d33;color:#f1f4fa} QTabBar::tab:hover:!selected{background:#24272c}')
        bar.addWidget(self.workspace_tab_bar)
        bar.addWidget(QLabel('Formato')); self.format_box=QComboBox(); self.format_box.addItem('YouTube · 16:9',('youtube',1920,1080)); self.format_box.addItem('Reels / Shorts · 9:16',('vertical',1080,1920)); self.format_box.currentIndexChanged.connect(self.change_format); bar.addWidget(self.format_box)
        for text,fn in [('↶',self.undo),('↷',self.redo)]:
            b=QPushButton(text); b.clicked.connect(fn); bar.addWidget(b)
        file_menu=QMenu(self)
        for text,fn in (
            ('Nuevo',self.new_project),
            ('Abrir',self.open_project),
            ('Guardar',self.save_project),
            ('Exportar MP4',self.export_video),
        ):
            action=file_menu.addAction(text)
            action.triggered.connect(fn)
        file_menu_button=QToolButton()
        file_menu_button.setText('Archivo ▾')
        file_menu_button.setMenu(file_menu)
        file_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        file_menu_button.setToolTip('Nuevo, abrir, guardar o exportar el proyecto')
        bar.addWidget(file_menu_button)
        outer.addLayout(bar)
        # Área central: previsualización, timeline y editor de código.
        body=QHBoxLayout(); center=QVBoxLayout(); self.preview=Preview(self.state)
        self.play_btn=QPushButton('▶'); self.play_btn.setToolTip('Reproducir'); self.play_btn.setFixedWidth(32); self.play_btn.clicked.connect(self.toggle_play)
        self.slider=QSlider(Qt.Orientation.Horizontal); self.slider.setRange(0,100); self.slider.setValue(38); self.slider.valueChanged.connect(self.seek)
        self.timecode=QLabel('00:00:03:24 / 00:00:10:00'); self.timecode.setMinimumWidth(190)
        self.trim_button=QPushButton('✂ Trim'); self.trim_button.setToolTip('Dividir el clip seleccionado en el cabezal'); self.trim_button.clicked.connect(self.trim_clip)
        timeline_row=QHBoxLayout(); self.timeline=Timeline(self.state, self.seek, self._timeline_state_changed, self._timeline_clip_selected); self.timeline.set_transport_controls(self.play_btn, self.slider, self.timecode); timeline_row.addWidget(self.timeline,1)
        self.track_scroll=QScrollBar(Qt.Orientation.Vertical); self.track_scroll.valueChanged.connect(self.timeline.set_row_offset); self.track_scroll.setSingleStep(1); timeline_row.addWidget(self.track_scroll)
        self.timeline_area=QWidget(); self.timeline_area.setLayout(timeline_row)
        self.vertical_split=QSplitter(Qt.Orientation.Vertical); self.vertical_split.setChildrenCollapsible(False); self.vertical_split.addWidget(self.preview); self.vertical_split.addWidget(self.timeline_area); self.vertical_split.setStretchFactor(0,1); self.vertical_split.setSizes([560,190])
        zoom_row=QHBoxLayout(); add_track=QPushButton('+ Pista'); add_track.clicked.connect(self.add_track); zoom_row.addWidget(add_track); remove_track=QPushButton('− Pista'); remove_track.clicked.connect(self.remove_track); zoom_row.addWidget(remove_track); zoom_row.addWidget(QLabel('Zoom'))
        for label,factor in [('−',1.25),('+',0.8)]:
            button=QPushButton(label); button.clicked.connect(lambda _=False,f=factor:self.timeline.zoom(f)); zoom_row.addWidget(button)
        zoom_row.addStretch(); zoom_row.addWidget(self.trim_button)
        self.timeline_scroll=QScrollBar(Qt.Orientation.Horizontal); self.timeline_scroll.valueChanged.connect(self.timeline.set_scroll_offset)

        video_page=QWidget(); video_layout=QVBoxLayout(video_page); video_layout.setContentsMargins(0,0,0,0)
        video_layout.addWidget(self.vertical_split,1); video_layout.addLayout(zoom_row); video_layout.addWidget(self.timeline_scroll)
        code_page=QWidget(); code_layout=QVBoxLayout(code_page); code_layout.setContentsMargins(8,8,8,8)
        self._code_view_dirty=False; self._code_user_editing=False; self._updating_code_view=False
        self.code_view=PythonCodeEditor(); self.code_view.setReadOnly(False); self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._code_highlighter=PythonHighlighter(self.code_view.document())
        code_font=QFont(MANIM_TEXT_FONT, 10)
        self.code_view.setFont(code_font)
        self.code_view.textChanged.connect(self._mark_code_view_edited)
        self.code_view.setPlaceholderText('Escribe una escena Python completa usando Manim.')
        self.code_view.setStyleSheet('QPlainTextEdit{background:#15171b;color:#d8dee9;border:1px solid #363a40;border-radius:6px;padding:10px;font-family:sans-serif;font-size:13px;selection-background-color:#365f8c}')
        code_toolbar=QHBoxLayout()
        self.render_code_button=QPushButton('▶ Ejecutar escena')
        self.render_code_button.setToolTip('Ejecutar el código con Manim y actualizar la previsualización')
        self.render_code_button.clicked.connect(self.render_code_scene)
        self.show_manim_error_button=QPushButton('Ver error')
        self.show_manim_error_button.setVisible(False)
        self.show_manim_error_button.clicked.connect(self._show_last_manim_error)
        self.code_status=QLabel('El código y la previsualización se actualizan al terminar de editar.')
        self.code_status.setWordWrap(True)
        code_toolbar.addWidget(self.render_code_button)
        code_toolbar.addWidget(self.show_manim_error_button)
        code_toolbar.addWidget(self.code_status,1)
        code_layout.addLayout(code_toolbar)
        code_layout.addWidget(self.code_view)
        self._code_render_timer=QTimer(self); self._code_render_timer.setSingleShot(True); self._code_render_timer.setInterval(1000); self._code_render_timer.timeout.connect(self._render_edited_code)
        self._auto_render_pending=False; self._auto_rendering=False; self._last_manim_error=''
        self._preview_sync_timer=QTimer(self); self._preview_sync_timer.setSingleShot(True); self._preview_sync_timer.setInterval(100); self._preview_sync_timer.timeout.connect(self._sync_preview_changes)
        self.workspace_pages=QStackedWidget(); self.workspace_pages.addWidget(video_page); self.workspace_pages.addWidget(code_page)
        self.workspace_tab_bar.currentChanged.connect(self.workspace_pages.setCurrentIndex)
        center.addWidget(self.workspace_pages,1)
        self._update_timeline_scroll(); body.addLayout(center,1)
        # Panel lateral de capas y propiedades; las altas se hacen desde el lienzo.
        side=QVBoxLayout(); side.addWidget(QLabel('CAPAS'))
        self.objects=QListWidget(); self.objects.currentRowChanged.connect(self.select_object); side.addWidget(self.objects,1)
        object_actions=QHBoxLayout()
        duplicate_btn=QPushButton('Duplicar'); duplicate_btn.clicked.connect(self.duplicate_object); object_actions.addWidget(duplicate_btn)
        delete_btn=QPushButton('Eliminar'); delete_btn.clicked.connect(self.delete_object); object_actions.addWidget(delete_btn)
        side.addLayout(object_actions)
        side.addWidget(QLabel('PROPIEDADES'))
        form=QFormLayout(); self.name=QLineEdit(); self.expr=QLineEdit()
        self.start=QDoubleSpinBox(); self.start.setRange(0,999); self.start.setDecimals(2); self.start.setSingleStep(0.1)
        self.end=QDoubleSpinBox(); self.end.setRange(0.01,999); self.end.setDecimals(2); self.end.setSingleStep(0.1)
        self.length=self.end
        self.color_btn=QPushButton('Color del objeto'); self.color_btn.clicked.connect(lambda: self.choose_color('color'))
        self.clip_color_btn=QPushButton('Color del bloque'); self.clip_color_btn.clicked.connect(lambda: self.choose_color('clip_color'))
        self.animation_box=QComboBox()
        for label,value in [('Sin animación','None'),('Crear','Create'),('Aparecer','FadeIn'),('Escribir','Write'),('Crecer desde el centro','GrowFromCenter')]:
            self.animation_box.addItem(label,value)
        self.visible=QCheckBox('Visible en la escena'); self.visible.stateChanged.connect(self.visibility_changed)
        for label,w in [('Nombre del bloque',self.name),('Función / texto',self.expr),('Inicio (s)',self.start),('Final (s)',self.end),('Animación',self.animation_box),('Color del objeto',self.color_btn),('Color del bloque',self.clip_color_btn),('',self.visible)]: form.addRow(label,w)
        side.addLayout(form); self.apply_btn=QPushButton('Aplicar cambios'); self.apply_btn.clicked.connect(self.apply_properties); side.addWidget(self.apply_btn); side.addStretch(); body.addLayout(side)
        outer.addLayout(body,1); self.setCentralWidget(root)
        # Apariencia global de la ventana y controles.
        self.setStyleSheet("QWidget#root{background:#111317;color:#e7e7e7;font-family:sans-serif} QFrame,QListWidget,QLineEdit,QSpinBox,QComboBox{border-radius:7px} QPushButton,QLineEdit,QSpinBox,QListWidget,QComboBox{background:#202226;color:#eee;border:1px solid #363a40;border-radius:7px;padding:5px} QPushButton:hover{background:#30343b} QSplitter::handle:vertical{background:#34363a;height:5px;border-radius:3px} QSplitter::handle:vertical:hover{background:#777} QScrollBar:vertical{background:transparent;width:8px;margin:0} QScrollBar::handle:vertical{background:#52565c;min-height:24px;border-radius:4px} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0} QScrollBar:horizontal{background:#1b1d21;height:8px} QScrollBar::handle:horizontal{background:#52565c;min-width:24px;border-radius:4px} QSlider::groove:horizontal{height:3px;background:#464646;border-radius:2px} QSlider::handle:horizontal{background:#f5bd32;width:11px;margin:-4px 0;border-radius:6px}")
        self.timer=QTimer(self); self.timer.setInterval(40); self.timer.timeout.connect(self.tick); self.set_format_control(); self.refresh_objects(); self.refresh_code_view()

    def set_format_control(self):
        idx=1 if self.state.get('format')=='vertical' else 0
        self.format_box.blockSignals(True); self.format_box.setCurrentIndex(idx); self.format_box.blockSignals(False)
    def change_format(self,index):
        fmt,width,height=self.format_box.currentData(); self.state.update(format=fmt,width=width,height=height); self.update_views()

    def refresh_objects(self,select=0):
        self.objects.blockSignals(True); self.objects.clear(); self.objects.addItems([o['name'] for o in self.state['objects']]); self.objects.blockSignals(False)
        if self.state['objects']: self.objects.setCurrentRow(min(select,len(self.state['objects'])-1)); self.select_object(self.objects.currentRow())
        else: self.timeline.set_selected_index(None)
        self.project_label.setText(self.path.name if self.path else self.state['name']); self.update_views()
    def select_object(self,row):
        if row<0 or row>=len(self.state['objects']): return
        o=self.state['objects'][row]
        self.timeline.set_selected_index(row)
        self.name.setText(o.get('name','Objeto')); self.expr.setText(o.get('expression',''))
        self.start.setValue(float(o.get('start',0))); self.end.setValue(float(o.get('start',0))+float(o.get('duration',1)))
        self.animation_box.setCurrentIndex(max(0,self.animation_box.findData(o.get('animation','None'))))
        self.color_btn.setText(o.get('color','#65d6ff')); self.color_btn.setStyleSheet('background:'+o.get('color','#65d6ff'))
        clip_color=o.get('clip_color',o.get('color','#65d6ff'))
        self.clip_color_btn.setText(clip_color); self.clip_color_btn.setStyleSheet('background:'+clip_color)
        self.expr.setEnabled(o.get('kind') in {'graph','text','table'})
        self.animation_box.setEnabled(o.get('kind')!='manim_scene')
        self.visible.blockSignals(True); self.visible.setChecked(o.get('visible',True)); self.visible.blockSignals(False)
    def _timeline_clip_selected(self,index):
        self.objects.setCurrentRow(index)
    def duplicate_object(self):
        row=self.objects.currentRow()
        if row<0 or row>=len(self.state['objects']): return
        original=self.state['objects'][row]
        duplicate={**original}
        if isinstance(original.get('position'),dict):
            duplicate['position']=dict(original['position'])
            duplicate['position']['x']=min(0.95,duplicate['position'].get('x',0.5)+0.025)
            duplicate['position']['y']=min(0.95,duplicate['position'].get('y',0.5)+0.025)
        duplicate['name']=f"{original.get('name','Objeto')} (copia)"
        duplicate.pop('manim_variable',None)
        duplicate['track']=self.preview._track_for_new_object()
        self.state['objects'].insert(row+1,duplicate)
        self.refresh_objects(row+1)
        self.preview_state_changed()
    def delete_object(self):
        row=self.objects.currentRow()
        if row<0:return
        self.state['objects'].pop(row); self.refresh_objects(max(0,row-1)); self.preview_state_changed()
    def visibility_changed(self,_):
        row=self.objects.currentRow()
        if row>=0:
            self.state['objects'][row]['visible']=self.visible.isChecked()
            self.update_views(); self.preview_state_changed()
    def apply_properties(self):
        row=self.objects.currentRow()
        if row<0:return
        o=self.state['objects'][row]
        start=float(self.start.value()); end=max(start+0.01,float(self.end.value()))
        o.update(name=self.name.text() or 'Objeto',expression=self.expr.text(),start=start,duration=end-start,
                 animation=self.animation_box.currentData(),clip_color=o.get('clip_color',o.get('color','#65d6ff')))
        self.refresh_objects(row)
        self.preview_state_changed()
    def choose_color(self, field='color'):
        row=self.objects.currentRow()
        if row>=0:
            obj=self.state['objects'][row]
            current=obj.get(field,obj.get('color','#65d6ff'))
            c=QColorDialog.getColor(QColor(current),self)
            if c.isValid():
                obj[field]=c.name(); self.select_object(row); self.update_views(); self.preview_state_changed()


    # Mantiene las vistas, el código y el historial alineados con el estado.
    def update_views(self):
        self.state['duration']=max([self.state['duration']]+[o['start']+o['duration'] for o in self.state['objects']])
        snapshot=json.dumps(self.state,sort_keys=True)
        if snapshot != self._last_snapshot:
            # Conserva el código personalizado aunque todavía no haya un render en caché.
            self._undo_stack.append(self._last_snapshot); self._undo_stack=self._undo_stack[-100:]; self._redo_stack.clear(); self._last_snapshot=snapshot
            if not self._installing_manim_render and not self._code_view_dirty:
                self.refresh_code_view()
        self._timeline_timing_snapshot=self._timeline_timing_signature()
        self.preview.update(); self.timeline.update(); self._update_timeline_scroll()

    def _clear_manim_render(self):
        self.preview.set_rendered_frame(None)
        self._manim_render_frames=[]
        self._manim_frame_index=None
        self._manim_video_path=None
        if self._manim_render_directory:
            shutil.rmtree(self._manim_render_directory,ignore_errors=True)
            self._manim_render_directory=None

    # Historial de deshacer/rehacer basado en instantáneas del proyecto.
    def _restore_history(self, source, destination):
        if not source:return
        destination.append(json.dumps(self.state)); self.state=json.loads(source.pop()); self._last_snapshot=json.dumps(self.state,sort_keys=True)
        self._render_generation+=1; self._clear_manim_render(); self._code_view_dirty=False
        self.preview.state=self.state; self.timeline.state=self.state; self.refresh_objects()
        if not self._code_view_dirty:
            self.refresh_code_view()
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
        else:
            self.refresh_objects(0)
        self._update_timeline_scroll()
    def trim_clip(self):
        if not self.timeline.trim_at_playhead():
            QMessageBox.information(self,'Trim','Selecciona un bloque y coloca el cabezal dentro del clip para dividirlo.')
        else:
            self.refresh_objects(min(self.timeline._selected_index+1,len(self.state['objects'])-1))
    def seek(self,v):
        seconds=v if isinstance(v,float) else self.state['duration']*v/100
        seconds=max(0,min(self.state['duration'],seconds)); self.slider.blockSignals(True); self.slider.setValue(round(seconds/max(1,self.state['duration'])*100)); self.slider.blockSignals(False)
        self.preview.progress=seconds/max(1,self.state['duration']); self.timeline.position=seconds; self.update_views()
        if self._manim_render_frames and not self._timeline_preview_override:
            frame_index=min(len(self._manim_render_frames)-1,round(self.preview.progress*(len(self._manim_render_frames)-1)))
            if frame_index != self._manim_frame_index:
                self.preview.set_rendered_frame(QPixmap(self._manim_render_frames[frame_index]))
                self._manim_frame_index=frame_index
        frame=round(seconds*30); total=round(self.state['duration']*30)
        def tc(n):
            s,f=divmod(n,30); h,s=divmod(s,3600); m,s=divmod(s,60); return f'{h:02d}:{m:02d}:{s:02d}:{f:02d}'
        self.timecode.setText(f'{tc(frame)} / {tc(total)}')
    def toggle_play(self):
        self.playing=not self.playing; self.play_btn.setText('❚❚' if self.playing else '▶'); self.play_btn.setToolTip('Pausar' if self.playing else 'Reproducir'); self.timer.start() if self.playing else self.timer.stop()
    def tick(self):
        duration=max(0.1,float(self.state.get('duration',10)))
        seconds=float(self.timeline.position) + self.timer.interval()/1000
        if seconds>=duration:
            self.timer.stop(); self.playing=False; self.play_btn.setText('▶'); self.play_btn.setToolTip('Reproducir')
            self.seek(duration)
        else:
            self.seek(seconds)
    def new_project(self):
        self._render_generation+=1; self._clear_manim_render(); self._code_view_dirty=False
        self.state=new_project(); self.path=None; self.preview.state=self.state; self.timeline.state=self.state; self.timeline.set_scroll_offset(0); self._update_timeline_scroll(); self.refresh_objects(); self.refresh_code_view()
    # Persistencia: carga y guardado del formato de proyecto.
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Abrir proyecto','','Manim Editor (*.manimproj);;JSON (*.json)')
        if not path:return
        try:
            data=load_project(path)
            self._render_generation+=1; self._clear_manim_render(); self._code_view_dirty=False
            self.state=data; self._last_snapshot=json.dumps(self.state,sort_keys=True); self.path=Path(path); self.preview.state=self.state; self.timeline.state=self.state; self._update_timeline_scroll(); self.set_format_control(); self.refresh_objects()
            self.refresh_code_view()
        except (OSError,ValueError,AssertionError,KeyError) as e: QMessageBox.critical(self,'No se pudo abrir',str(e))
    def save_project(self):
        if not self.path:
            path,_=QFileDialog.getSaveFileName(self,'Guardar proyecto','proyecto.maniproj','Manim Editor (*.manimproj)')
            if not path:return
            self.path=Path(path)
        try:
            if self._code_view_dirty:
                self.state['manim_source']=self.code_view.toPlainText()
            self.state['name']=self.path.stem; save_project(self.path,self.state); self.project_label.setText(self.path.name)
            self._last_snapshot=json.dumps(self.state,sort_keys=True)
        except OSError as e: QMessageBox.critical(self,'No se pudo guardar',str(e))

    # Exportación: renderiza cada fotograma de la previsualización y lo envía a ffmpeg.
    def export_video(self):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            QMessageBox.warning(self,'Exportar MP4','No se encontró ffmpeg. Instálalo y vuelve a intentarlo.')
            return

        if self._code_view_dirty:
            QMessageBox.information(self,'Código sin renderizar','Ejecuta la escena con Manim antes de exportar el código editado.')
            return
        output_path,_=QFileDialog.getSaveFileName(self,'Exportar video MP4','video.mp4','Video MP4 (*.mp4)')
        if not output_path:return
        if not output_path.lower().endswith('.mp4'):
            output_path += '.mp4'

        if self._manim_video_path and os.path.isfile(self._manim_video_path):
            try:
                shutil.copy2(self._manim_video_path,output_path)
            except OSError as error:
                QMessageBox.critical(self,'No se pudo exportar el video',str(error))
            else:
                QMessageBox.information(self,'Video exportado',f'El video se guardó en:\n{output_path}')
            return

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

    def closeEvent(self,event):
        self._render_generation+=1
        worker=self._manim_render_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait()
        self._clear_manim_render()
        super().closeEvent(event)
