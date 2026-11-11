"""Editor de proyectos y escenas Manim con previsualización integrada."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QSlider, QSplitter,
    QVBoxLayout, QWidget, QComboBox, QScrollBar,
    QToolButton, QScrollArea, QFrame,
)

from manim_editor.models.project import new_project
from manim_editor.services.project_io import load_project, save_project
from manim_editor.ui.preview import Preview
from manim_editor.ui.timeline import Timeline
from manim_editor.ui.element_catalog import ELEMENTS
from manim_editor.ui.inspector import Inspector
from manim_editor.ui.video_export import export_preview_video, show_export_result


class MainWindow(QMainWindow):
    """Ventana principal que coordina la interfaz y el estado del proyecto."""

    def __init__(self):
        super().__init__(); self.state=new_project(); self.path=None; self.playing=False
        self.setWindowTitle('Manim Editor'); self.resize(1360,850)
        self._undo_stack=[]; self._redo_stack=[]; self._last_snapshot=json.dumps(self.state,sort_keys=True)
        # Barra superior: nombre, formato, historial y operaciones de archivo.
        root=QWidget(); root.setObjectName('root'); outer=QVBoxLayout(root); outer.setContentsMargins(8,8,8,8)
        bar=QHBoxLayout()
        app_icon=QLabel(); app_icon.setFixedSize(28,28); app_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = Path(__file__).resolve().parent.parent / 'icons' / 'icon.png'
        icon_pixmap=QPixmap(str(icon_path))
        if not icon_pixmap.isNull():
            app_icon.setPixmap(icon_pixmap.scaled(28,28,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            bar.addWidget(app_icon)
        self.project_label=QLabel(self.state['name']); bar.addWidget(self.project_label); bar.addStretch()
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
        # Área central: previsualización y timeline, con selección gráfica.
        body=QHBoxLayout(); center=QVBoxLayout(); self.preview=Preview(self.state)
        self.preview.on_selection_changed=self.select_object
        self.play_btn=QPushButton('▶'); self.play_btn.setToolTip('Reproducir'); self.play_btn.setFixedWidth(32); self.play_btn.clicked.connect(self.toggle_play)
        self.slider=QSlider(Qt.Orientation.Horizontal); self.slider.setRange(0,100); self.slider.setValue(38); self.slider.valueChanged.connect(self.seek)
        self.timecode=QLabel('00:00:03:24 / 00:00:10:00'); self.timecode.setMinimumWidth(190)
        self.trim_button=QPushButton('✂ Trim'); self.trim_button.setToolTip('Dividir el clip seleccionado en el cabezal'); self.trim_button.clicked.connect(self.trim_clip)
        timeline_row=QHBoxLayout(); self.timeline=Timeline(self.state, self.seek, self.timeline_state_changed, self.select_object); self.timeline.set_transport_controls(self.play_btn, self.slider, self.timecode); timeline_row.addWidget(self.timeline,1)
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
        center.addWidget(video_page,1)
        self._update_timeline_scroll(); body.addLayout(center,1)
        # Inspector lateral: creación, selección y propiedades de elementos.
        side=QVBoxLayout(); side.addWidget(QLabel('AÑADIR ELEMENTO'))
        self.element_category=QComboBox()
        self.element_category.addItems(['Todos'] + sorted({element.category for element in ELEMENTS}))
        self.element_category.currentTextChanged.connect(self.populate_element_list)
        side.addWidget(self.element_category)
        self.element_list=QListWidget(); self.element_list.setMaximumHeight(190); side.addWidget(self.element_list)
        self.populate_element_list('Todos')
        add_btn=QPushButton('+ Añadir al timeline'); add_btn.clicked.connect(self.add_selected_element); side.addWidget(add_btn)
        delete_btn=QPushButton('Eliminar clip seleccionado'); delete_btn.clicked.connect(self.delete_object); side.addWidget(delete_btn)
        self.inspector=Inspector(self.update_views)
        inspector_scroll=QScrollArea(); inspector_scroll.setWidgetResizable(True); inspector_scroll.setFrameShape(QFrame.Shape.NoFrame); inspector_scroll.setWidget(self.inspector); side.addWidget(inspector_scroll,1); body.addLayout(side)
        outer.addLayout(body,1); self.setCentralWidget(root)
        # Apariencia global de la ventana y controles.
        self.setStyleSheet("QWidget#root{background:#111317;color:#e7e7e7;font-family:'Segoe UI',sans-serif} QFrame,QListWidget,QLineEdit,QSpinBox,QComboBox{border-radius:7px} QPushButton,QLineEdit,QSpinBox,QListWidget,QComboBox{background:#202226;color:#eee;border:1px solid #363a40;border-radius:7px;padding:5px} QPushButton:hover{background:#30343b} QSplitter::handle:vertical{background:#34363a;height:5px;border-radius:3px} QSplitter::handle:vertical:hover{background:#777} QScrollBar:vertical{background:transparent;width:8px;margin:0} QScrollBar::handle:vertical{background:#52565c;min-height:24px;border-radius:4px} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0} QScrollBar:horizontal{background:#1b1d21;height:8px} QScrollBar::handle:horizontal{background:#52565c;min-width:24px;border-radius:4px} QSlider::groove:horizontal{height:3px;background:#464646;border-radius:2px} QSlider::handle:horizontal{background:#f5bd32;width:11px;margin:-4px 0;border-radius:6px}")
        self.timer=QTimer(self); self.timer.setInterval(40); self.timer.timeout.connect(self.tick); self.set_format_control(); self.inspector.set_object(None); self.refresh_objects(); self.seek(3.8)

    def set_format_control(self):
        idx=1 if self.state.get('format')=='vertical' else 0
        self.format_box.blockSignals(True); self.format_box.setCurrentIndex(idx); self.format_box.blockSignals(False)
    def change_format(self,index):
        fmt,width,height=self.format_box.currentData(); self.state.update(format=fmt,width=width,height=height); self.update_views()

    def refresh_objects(self,select=None):
        if select is not None and 0 <= select < len(self.state['objects']): self.select_object(select)
        self.project_label.setText(self.path.name if self.path else self.state['name']); self.update_views()
    def select_object(self,row):
        if row is None or row<0 or row>=len(self.state['objects']):
            self.timeline.selected_index=None; self.preview.selected_index=None; self.inspector.set_object(None); self.timeline.update(); self.preview.update(); return
        self.timeline.selected_index=row; self.timeline._selected_index=row; self.preview.selected_index=row; self.inspector.set_object(self.state['objects'][row]); self.timeline.update(); self.preview.update()
    def add_selected_element(self):
        row=self.element_list.currentRow()
        if row<0: return
        preset_index=self.element_list.currentItem().data(Qt.ItemDataRole.UserRole)
        preset=ELEMENTS[preset_index]; track=self.timeline.selected_track or self.state.setdefault('tracks',['Pista 1'])[0]
        obj={'name':preset.label,'kind':preset.kind,'expression':preset.expression,'color':preset.color,'start':round(self.timeline.position),'duration':max(1,self.state['duration']-round(self.timeline.position)),'visible':True,'track':track,'position':{'x':0.52,'y':0.54},'scale':1.0,'rotation':0,'opacity':1.0,'stroke_width':3,'font_size':42,'font_family':'Sans Serif'}
        self.state['objects'].append(obj); self.select_object(len(self.state['objects'])-1); self.refresh_objects()
    def delete_object(self):
        row=self.timeline.selected_index
        if row is None or not 0 <= row < len(self.state['objects']):return
        self.state['objects'].pop(row); self.select_object(min(row,len(self.state['objects'])-1) if self.state['objects'] else None); self.refresh_objects()
    def preview_state_changed(self):
        """Actualiza la vista después de un cambio gráfico en el canvas."""
        index=self.timeline.selected_index
        selected=self.state['objects'][index] if index is not None and index < len(self.state['objects']) else None
        self.inspector.set_object(selected)
        self.update_views()

    def timeline_state_changed(self):
        """Refleja en el inspector los cambios hechos al mover clips o pistas."""
        index=self.timeline.selected_index
        if index is not None and index < len(self.state['objects']):
            self.inspector.set_object(self.state['objects'][index])
        self.update_views()

    def populate_element_list(self, category):
        """Filtra el catálogo y conserva el índice real de cada elemento."""
        self.element_list.clear()
        for index, element in enumerate(ELEMENTS):
            if category != 'Todos' and element.category != category:
                continue
            item=QListWidgetItem(element.label)
            item.setData(Qt.ItemDataRole.UserRole,index)
            self.element_list.addItem(item)

    # Sincroniza el preview y timeline y registra cambios para deshacer/rehacer.
    def update_views(self):
        self.state['duration']=max([self.state['duration']]+[o['start']+o['duration'] for o in self.state['objects']])
        snapshot=json.dumps(self.state,sort_keys=True)
        if snapshot != self._last_snapshot:
            self._undo_stack.append(self._last_snapshot); self._undo_stack=self._undo_stack[-100:]; self._redo_stack.clear(); self._last_snapshot=snapshot
        self.preview.update(); self.timeline.update(); self._update_timeline_scroll()

    # Historial de deshacer/rehacer basado en instantáneas del proyecto.
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
            total_seconds=round(n/30); hours,remainder=divmod(total_seconds,3600); minutes,seconds=divmod(remainder,60)
            return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
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
        self.state=new_project(); self.path=None; self._undo_stack.clear(); self._redo_stack.clear(); self._last_snapshot=json.dumps(self.state,sort_keys=True); self.preview.state=self.state; self.timeline.state=self.state; self.timeline.position=0; self.timeline.set_scroll_offset(0); self._update_timeline_scroll(); self.refresh_objects(); self.seek(0)
    # Persistencia: carga y guardado del formato de proyecto.
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Abrir proyecto','','Manim Editor (*.manimproj);;JSON (*.json)')
        if not path:return
        try:
            data=load_project(path)
            self.state=data; self._undo_stack.clear(); self._redo_stack.clear(); self._last_snapshot=json.dumps(self.state,sort_keys=True); self.path=Path(path); self.preview.state=self.state; self.timeline.state=self.state; self.timeline.position=0; self._update_timeline_scroll(); self.set_format_control(); self.refresh_objects(); self.seek(0)
        except (OSError,ValueError,AssertionError,KeyError) as e: QMessageBox.critical(self,'No se pudo abrir',str(e))
    def save_project(self):
        if not self.path:
            path,_=QFileDialog.getSaveFileName(self,'Guardar proyecto','proyecto.maniproj','Manim Editor (*.manimproj)')
            if not path:return
            self.path=Path(path)
        try:
            self.state['name']=self.path.stem; save_project(self.path,self.state); self.project_label.setText(self.path.name)
            self._last_snapshot=json.dumps(self.state,sort_keys=True)
        except OSError as e: QMessageBox.critical(self,'No se pudo guardar',str(e))

    # Exportación: la lógica de fotogramas y ffmpeg vive en su propio módulo.
    def export_video(self):
        output_path,_=QFileDialog.getSaveFileName(self,'Exportar video MP4','video.mp4','Video MP4 (*.mp4)')
        if not output_path:return
        if not output_path.lower().endswith('.mp4'):
            output_path += '.mp4'
        result=export_preview_video(self.state,output_path,self,self.timer)
        show_export_result(self,result,output_path)

    def closeEvent(self,event):
        """Cierra la ventana y libera los recursos de Qt."""
        super().closeEvent(event)
