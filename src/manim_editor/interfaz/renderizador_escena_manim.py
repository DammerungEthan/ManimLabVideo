"""Coordina la ejecución de escenas y la carga de sus fotogramas."""

import json
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)
from manim_editor.servicios.ejecutor_manim import ManimRenderWorker


class RenderizadorEscenaManim:
    """Coordina la ejecución de escenas y la carga de sus fotogramas."""

    def render_code_scene(self, automatic=False):
        if not automatic:
            self._code_render_timer.stop()
        if self._manim_render_worker is not None and self._manim_render_worker.isRunning():
            self._auto_render_pending=True
            return
        source=self.code_view.toPlainText()
        if not source.strip():
            self.code_status.setText('Escribe una escena Python antes de ejecutarla.')
            self.code_status.setStyleSheet('color:#ff8585')
            return

        width=max(1,int(self.state.get('width',1920)))
        height=max(1,int(self.state.get('height',1080)))
        factor=min(640/width,640/height)
        render_width=max(240,round(width*factor))
        render_height=max(240,round(height*factor))
        project_root=Path(__file__).resolve().parents[3]
        worker=ManimRenderWorker(source,render_width,render_height,project_root,self)
        worker.render_done.connect(self._on_manim_render_done)
        worker.finished.connect(self._release_manim_render_worker)
        self._active_render_source=source
        self._render_generation=getattr(self,'_render_generation',0)
        self._active_render_generation=self._render_generation
        self._auto_render_pending=False
        self._auto_rendering=automatic
        self._manim_render_worker=worker
        self.render_code_button.setEnabled(False)
        self.code_status.setText('Renderizando automáticamente…' if automatic else 'Renderizando la escena con Manim…')
        self.code_status.setStyleSheet('color:#d8c27a')
        worker.start()

    def _on_manim_render_done(self, succeeded, render_directory, frames, video_path, scene_name, error):
        self.render_code_button.setEnabled(True)
        if getattr(self,'_active_render_generation',-1) != getattr(self,'_render_generation',0):
            if succeeded and render_directory:
                shutil.rmtree(render_directory,ignore_errors=True)
            return
        if not succeeded:
            self._last_manim_error=error
            self.show_manim_error_button.setVisible(True)
            self.code_status.setText(
                'Falló el render automático; se conserva la última previsualización. Usa «Ver error» para ver el detalle.'
                if self._auto_rendering else
                'Manim no pudo renderizar el código; se conserva la última previsualización.'
            )
            self.code_status.setStyleSheet('color:#ff8585')
            if not self._auto_rendering:
                self._show_manim_error(error)
            return

        selected_row=self.objects.currentRow()
        selected_variable=(
            self.state['objects'][selected_row].get('manim_variable')
            if 0<=selected_row<len(self.state.get('objects',[])) else None
        )
        if self._manim_render_directory:
            shutil.rmtree(self._manim_render_directory,ignore_errors=True)
        self._manim_render_directory=render_directory
        self._manim_render_frames=list(frames)
        self._manim_video_path=video_path
        self._code_user_editing=False
        self._manim_frame_index=None
        duration=max(0.1,len(self._manim_render_frames)/30)
        tracks=self.state.setdefault('tracks',['Pista 1'])
        track=tracks[0] if tracks else 'Pista 1'
        if not tracks:
            tracks.append(track)
        try:
            parsed_objects,_parsed_duration=self._parse_manim_scene(self._active_render_source)
        except (SyntaxError,TypeError,ValueError):
            parsed_objects=[]
        editable_objects={}
        for obj in parsed_objects:
            variable=obj.get('manim_variable')
            if not variable:
                continue
            if variable not in editable_objects:
                editable_objects[variable]=dict(obj)
            else:
                existing=editable_objects[variable]
                end=max(existing['start']+existing['duration'],obj['start']+obj['duration'])
                existing['start']=min(existing['start'],obj['start'])
                existing['duration']=max(0.1,end-existing['start'])
        editable_objects=list(editable_objects.values())
        if editable_objects:
            for obj in editable_objects:
                obj['start']=max(0.0,min(duration,obj.get('start',0.0)))
                obj['duration']=max(0.1,min(obj.get('duration',duration),duration-obj['start']))
            rendered_objects=editable_objects
        else:
            rendered_objects=[{
                'name':f'Escena Manim · {scene_name}','kind':'manim_scene',
                'expression':'','color':'#65d6ff','start':0.0,'duration':duration,
                'visible':True,'track':track,
            }]
        old_snapshot=self._last_snapshot
        self._undo_stack.append(old_snapshot)
        self._undo_stack=self._undo_stack[-100:]
        self._redo_stack.clear()
        self.state['objects']=rendered_objects
        self.state['duration']=duration
        self.state['manim_source']=self._active_render_source
        self._timeline_timing_snapshot=self._timeline_timing_signature()
        self._timeline_preview_override=False
        self._last_snapshot=json.dumps(self.state,sort_keys=True)
        self._installing_manim_render=True
        try:
            self.preview.state=self.state
            self.timeline.state=self.state
            self.preview.progress=0
            self.timeline.position=0
            self._code_view_dirty=False
            self.preview.set_editing_enabled(True)
            selected_index=next(
                (index for index,obj in enumerate(rendered_objects)
                 if selected_variable and obj.get('manim_variable')==selected_variable),
                min(max(selected_row,0),len(rendered_objects)-1),
            )
            self.refresh_objects(selected_index)
            self.refresh_code_view()
            preview_seek=getattr(self,'_pending_preview_seek',None)
            self._pending_preview_seek=None
            self.seek(max(0.0,min(duration,preview_seek)) if preview_seek is not None else 0.0)
            self.timeline.update()
            self.code_status.setText(f'Render listo · {scene_name} · {duration:.1f} s')
            self.code_status.setStyleSheet('color:#9bd6a4')
            self._last_manim_error=''
            self.show_manim_error_button.setVisible(False)
        finally:
            self._installing_manim_render=False

    def _show_manim_error(self, error):
        """Muestra el traceback completo en un cuadro que permite desplazarse y copiar."""
        dialog = QDialog(self)
        dialog.setWindowTitle('Error al ejecutar Manim')
        dialog.resize(900, 600)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            'Manim no pudo renderizar la escena. Puedes desplazarte por el error o copiarlo completo.'
        ))

        error_text = QPlainTextEdit(dialog)
        error_text.setReadOnly(True)
        error_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        error_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        error_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        error_text.setStyleSheet(
            'QPlainTextEdit{background:#15171b;color:#d8dee9;border:1px solid #363a40;'
            'border-radius:6px;padding:8px;font-family:sans-serif;font-size:12px;'
            'selection-background-color:#365f8c}'
        )
        error_text.setPlainText(str(error) or 'Manim terminó con un error sin incluir detalles.')
        error_text.setMinimumSize(680, 380)
        layout.addWidget(error_text, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        copy_button = QPushButton('Copiar error', dialog)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(error_text.toPlainText()))
        buttons.addWidget(copy_button)
        close_button = QPushButton('Cerrar', dialog)
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        dialog.exec()

    def _release_manim_render_worker(self):
        worker=self._manim_render_worker
        self._manim_render_worker=None
        if worker is not None:
            worker.deleteLater()
        if self._auto_render_pending and not self._code_render_timer.isActive():
            self._code_render_timer.start(0)
