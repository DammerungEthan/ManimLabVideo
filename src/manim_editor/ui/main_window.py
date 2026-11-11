"""Editor de proyectos y escenas Manim con previsualización integrada."""
import ast
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint, QRegularExpression, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QImage, QPainter, QPixmap, QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton, QSlider, QSpinBox, QDoubleSpinBox, QSplitter,
    QVBoxLayout, QWidget, QLineEdit, QFormLayout, QCheckBox, QComboBox, QScrollBar,
    QProgressDialog, QToolButton, QPlainTextEdit, QTabBar, QStackedWidget, QDialog,
)

from manim_editor.models.project import new_project
from manim_editor.services.project_io import load_project, save_project
from manim_editor.services.manim_runner import ManimRenderWorker
from manim_editor.ui.preview import Preview
from manim_editor.ui.timeline import Timeline
from manim_editor.typography import MANIM_MATH_FONT, MANIM_TEXT_FONT


class PythonHighlighter(QSyntaxHighlighter):
    """Resaltado ligero de sintaxis Python y nombres frecuentes de Manim."""

    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        self._add_rule(
            r"\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b",
            "#c792ea", True,
        )
        self._add_rule(
            r"\b(Scene|ThreeDScene|MovingCameraScene|Text|MathTex|Tex|Axes|VGroup|Vector|Arrow|Line|Dot|Circle|Square|Rectangle|Ellipse|Polygon|NumberPlane|Table|ValueTracker|always_redraw|Create|Write|FadeIn|FadeOut|Transform|ReplacementTransform|Rotate|GrowArrow|DrawBorderThenFill|AnimationGroup|Succession|LaggedStart)\b",
            "#82aaff", True,
        )
        self._add_rule(r"\b(self|super|np|numpy|math)\b", "#f78c6c")
        self._add_rule(r"\b\d+(?:\.\d+)?\b", "#f78c6c")
        self._add_rule(r"\b[A-Z][A-Z0-9_]*\b", "#ffcb6b")
        self._add_rule(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", "#c3e88d")
        self._add_rule(r"#[^\n]*", "#697386")

    def _add_rule(self, pattern, color, bold=False):
        char_format = QTextCharFormat()
        char_format.setForeground(QColor(color))
        if bold:
            char_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(pattern), char_format))

    def highlightBlock(self, text):
        for expression, char_format in self.rules:
            match = expression.globalMatch(text)
            while match.hasNext():
                result = match.next()
                self.setFormat(result.capturedStart(), result.capturedLength(), char_format)


class PythonCodeEditor(QPlainTextEdit):
    """Editor Python con tabulación e indentación automática básica."""

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            self.textCursor().insertText("    ")
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            line = cursor.block().text()
            indentation = line[:len(line) - len(line.lstrip())]
            if line.rstrip().endswith(":"):
                indentation += "    "
            cursor.insertText("\n" + indentation)
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
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
        code_font=QFont("monospace", 10); code_font.setStyleHint(QFont.StyleHint.Monospace)
        self.code_view.setFont(code_font)
        self.code_view.textChanged.connect(self._mark_code_view_edited)
        self.code_view.setPlaceholderText('Escribe una escena Python completa usando Manim.')
        self.code_view.setStyleSheet('QPlainTextEdit{background:#15171b;color:#d8dee9;border:1px solid #363a40;border-radius:6px;padding:10px;font-family:monospace;font-size:13px;selection-background-color:#365f8c}')
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

    # Convierte el estado del proyecto en una escena editable de Manim.
    def refresh_code_view(self, _index=None):
        saved_source = self.state.get('manim_source')
        if isinstance(saved_source, str) and saved_source.strip():
            self._updating_code_view=True
            self.code_view.setPlainText(saved_source)
            self._updating_code_view=False
            self._code_user_editing=False
            self._code_view_dirty=not bool(self._manim_video_path)
            self.preview.set_editing_enabled(not self._code_view_dirty)
            if self._code_view_dirty:
                self.code_status.setText('Código cargado. Ejecútalo para reconstruir la previsualización.')
                self.code_status.setStyleSheet('color:#d8c27a')
            else:
                self.code_status.setText('Código de Manim cargado desde el proyecto.')
                self.code_status.setStyleSheet('color:#aeb4bd')
            return
        lines = [
            'from manim import *',
            'import numpy as np',
            '',
            '',
            'class VideoManim(Scene):',
            '    def construct(self):',
            '        self.camera.background_color = "#000000"',
        ]
        width = max(1, int(self.state.get('width', 1920)))
        height = max(1, int(self.state.get('height', 1080)))
        scene_width = 14.222
        scene_height = scene_width * height / width
        frame_height = 1000 / (width / height)
        total_duration = max(0.0, float(self.state.get('duration', 10)))
        events = {}
        supported = 0
        text_index = 0

        for index, obj in enumerate(self.state.get('objects', [])):
            kind = obj.get('kind', '')
            if kind == 'manim_scene':
                continue
            if kind == 'text':
                text_index += 1
            if not obj.get('visible', True):
                continue

            position = obj.get('position')
            if not isinstance(position, dict):
                if kind == 'text':
                    position = {'x': 0.035, 'y': min(0.85, (36 + (text_index - 1) * 28) / frame_height)}
                else:
                    position = {'x': 0.52, 'y': 0.54}
            x = (float(position.get('x', 0.5)) - 0.5) * scene_width
            y = (0.5 - float(position.get('y', 0.5))) * scene_height
            location = f'[{x:.3f}, {y:.3f}, 0]'
            color = json.dumps(str(obj.get('color', '#65d6ff')))
            variable = f'obj_{index + 1}'
            expression = str(obj.get('expression', ''))
            definition = None

            if kind == 'axes':
                definition = f'{variable} = Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], tips=False).set_color({color}).move_to({location})'
            elif kind == 'graph':
                try:
                    graph_expression = self._function_expression_to_numpy(expression)
                    axes_expression=(
                        f'Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], '
                        f'x_length={scene_width:.6f}, y_length={scene_height:.6f}, tips=False)'
                    )
                    components=[]
                    if obj.get('show_grid',True):
                        components.append(
                            f'NumberPlane(x_range=[-7, 7, 2], y_range=[-4, 4, 2], '
                            f'x_length={scene_width:.6f}, y_length={scene_height:.6f}, '
                            f'axis_config={{"stroke_opacity": 0}}, '
                            f'background_line_style={{"stroke_color": "#586273", "stroke_opacity": 0.35}})'
                        )
                    if obj.get('show_axes',True):
                        components.append(axes_expression)
                    components.append(
                        f'{axes_expression}.plot(lambda x: {graph_expression}, x_range=[-7, 7], color={color})'
                    )
                    group=f'VGroup({", ".join(components)})' if len(components)>1 else components[0]
                    definition=f'{variable} = {group}.move_to({location})'
                except (SyntaxError, ValueError, TypeError):
                    definition = None
            elif kind == 'equation':
                definition = (
                    f'{variable} = MathTex({json.dumps(expression, ensure_ascii=False)}, '
                    f'font_size={int(obj.get("font_size", 48))}, color={color}).move_to({location})'
                )
            elif kind == 'text':
                font = json.dumps(str(obj.get('font_family', MANIM_TEXT_FONT)))
                weight = 'BOLD' if int(obj.get('font_weight', 400)) >= 700 else 'NORMAL'
                definition = (
                    f'{variable} = Text({json.dumps(expression, ensure_ascii=False)}, '
                    f'font={font}, font_size={int(obj.get("font_size", 48))}, '
                    f'weight={json.dumps(weight)}, color={color}).move_to({location})'
                )
            elif kind == 'point':
                definition = f'{variable} = Dot(point={location}, color={color})'
            elif kind == 'vector':
                definition = f'{variable} = Arrow(ORIGIN, RIGHT, color={color}).move_to({location})'
            elif kind == 'line':
                definition = f'{variable} = Line(LEFT, RIGHT, color={color}).move_to({location})'
            elif kind == 'circle':
                definition = f'{variable} = Circle(color={color}).move_to({location})'
            elif kind == 'ellipse':
                definition = f'{variable} = Ellipse(width=2, height=1, color={color}).move_to({location})'
            elif kind == 'arrow':
                definition = f'{variable} = Arrow(LEFT, RIGHT, color={color}).move_to({location})'
            elif kind == 'polygon':
                definition = f'{variable} = Polygon(LEFT, UP, RIGHT, color={color}).move_to({location})'
            elif kind == 'table':
                definition = f'{variable} = Table([[{json.dumps(expression, ensure_ascii=False)}]], include_outer_lines=True).move_to({location})'
            elif kind == 'group':
                definition = f'{variable} = VGroup()'

            if definition is None:
                lines.append(f'        # No hay conversión Manim disponible para el tipo: {kind or "desconocido"}.')
                continue
            obj['manim_variable']=variable

            object_scale=float(obj.get('scale',1.0))
            if kind not in {'text','group'} and object_scale != 1.0:
                definition += f'.scale({object_scale:.4f})'
            object_rotation=float(obj.get('rotation',0.0))
            if object_rotation != 0.0:
                definition += f'.rotate({object_rotation:.4f} * DEGREES)'

            supported += 1
            lines.extend('        ' + part.lstrip() for part in definition.splitlines())
            start = max(0.0, float(obj.get('start', 0)))
            duration = max(0.0, float(obj.get('duration', 0)))
            end = min(total_duration, start + duration)
            if start <= total_duration and end >= start:
                animation=obj.get('animation','None')
                if animation in {'Create','FadeIn','Write','GrowFromCenter'} and duration>0:
                    run_time=max(0.1,min(float(obj.get('animation_duration',1.0)),duration))
                    events.setdefault(min(start,total_duration),[]).append(
                        (1,f'self.play({animation}({variable}), run_time={run_time:.3f})',run_time)
                    )
                else:
                    events.setdefault(min(start,total_duration),[]).append((1,f'self.add({variable})',0.0))
                events.setdefault(end,[]).append((0,f'self.remove({variable})',0.0))

        lines.extend(['', '        # Aparición y desaparición según la línea de tiempo.'])
        current_time = 0.0
        for event_time in sorted(events):
            delta = event_time - current_time
            if delta > 0:
                lines.append(f'        self.wait({delta:.3f})')
            plays=[]
            for priority,statement,run_time in sorted(events[event_time],key=lambda item:(item[0],item[1])):
                if statement.startswith('self.play('):
                    plays.append((statement,run_time))
                    continue
                lines.append(f'        {statement}')
            if plays:
                if len(plays)==1:
                    lines.append(f'        {plays[0][0]}')
                else:
                    animations=[]
                    for statement,_run_time in plays:
                        animation_call=statement[len('self.play('):].split(', run_time=',1)[0]
                        animations.append(animation_call)
                    run_time=max(item[1] for item in plays)
                    lines.append(
                        f'        self.play(AnimationGroup({", ".join(animations)}, lag_ratio=0), run_time={run_time:.3f})'
                    )
                current_time=event_time+max(item[1] for item in plays)
            else:
                current_time=event_time
        if total_duration > current_time:
            lines.append(f'        self.wait({total_duration - current_time:.3f})')
        if supported == 0:
            lines.append('        self.wait(1)')
        generated_source=self._sync_object_metadata('\n'.join(lines) + '\n',self.state.get('objects',[]))
        self._updating_code_view=True
        self.code_view.setPlainText(generated_source)
        self._updating_code_view=False
        self._code_user_editing=False
        self._code_view_dirty=False
        self.preview.set_editing_enabled(True)
        self.code_status.setText('Código sincronizado con la previsualización.')
        self.code_status.setStyleSheet('color:#aeb4bd')

    # Renderiza automáticamente cuando termina una pausa en la escritura.
    def _mark_code_view_edited(self):
        if not self._updating_code_view:
            self._pending_preview_seek=None
            self._code_user_editing=True
            self._code_view_dirty=True
            self.preview.set_editing_enabled(False)
            self._render_generation+=1
            self._auto_render_pending=True
            self._code_render_timer.start()
            self.code_status.setText('Renderizando al terminar de escribir…')
            self.code_status.setStyleSheet('color:#d8c27a')

    def _render_edited_code(self):
        self.render_code_scene(automatic=True)

    def _show_last_manim_error(self):
        if self._last_manim_error:
            self._show_manim_error(self._last_manim_error)

    def preview_state_changed(self):
        self._preview_sync_timer.start()

    def _timeline_state_changed(self):
        """Propaga cambios de clips a la vista, al código y al historial."""
        self._pending_timeline_sync=True
        timing_signature=self._timeline_timing_signature()
        timing_changed=timing_signature!=self._timeline_timing_snapshot
        self._timeline_timing_snapshot=timing_signature
        editable_preview=all(
            obj.get('kind')!='manim_scene' for obj in self.state.get('objects',[])
        )
        if timing_changed and editable_preview:
            # El fotograma guardado conserva los tiempos anteriores; mientras
            # Manim se actualiza, pinta los clips con sus tiempos nuevos.
            self._timeline_preview_override=True
            self.preview.set_rendered_frame(None)
        self._preview_sync_timer.start()
        self.update_views()
        self.seek(float(self.timeline.position))

    def _timeline_timing_signature(self):
        return tuple(
            (obj.get('manim_variable'),obj.get('name'),
             round(float(obj.get('start',0)),4),round(float(obj.get('duration',0)),4))
            for obj in self.state.get('objects',[])
        )

    def _sync_preview_changes(self):
        timeline_sync=self._pending_timeline_sync
        self._pending_timeline_sync=False
        source=(
            self.code_view.toPlainText()
            if timeline_sync and self._code_user_editing
            else self.state.get('manim_source')
        )
        if source and (timeline_sync or not self._code_user_editing):
            # Los cambios de tiempo se aplican al texto actual, incluso si el
            # usuario tiene ediciones pendientes de renderizar.
            updated_source=self._sync_manim_source_from_preview(source,self.state.get('objects',[]))
            if updated_source and updated_source!=source:
                self._pending_preview_seek=float(self.timeline.position)
                self.state['manim_source']=updated_source
                self._updating_code_view=True
                self.code_view.setPlainText(updated_source)
                self._updating_code_view=False
                self._code_view_dirty=True
                self._render_generation+=1
                self._auto_render_pending=True
                self._code_render_timer.start(700)
                self.code_status.setText('Cambios de la previsualización aplicados al código; preparando el render…')
                self.code_status.setStyleSheet('color:#d8c27a')
        elif not source and not self._code_view_dirty:
            # La escena creada desde el lienzo también se refleja en el código
            # aunque el proyecto aún no tenga una fuente Manim guardada.
            self.refresh_code_view()
        self.update_views()

    def _sync_manim_source_from_preview(self, source, preview_objects):
        """Actualiza solo las asignaciones de Mobject reconocidas en construct()."""
        if any(obj.get('kind') == 'graph' for obj in preview_objects):
            source = self._ensure_numpy_import(source)
        try:
            tree=ast.parse(source)
            baseline,_duration=self._parse_manim_scene(source)
        except (SyntaxError,TypeError,ValueError):
            return source
        baseline_by_variable={
            obj.get('manim_variable'):obj for obj in baseline if obj.get('manim_variable')
        }
        construct=next(
            (node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='construct'),
            None,
        )
        if construct is None:
            return source
        assignments={}
        for statement in construct.body:
            if isinstance(statement,ast.Assign):
                targets=statement.targets
            elif isinstance(statement,ast.AnnAssign):
                targets=[statement.target]
            else:
                continue
            for target in targets:
                if isinstance(target,ast.Name):
                    assignments[target.id]=statement.value

        source_bytes=source.encode('utf-8')
        line_offsets=[]
        offset=0
        for line in source.splitlines(keepends=True):
            line_offsets.append(offset)
            offset+=len(line.encode('utf-8'))
        replacements=[]
        for obj in preview_objects:
            variable=obj.get('manim_variable')
            original=baseline_by_variable.get(variable)
            value_node=assignments.get(variable)
            if original is None or value_node is None:
                continue
            position_changed=any(
                abs(float(obj.get('position',{}).get(axis,0.5))-float(original.get('position',{}).get(axis,0.5)))>0.0005
                for axis in ('x','y')
            )
            is_text=obj.get('kind')=='text'
            scale_changed=(
                int(obj.get('font_size',48))!=int(original.get('font_size',48))
                if is_text else
                abs(float(obj.get('scale',1.0))-float(original.get('scale',1.0)))>0.001
            )
            rotation_changed=abs(float(obj.get('rotation',0.0))-float(original.get('rotation',0.0)))>0.1
            color_changed=str(obj.get('color','#65d6ff')).lower()!=str(original.get('color','#65d6ff')).lower()
            visibility_changed=bool(obj.get('visible',True))!=bool(original.get('visible',True))
            expression_changed=(obj.get('kind') in {'graph','text','table'} and str(obj.get('expression',''))!=str(original.get('expression','')))
            graph_options_changed=(obj.get('kind')=='graph' and any(
                obj.get(key,True)!=original.get(key,True) for key in ('show_grid','show_axes')
            ))
            if expression_changed or graph_options_changed or (obj.get('kind')=='graph' and color_changed):
                expression=self._preview_object_expression(obj)
                if expression:
                    start=line_offsets[value_node.lineno-1]+value_node.col_offset
                    end=line_offsets[value_node.end_lineno-1]+value_node.end_col_offset
                    replacements.append((start,end,expression.encode('utf-8')))
                continue
            if not (position_changed or scale_changed or rotation_changed or color_changed or visibility_changed):
                continue

            base_node=value_node
            while (
                isinstance(base_node,ast.Call)
                and isinstance(base_node.func,ast.Attribute)
                and base_node.func.attr in {'move_to','scale','rotate','set_color','set_opacity'}
            ):
                base_node=base_node.func.value
            base_expression=ast.get_source_segment(source,base_node)
            if not base_expression:
                continue

            transform_expressions=original.get('manim_transform_expressions',[])
            expression=base_expression
            for method in ('move_to','scale','rotate','set_color','set_opacity'):
                if method=='move_to' and position_changed:
                    frame_width=14.222
                    width=max(1,int(self.state.get('width',1920)))
                    height=max(1,int(self.state.get('height',1080)))
                    frame_height=frame_width*height/width
                    position=obj.get('position',{'x':0.5,'y':0.5})
                    x=float(position.get('x',0.5))
                    y=float(position.get('y',0.5))
                    if is_text:
                        font=QFont(obj.get('font_family',MANIM_TEXT_FONT),int(obj.get('font_size',48)))
                        metrics=QFontMetricsF(font)
                        x+=metrics.horizontalAdvance(str(obj.get('expression','')))/2000
                        y+=metrics.height()/(2*1000*height/width)
                    scene_x=(x-0.5)*frame_width
                    scene_y=(0.5-y)*frame_height
                    expression+=f'.move_to([{scene_x:.6f}, {scene_y:.6f}, 0])'
                elif method=='scale' and scale_changed:
                    if is_text:
                        base_keywords={item.arg:item.value for item in base_node.keywords if item.arg}
                        base_size=int(self._code_literal(base_keywords.get('font_size'),48))
                        scale=float(obj.get('font_size',base_size))/max(1,base_size)
                    else:
                        scale=float(obj.get('scale',1.0))
                    if abs(scale-1.0)>0.001:
                        expression+=f'.scale({scale:.6f})'
                elif method=='rotate' and rotation_changed:
                    rotation=float(obj.get('rotation',0.0))
                    if abs(rotation)>0.1:
                        expression+=f'.rotate({rotation:.6f} * DEGREES)'
                elif method=='set_color' and color_changed:
                    expression+=f'.set_color({json.dumps(str(obj.get("color","#65d6ff")))})'
                elif method=='set_opacity' and visibility_changed:
                    expression+=f'.set_opacity({1 if obj.get("visible",True) else 0})'
                else:
                    expression+=''.join(
                        f'.{existing_method}({argument})'
                        for existing_method,argument in transform_expressions
                        if existing_method==method
                    )

            start=line_offsets[value_node.lineno-1]+value_node.col_offset
            end=line_offsets[value_node.end_lineno-1]+value_node.end_col_offset
            replacements.append((start,end,expression.encode('utf-8')))

        for start,end,replacement in sorted(replacements,reverse=True):
            source_bytes=source_bytes[:start]+replacement+source_bytes[end:]
        updated_source=source_bytes.decode('utf-8')
        for obj in preview_objects:
            if obj.get('manim_variable') or obj.get('kind')=='manim_scene':
                continue
            variable=self._next_preview_variable(updated_source)
            expression=self._preview_object_expression(obj)
            if not expression:
                continue
            source_before_insert=updated_source
            updated_source,actual_start=self._insert_preview_object(
                updated_source,variable,expression,float(obj.get('start',0.0)),float(obj.get('duration',1.0)),
                obj.get('animation','None'),float(obj.get('animation_duration',1.0)),
            )
            if (
                updated_source != source_before_insert
                and re.search(rf'\b{re.escape(variable)}\s*=',updated_source)
            ):
                obj['manim_variable']=variable
                obj['start']=actual_start
                self._pending_preview_seek=actual_start
        updated_source=self._sync_object_metadata(updated_source,preview_objects)
        return self._sync_simple_timeline_to_code(updated_source,preview_objects)

    @staticmethod
    def _sync_object_metadata(source, objects):
        """Guarda nombre y color del clip en comentarios legibles por el editor."""
        source_lines=[line for line in source.splitlines() if not line.lstrip().startswith('# manim-editor-object:')]
        metadata=[]
        for obj in objects:
            variable=obj.get('manim_variable')
            if not variable or obj.get('kind')=='manim_scene':
                continue
            record={'variable':variable,'name':obj.get('name',variable),
                    'clip_color':obj.get('clip_color',obj.get('color','#65d6ff')),
                    'track':obj.get('track','Pista 1')}
            metadata.append('# manim-editor-object: '+json.dumps(record,ensure_ascii=False))
        if metadata:
            source_lines.extend(['', *metadata])
        return '\n'.join(source_lines).rstrip()+'\n'

    def _sync_simple_timeline_to_code(self,source,preview_objects):
        """Reescribe esperas y animaciones sencillas usando los tiempos del timeline."""
        variables={
            obj.get('manim_variable'):obj
            for obj in preview_objects
            if obj.get('manim_variable') and obj.get('kind')!='manim_scene'
        }
        if not variables:
            return source
        try:
            tree=ast.parse(source)
            parsed_objects,_duration=self._parse_manim_scene(source)
        except (SyntaxError,TypeError,ValueError):
            return source
        code_times={
            obj.get('manim_variable'):obj
            for obj in parsed_objects if obj.get('manim_variable')
        }
        timing_changed=any(
            variable not in code_times
            or abs(float(obj.get('start',0))-float(code_times[variable].get('start',0)))>0.01
            or abs(float(obj.get('duration',0))-float(code_times[variable].get('duration',0)))>0.01
            or obj.get('animation','None')!=code_times[variable].get('animation','None')
            for variable,obj in variables.items()
        )
        if not timing_changed:
            return source
        construct=next(
            (node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='construct'),
            None,
        )
        if construct is None:
            return source

        timing_nodes=[]
        for statement in construct.body:
            if not isinstance(statement,ast.Expr) or not isinstance(statement.value,ast.Call):
                continue
            call=statement.value
            if not isinstance(call.func,ast.Attribute) or not isinstance(call.func.value,ast.Name) or call.func.value.id!='self':
                continue
            action=call.func.attr
            if action in {'wait','add','remove','play'}:
                timing_nodes.append(statement)
            elif timing_nodes:
                # Una llamada de escena intercalada con el timeline puede tener
                # efectos laterales; en ese caso no movemos los bloques de código.
                return source
        if not timing_nodes:
            return source

        first_timing=min(node.lineno for node in timing_nodes)
        if any(
            statement.lineno>=first_timing
            and statement not in timing_nodes
            and not isinstance(statement,ast.Pass)
            for statement in construct.body
        ):
            # Solo reconstruye la cola temporal cuando las definiciones de
            # objetos ya están completas antes de la primera acción.
            return source

        events=[]
        intro_names=set()
        ending_names=set()
        current_time=0.0
        animation_order=0
        for statement in timing_nodes:
            call=statement.value
            action=call.func.attr
            if action=='wait':
                current_time+=max(0.0,float(self._code_literal(call.args[0],1.0))) if call.args else 1.0
                continue
            if action in {'add','remove'}:
                # La adición/eliminación se reconstruye a partir de cada clip.
                referenced={
                    node.id for argument in call.args for node in ast.walk(argument)
                    if isinstance(node,ast.Name) and node.id in variables
                }
                if action=='add':
                    for variable in referenced:
                        obj=variables[variable]
                        animation=obj.get('animation','None')
                        if animation not in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}:
                            continue
                        run_time=max(0.1,min(float(obj.get('animation_duration',1.0)),float(obj.get('duration',1.0))))
                        start=max(0.0,float(obj.get('start',current_time)))
                        events.append((start,2,animation_order,
                                       f'self.play({animation}({variable}), run_time={run_time:.3f})',
                                       run_time,{variable},{variable},set()))
                        animation_order+=1
                        intro_names.add(variable)
                if not referenced:
                    events.append((current_time,1 if action=='add' else 0,animation_order,
                                   ast.unparse(call),0.0,set(),set(),set()))
                    animation_order+=1
                else:
                    untracked_args=[
                        ast.unparse(argument) for argument in call.args
                        if not any(
                            isinstance(node,ast.Name) and node.id in variables
                            for node in ast.walk(argument)
                        )
                    ]
                    if untracked_args:
                        events.append((current_time,1 if action=='add' else 0,animation_order,
                                       f'self.{action}({", ".join(untracked_args)})',0.0,set(),set(),set()))
                        animation_order+=1
                continue

            run_time=max(0.01,float(next(
                (self._code_literal(item.value,1.0) for item in call.keywords if item.arg=='run_time'),
                1.0,
            )))
            referenced={
                node.id for argument in call.args for node in ast.walk(argument)
                if isinstance(node,ast.Name) and node.id in variables
            }
            if not referenced:
                events.append((current_time,2,animation_order,ast.unparse(call),run_time,set(),set(),set()))
                animation_order+=1
                current_time+=run_time
                continue
            desired_starts=[]
            local_intro=set()
            local_ending=set()
            for argument in call.args:
                for animation_node in ast.walk(argument):
                    if not isinstance(animation_node,ast.Call):
                        continue
                    animation_name=self._manim_call_name(animation_node)
                    anim_variables={
                        node.id for node in ast.walk(animation_node)
                        if isinstance(node,ast.Name) and node.id in variables
                    }
                    if animation_name in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}:
                        local_intro.update(anim_variables)
                    if animation_name in {'FadeOut','Uncreate','Unwrite'}:
                        local_ending.update(anim_variables)
            for variable in referenced:
                obj=variables[variable]
                old=code_times.get(variable,{'start':current_time})
                start=max(0.0,float(obj.get('start',0)))
                end=start+max(0.1,float(obj.get('duration',0.1)))
                if referenced.issubset(local_ending) and variable in local_ending:
                    desired_starts.append(max(start,end-run_time))
                else:
                    offset=max(0.0,current_time-float(old.get('start',current_time)))
                    desired_starts.append(start+offset)
            if max(desired_starts)-min(desired_starts)>0.01:
                # Un play agrupado no se puede separar sin cambiar su animación.
                return source
            target_start=desired_starts[0]
            if not all(obj.get('visible',True) for variable,obj in variables.items() if variable in referenced):
                return source
            call_text=ast.unparse(call)
            if len(referenced)==1:
                variable=next(iter(referenced))
                desired=variables[variable].get('animation','None')
                previous=code_times.get(variable,{}).get('animation','None')
                if desired!=previous and previous in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}:
                    if desired in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}:
                        call_text=re.sub(
                            rf'\b{re.escape(previous)}\s*\(\s*{re.escape(variable)}\s*\)',
                            f'{desired}({variable})',call_text,count=1,
                        )
                    elif previous+'(' in call_text:
                        call_text=f'self.add({variable})'
                        run_time=0.0
                        local_intro.discard(variable)
                        local_ending.discard(variable)
                        intro_names.discard(variable)
                        ending_names.discard(variable)
            events.append((target_start,2,animation_order,call_text,run_time,referenced,local_intro,local_ending))
            animation_order+=1
            intro_names.update(local_intro)
            ending_names.update(local_ending)
            current_time+=run_time

        total_duration=max(0.1,float(self.state.get('duration',1)))
        for variable,obj in variables.items():
            if not obj.get('visible',True):
                continue
            start=max(0.0,float(obj.get('start',0)))
            end=start+max(0.1,float(obj.get('duration',0.1)))
            total_duration=max(total_duration,end)
            if variable not in intro_names:
                events.append((start,1,animation_order,f'self.add({variable})',0.0,{variable},set(),set()))
                animation_order+=1
            if variable not in ending_names:
                events.append((end,0,animation_order,f'self.remove({variable})',0.0,{variable},set(),set()))
                animation_order+=1

        events.sort(key=lambda event:(event[0],event[1],event[2]))

        indent=' '*(construct.col_offset+4)
        schedule=[]
        schedule_time=0.0
        for event_time,_priority,_order,statement,run_time,_names,_intro,_ending in events:
            if event_time<schedule_time-0.01:
                # Las animaciones Manim son secuenciales en construct(); no
                # podemos solapar dos plays cambiando solo sus tiempos.
                return source
            if event_time>schedule_time:
                schedule.append(f'{indent}self.wait({event_time-schedule_time:.3f})\n')
            schedule.append(f'{indent}{statement}\n')
            schedule_time=event_time+run_time
        if total_duration>schedule_time:
            schedule.append(f'{indent}self.wait({total_duration-schedule_time:.3f})\n')

        lines=source.splitlines(keepends=True)
        first_timing_line=min(node.lineno-1 for node in timing_nodes)
        timing_lines={
            line for node in timing_nodes for line in range(node.lineno-1,node.end_lineno)
        }
        rewritten=[]
        inserted=False
        for index,line in enumerate(lines):
            if index==first_timing_line and not inserted:
                rewritten.extend(schedule)
                inserted=True
            if index not in timing_lines:
                rewritten.append(line)
        if not inserted:
            return source
        return ''.join(rewritten)

    @staticmethod
    def _next_preview_variable(source):
        names=set(re.findall(r'\bpreview_obj_(\d+)\b',source))
        index=1
        while str(index) in names:
            index+=1
        return f'preview_obj_{index}'

    def _preview_object_expression(self,obj):
        """Forma una expresión Manim para un objeto creado desde la previsualización."""
        kind=obj.get('kind')
        color=json.dumps(str(obj.get('color','#65d6ff')))
        expression=str(obj.get('expression',''))
        if kind=='graph':
            try:
                graph_expression=self._function_expression_to_numpy(expression)
            except (SyntaxError,ValueError,TypeError):
                return None
            width=max(1,int(self.state.get('width',1920)))
            height=max(1,int(self.state.get('height',1080)))
            frame_width=14.222
            frame_height=frame_width*height/width
            axes=(
                'Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], '
                f'x_length={frame_width:.6f}, y_length={frame_height:.6f}, tips=False)'
            )
            components=[]
            if obj.get('show_grid',True):
                components.append(
                    'NumberPlane(x_range=[-7, 7, 2], y_range=[-4, 4, 2], '
                    f'x_length={frame_width:.6f}, y_length={frame_height:.6f}, '
                    'axis_config={"stroke_opacity": 0}, '
                    'background_line_style={"stroke_color": "#586273", "stroke_opacity": 0.35})'
                )
            if obj.get('show_axes',True):
                components.append(axes)
            components.append(f'{axes}.plot(lambda x: {graph_expression}, x_range=[-7, 7], color={color})')
            base=f'VGroup({", ".join(components)})' if len(components)>1 else components[0]
        elif kind=='text':
            weight='BOLD' if int(obj.get('font_weight',400))>=700 else 'NORMAL'
            base=(
                f'Text({json.dumps(expression,ensure_ascii=False)}, '
                f'font={json.dumps(str(obj.get("font_family",MANIM_TEXT_FONT)))}, '
                f'font_size={int(obj.get("font_size",48))}, weight={json.dumps(weight)}, color={color})'
            )
        elif kind=='axes':
            base=f'Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], tips=False).set_color({color})'
        elif kind=='point':
            base=f'Dot(color={color})'
        elif kind=='line':
            base=f'Line(LEFT, RIGHT, color={color})'
        elif kind=='vector':
            base=f'Arrow(ORIGIN, RIGHT, color={color})'
        elif kind=='arrow':
            base=f'Arrow(LEFT, RIGHT, color={color})'
        elif kind=='circle':
            base=f'Circle(color={color})'
        elif kind=='ellipse':
            base=f'Ellipse(width=2, height=1, color={color})'
        elif kind=='polygon':
            base=f'Polygon(LEFT, UP, RIGHT, color={color})'
        elif kind=='table':
            base=f'Table([[{json.dumps(expression,ensure_ascii=False)}]], include_outer_lines=True).set_color({color})'
        else:
            return None

        position=obj.get('position',{'x':0.5,'y':0.5})
        x=float(position.get('x',0.5))
        y=float(position.get('y',0.5))
        width=max(1,int(self.state.get('width',1920)))
        height=max(1,int(self.state.get('height',1080)))
        frame_width=14.222
        frame_height=frame_width*height/width
        if kind=='text':
            font=QFont(obj.get('font_family',MANIM_TEXT_FONT),int(obj.get('font_size',48)))
            metrics=QFontMetricsF(font)
            x+=metrics.horizontalAdvance(expression)/2000
            y+=metrics.height()/(2*1000*height/width)
        scene_x=(x-0.5)*frame_width
        scene_y=(0.5-y)*frame_height
        result=f'{base}.move_to([{scene_x:.6f}, {scene_y:.6f}, 0])'
        if not obj.get('visible',True):
            result+='.set_opacity(0)'
        if kind!='text' and abs(float(obj.get('scale',1.0))-1.0)>0.001:
            result+=f'.scale({float(obj["scale"]):.6f})'
        rotation=float(obj.get('rotation',0.0))
        if abs(rotation)>0.1:
            result+=f'.rotate({rotation:.6f} * DEGREES)'
        return result

    @staticmethod
    def _function_expression_to_numpy(expression):
        """Convierte una fórmula de f(x) en una expresión vectorizada para Manim."""
        tree=ast.parse(str(expression).strip().replace('^','**'),mode='eval')
        functions={
            'sin','cos','tan','asin','acos','atan','sinh','cosh','tanh',
            'sqrt','abs','exp','log','log10','floor','ceil','min','max',
        }
        constants={'pi':'np.pi','e':'np.e','tau':'(2 * np.pi)'}

        class Translator(ast.NodeTransformer):
            def visit_Name(self,node):
                if node.id in constants:
                    return ast.copy_location(ast.parse(constants[node.id],mode='eval').body,node)
                if node.id in functions:
                    numpy_name={'min':'minimum','max':'maximum'}.get(node.id,node.id)
                    return ast.copy_location(
                        ast.Attribute(value=ast.Name(id='np',ctx=ast.Load()),attr=numpy_name,ctx=ast.Load()),node
                    )
                if node.id!='x':
                    raise ValueError(f'Nombre no permitido en la función: {node.id}')
                return node

            def visit_Call(self,node):
                if not isinstance(node.func,ast.Name) or node.func.id not in functions:
                    raise ValueError('Solo se permiten funciones matemáticas conocidas.')
                expected={
                    'min':2,'max':2,'log':(1,2),
                }.get(node.func.id,1)
                if isinstance(expected,tuple):
                    if len(node.args) not in expected:
                        raise ValueError('Número de argumentos incorrecto.')
                elif len(node.args)!=expected:
                    raise ValueError('Número de argumentos incorrecto.')
                if node.keywords:
                    raise ValueError('No se permiten argumentos con nombre.')
                if node.func.id=='log' and len(node.args)==2:
                    numerator=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='np',ctx=ast.Load()),attr='log',ctx=ast.Load()),
                        args=[self.visit(node.args[0])],keywords=[],
                    )
                    denominator=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='np',ctx=ast.Load()),attr='log',ctx=ast.Load()),
                        args=[self.visit(node.args[1])],keywords=[],
                    )
                    return ast.copy_location(ast.BinOp(left=numerator,op=ast.Div(),right=denominator),node)
                return self.generic_visit(node)

            def visit_Attribute(self,node):
                raise ValueError('No se permiten atributos en la función.')

        translated=Translator().visit(tree)
        return ast.unparse(ast.fix_missing_locations(translated))

    @staticmethod
    def _ensure_numpy_import(source):
        """Asegura el alias np que requieren las gráficas vectorizadas."""
        try:
            tree=ast.parse(source)
        except SyntaxError:
            return source
        if any(
            isinstance(node,ast.Import)
            and any(alias.name=='numpy' and alias.asname=='np' for alias in node.names)
            for node in tree.body
        ):
            return source
        insertion_line=0
        if tree.body and isinstance(tree.body[0],ast.Expr) and isinstance(tree.body[0].value,ast.Constant) and isinstance(tree.body[0].value.value,str):
            insertion_line=tree.body[0].end_lineno
        future_lines=[node.end_lineno for node in tree.body if isinstance(node,ast.ImportFrom) and node.module=='__future__']
        if future_lines:
            insertion_line=max(insertion_line,max(future_lines))
        lines=source.splitlines(keepends=True)
        lines.insert(insertion_line,'import numpy as np\n')
        return ''.join(lines)

    def _insert_preview_object(self,source,variable,expression,start,duration,animation='None',animation_duration=1.0):
        """Inserta el objeto en construct() cerca del instante elegido en la línea de tiempo."""
        try:
            tree=ast.parse(source)
        except SyntaxError:
            return source,start
        construct=next(
            (node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='construct'),
            None,
        )
        if construct is None:
            return source,start
        indent=' '*(construct.col_offset+4)
        block=[f'{indent}{variable} = {expression}']
        if animation in {'Create','FadeIn','Write','GrowFromCenter'}:
            run_time=max(0.1,min(float(animation_duration),max(0.1,float(duration))))
            block.append(f'{indent}self.play({animation}({variable}), run_time={run_time:.3f})')
        else:
            block.append(f'{indent}self.add({variable})')
        target=max(0.0,start)
        current=0.0
        insertion_index=construct.end_lineno
        actual_start=current
        timed_actions={'wait','play'}
        for statement in construct.body:
            if isinstance(statement,ast.Return):
                insertion_index=statement.lineno-1
                actual_start=current
                break
            if not isinstance(statement,ast.Expr) or not isinstance(statement.value,ast.Call):
                continue
            call=statement.value
            if not isinstance(call.func,ast.Attribute) or not isinstance(call.func.value,ast.Name) or call.func.value.id!='self':
                continue
            action=call.func.attr
            if action in {'add','remove'} and target<=current+0.0001:
                insertion_index=statement.lineno-1
                actual_start=current
                break
            if action not in timed_actions:
                continue
            elapsed=(
                max(0.0,float(self._code_literal(call.args[0],1.0)))
                if action=='wait' and call.args else
                max(0.0,float(next((self._code_literal(item.value,1.0) for item in call.keywords if item.arg=='run_time'),1.0)))
                if action=='play' else 1.0
            )
            if target<=current+0.0001:
                insertion_index=statement.lineno-1
                actual_start=current
                break
            if target<current+elapsed:
                # Insertar al cerrar una animación evita dividir su secuencia.
                insertion_index=statement.end_lineno
                actual_start=current+elapsed
                break
            current+=elapsed
            actual_start=current

        lines=source.splitlines(keepends=True)
        future_timing=False
        for statement in construct.body:
            if statement.lineno-1<insertion_index:
                continue
            if isinstance(statement,ast.Expr) and isinstance(statement.value,ast.Call):
                call=statement.value
                if isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id=='self' and call.func.attr in timed_actions:
                    future_timing=True
                    break
        if not future_timing:
            block.append(f'{indent}self.wait({max(0.1,min(1.0,duration)):.3f})')
        block_text='\n'.join(block)+'\n'
        if insertion_index>0 and insertion_index<=len(lines) and not lines[insertion_index-1].endswith(('\n','\r')):
            lines[insertion_index-1]+='\n'
        lines.insert(insertion_index,block_text)
        return ''.join(lines),actual_start

    # Lectura segura de las construcciones de Manim que soporta el editor.
    @staticmethod
    def _code_literal(node, default=None):
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            return default

    @staticmethod
    def _manim_call_name(node):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                return function.id
            if isinstance(function, ast.Attribute):
                return function.attr
        return ''

    def _read_manim_object(self, node, variable):
        transforms=[]
        while (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {'move_to', 'scale', 'set_color', 'set_opacity', 'rotate'}
        ):
            transforms.append(node)
            node=node.func.value

        call_name=self._manim_call_name(node)
        if not isinstance(node, ast.Call):
            return None
        nested_plot=next(
            (item for item in ast.walk(node)
             if isinstance(item,ast.Call) and self._manim_call_name(item)=='plot'),
            None,
        )
        nested_names={
            self._manim_call_name(item)
            for item in ast.walk(node) if isinstance(item,ast.Call)
        }
        keywords={item.arg:item.value for item in node.keywords if item.arg}
        args=node.args
        color_names={
            'WHITE':'#FFFFFF','BLACK':'#000000','RED':'#FC6255','MAROON':'#C55AAB',
            'YELLOW':'#FFFF00','GOLD':'#F0AC5F','GREEN':'#83C167','TEAL':'#5CD0B3',
            'BLUE':'#58C4DD','PURPLE':'#9A72AC','PINK':'#D147BD','ORANGE':'#FF862F',
            'GREY':'#888888','GRAY':'#888888',
        }
        color_node=keywords.get('color')
        color=self._code_literal(color_node, color_names.get(getattr(color_node,'id',''), '#65d6ff'))
        expression=''
        kind=None
        obj={'name':variable.replace('_',' ').title(),'kind':'','expression':'','color':color,'clip_color':color,'animation':'None',
             'start':0,'duration':1,'visible':True,'track':'Pista 1','position':{'x':0.52,'y':0.54},'scale':1.0,
             'manim_variable':variable}

        if call_name in {'Text','MathTex','Tex'}:
            kind='equation' if call_name in {'MathTex', 'Tex'} else 'text'
            expression=self._code_literal(args[0], '') if args else ''
            obj['position']={'x':0.5,'y':0.5}
            obj.update(
                name=str(expression)[:24] or obj['name'],
                font_family=(MANIM_MATH_FONT if kind == 'equation' else
                             self._code_literal(keywords.get('font'), MANIM_TEXT_FONT)),
                font_size=int(self._code_literal(keywords.get('font_size'), 48)),
                font_weight=700 if self._code_literal(keywords.get('weight'), 'NORMAL') == 'BOLD' else 400,
            )
        elif call_name=='Axes':
            kind='axes'
        elif call_name=='plot' or nested_plot is not None:
            kind='graph'
            plot_call=node if call_name=='plot' else nested_plot
            if plot_call.args and isinstance(plot_call.args[0],ast.Lambda):
                expression=self._numpy_expression_to_function(plot_call.args[0].body)
            plot_color=next((item.value for item in plot_call.keywords if item.arg=='color'),None)
            if plot_color is not None:
                obj['color']=self._code_literal(
                    plot_color,color_names.get(getattr(plot_color,'id',''),obj['color'])
                )
            obj['show_grid']='NumberPlane' in nested_names
            plot_base=plot_call.func.value if isinstance(plot_call.func,ast.Attribute) else None
            plot_base_ids={id(item) for item in ast.walk(plot_base)} if plot_base is not None else set()
            obj['show_axes']=any(
                isinstance(item,ast.Call)
                and self._manim_call_name(item)=='Axes'
                and id(item) not in plot_base_ids
                for item in ast.walk(node)
            )
        else:
            kind={
                'Dot':'point','Arrow':'arrow','Line':'line','Circle':'circle',
                'Ellipse':'ellipse','Polygon':'polygon','Table':'table','MathTable':'table','VGroup':'group',
            }.get(call_name)
        if kind is None:
            return None
        obj['kind']=kind
        obj['expression']=str(expression)
        if kind=='table' and args:
            table_data=self._code_literal(args[0],[])
            if table_data and isinstance(table_data[0],(list,tuple)) and table_data[0]:
                obj['expression']=str(table_data[0][0])

        point_node=keywords.get('point')
        if kind=='point' and point_node is not None:
            point=self._code_literal(point_node)
            if isinstance(point,(list,tuple)) and len(point)>=2:
                frame_width=14.222
                frame_height=frame_width*max(1,int(self.state.get('height',1080)))/max(1,int(self.state.get('width',1920)))
                obj['position']={'x':max(0,min(1,float(point[0])/frame_width+0.5)), 'y':max(0,min(1,0.5-float(point[1])/frame_height))}

        opacity=1.0
        for transform in reversed(transforms):
            method=transform.func.attr
            value=transform.args[0] if transform.args else None
            if method=='set_color':
                color_node=value
                obj['color']=self._code_literal(value, color_names.get(getattr(value,'id',''),obj['color']))
            elif method=='scale':
                obj['scale']=float(self._code_literal(value, 1.0))
            elif method=='rotate':
                if (
                    isinstance(value, ast.BinOp)
                    and isinstance(value.op, ast.Mult)
                    and isinstance(value.right, ast.Name)
                    and value.right.id == 'DEGREES'
                ):
                    obj['rotation']=float(self._code_literal(value.left, 0.0))
                else:
                    angle=self._code_literal(value)
                    if isinstance(angle,(int,float)):
                        obj['rotation']=math.degrees(float(angle))
            elif method=='set_opacity':
                opacity=float(self._code_literal(value,1.0))
            elif method=='move_to':
                point=self._code_literal(value)
                if isinstance(point, (list, tuple)) and len(point)>=2:
                    x,y=float(point[0]),float(point[1])
                elif isinstance(value, ast.Name):
                    x,y={'ORIGIN':(0,0),'UP':(0,1),'DOWN':(0,-1),'LEFT':(-1,0),'RIGHT':(1,0)}.get(value.id,(0,0))
                else:
                    x,y=0,0
                frame_width=14.222
                frame_height=frame_width*max(1,int(self.state.get('height',1080)))/max(1,int(self.state.get('width',1920)))
                obj['position']={'x':max(0,min(1,x/frame_width+0.5)), 'y':max(0,min(1,0.5-y/frame_height))}
        obj['manim_transform_expressions']=[
            (transform.func.attr,ast.unparse(transform.args[0]))
            for transform in reversed(transforms)
            if transform.args
        ]
        obj['visible']=opacity>0.001
        if color_node is not None:
            obj['manim_color_expression']=ast.unparse(color_node)
        if kind in {'text', 'equation'} and call_name in {'Text','MathTex','Tex'}:
            base_font_size=int(self._code_literal(keywords.get('font_size'),48))
            obj['font_size']=max(8,round(base_font_size*obj.get('scale',1.0)))
            obj['scale']=1.0
            font=QFont(
                obj.get('font_family', MANIM_MATH_FONT if kind == 'equation' else MANIM_TEXT_FONT),
                obj['font_size'],
                QFont.Weight(obj.get('font_weight',400)),
            )
            metrics=QFontMetricsF(font)
            center=obj['position']
            frame_width=1000.0
            frame_height=frame_width*max(1,int(self.state.get('height',1080)))/max(1,int(self.state.get('width',1920)))
            obj['position']={
                'x':center['x']-metrics.horizontalAdvance(obj['expression'])/(2*frame_width),
                'y':center['y']-metrics.height()/(2*frame_height),
            }
        return obj

    @staticmethod
    def _numpy_expression_to_function(node):
        """Recupera la sintaxis f(x) desde el cuerpo de una lambda generada."""
        class Translator(ast.NodeTransformer):
            numpy_names={'minimum':'min','maximum':'max'}

            def visit_Attribute(self,attribute):
                if isinstance(attribute.value,ast.Name) and attribute.value.id in {'np','numpy'}:
                    name=self.numpy_names.get(attribute.attr,attribute.attr)
                    if name=='pi':
                        return ast.copy_location(ast.Name(id='pi',ctx=ast.Load()),attribute)
                    if name=='e':
                        return ast.copy_location(ast.Name(id='e',ctx=ast.Load()),attribute)
                    if name in {
                        'sin','cos','tan','asin','acos','atan','sinh','cosh','tanh',
                        'sqrt','abs','exp','log','log10','floor','ceil','min','max',
                    }:
                        return ast.copy_location(ast.Name(id=name,ctx=ast.Load()),attribute)
                return self.generic_visit(attribute)

        translated=Translator().visit(node)
        try:
            return ast.unparse(ast.fix_missing_locations(translated))
        except (TypeError,ValueError):
            return 'sin(x)'

    # Convierte asignaciones y animaciones reconocidas en objetos del timeline.
    def _parse_manim_scene(self, source):
        tree=ast.parse(source)
        construct=next(
            (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name=='construct'),
            None,
        )
        if construct is None:
            raise ValueError('No se encontró el método construct(self) de la escena.')

        objects={}
        current_objects=self.state.get('objects',[])
        tracks_by_variable={
            obj.get('manim_variable'):obj.get('track','Pista 1')
            for obj in current_objects if obj.get('manim_variable')
        }
        tracks_by_variable.update({
            f'obj_{index + 1}':obj.get('track','Pista 1')
            for index,obj in enumerate(current_objects)
        })
        tracks_by_name={
            obj.get('name'):obj.get('track','Pista 1')
            for obj in current_objects if obj.get('name')
        }
        tracks=self.state.setdefault('tracks',['Pista 1'])
        used_tracks={obj.get('track') for obj in current_objects if obj.get('track')}

        def track_for(variable, obj):
            previous=tracks_by_variable.get(variable,tracks_by_name.get(obj.get('name')))
            if previous:
                used_tracks.add(previous)
                return previous
            available=next((track for track in reversed(tracks) if track not in used_tracks),None)
            if available is None:
                number=1
                while f'Pista {number}' in tracks:
                    number+=1
                available=f'Pista {number}'
                tracks.append(available)
            used_tracks.add(available)
            return available
        for statement in construct.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            target=statement.targets[0] if isinstance(statement, ast.Assign) and statement.targets else getattr(statement,'target',None)
            value=statement.value
            if not isinstance(target, ast.Name) or target.id.startswith('graph_axes_'):
                continue
            parsed=self._read_manim_object(value,target.id)
            if parsed is not None:
                parsed['track']=track_for(target.id,parsed)
                objects[target.id]=parsed

        starts={}
        active={}
        timeline=[]
        current_time=0.0

        def names_in(node):
            return list(dict.fromkeys(item.id for item in ast.walk(node) if isinstance(item, ast.Name) and item.id in objects))

        def animation_names(node):
            return {
                item.func.id if isinstance(item.func, ast.Name) else item.func.attr
                for item in ast.walk(node)
                if isinstance(item, ast.Call)
                and isinstance(item.func, (ast.Name, ast.Attribute))
            }

        def animated_names(node, animation_types):
            return {
                name
                for item in ast.walk(node)
                if isinstance(item, ast.Call)
                and self._manim_call_name(item) in animation_types
                for name in names_in(item)
            }

        for statement in construct.body:
            if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                continue
            call=statement.value
            if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name) or call.func.value.id!='self':
                continue
            action=call.func.attr
            if action=='wait':
                current_time+=max(0.0,float(self._code_literal(call.args[0],1.0))) if call.args else 1.0
            elif action=='add':
                for argument in call.args:
                    for name in names_in(argument):
                        starts[name]=current_time
                        active[name]=True
            elif action=='remove':
                for argument in call.args:
                    for name in names_in(argument):
                        if name in active:
                            obj=objects[name]
                            obj['start']=starts.get(name,0.0)
                            obj['duration']=max(0.1,current_time-obj['start'])
                            timeline.append(obj)
                            active.pop(name,None)
            elif action=='play':
                run_time=next((float(self._code_literal(item.value,1.0)) for item in call.keywords if item.arg=='run_time'),1.0)
                for argument in call.args:
                    nested_animations=animation_names(argument)
                    ending_objects=animated_names(argument,{'FadeOut','Uncreate','Unwrite'})
                    intro_objects=animated_names(argument,{'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'})
                    has_succession='Succession' in nested_animations
                    for name in names_in(argument):
                        if name in ending_objects and (name not in intro_objects or has_succession):
                            if name in active:
                                obj=objects[name]
                                obj['start']=starts.get(name,0.0)
                                obj['duration']=max(0.1,current_time+run_time-obj['start'])
                                timeline.append(obj)
                                active.pop(name,None)
                        else:
                            intro_animation=next((
                                self._manim_call_name(item)
                                for item in ast.walk(argument)
                                if isinstance(item,ast.Call)
                                and self._manim_call_name(item) in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}
                                and name in names_in(item)
                            ),None)
                            if intro_animation:
                                objects[name]['animation']={
                                    'ShowCreation':'Create','GrowArrow':'GrowFromCenter',
                                }.get(intro_animation,intro_animation)
                            # Los plays posteriores animan el mismo Mobject; no
                            # deben cambiar el inicio de su clip en el timeline.
                            if name not in active:
                                starts[name]=current_time
                            active[name]=True
                current_time+=max(0.0,run_time)

        editor_metadata={}
        for line in source.splitlines():
            if not line.lstrip().startswith('# manim-editor-object:'):
                continue
            try:
                record=json.loads(line.split(':',1)[1].strip())
            except (ValueError,TypeError):
                continue
            editor_metadata[record.get('variable')]=record
        for obj in timeline:
            record=editor_metadata.get(obj.get('manim_variable'),{})
            if record.get('name'):
                obj['name']=str(record['name'])
            if record.get('clip_color'):
                obj['clip_color']=str(record['clip_color'])
            if record.get('track'):
                obj['track']=str(record['track'])
                if obj['track'] not in self.state.setdefault('tracks',['Pista 1']):
                    self.state['tracks'].append(obj['track'])
        total_duration=max(1.0,current_time)
        for name in active:
            obj=objects[name]
            obj['start']=starts.get(name,0.0)
            obj['duration']=max(0.1,total_duration-obj['start'])
            timeline.append(obj)
        return timeline,total_duration

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
            'border-radius:6px;padding:8px;font-family:monospace;font-size:12px;'
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
