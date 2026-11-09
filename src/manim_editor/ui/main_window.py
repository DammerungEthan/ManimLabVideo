"""Prototipo funcional de editor de escenas con persistencia JSON."""
import ast
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton, QSlider, QSpinBox, QSplitter,
    QVBoxLayout, QWidget, QLineEdit, QFormLayout, QCheckBox, QComboBox, QScrollBar,
    QProgressDialog, QToolButton, QPlainTextEdit, QTabBar, QStackedWidget,
)

from manim_editor.models.project import new_project
from manim_editor.services.project_io import load_project, save_project
from manim_editor.ui.preview import Preview
from manim_editor.ui.timeline import Timeline

class MainWindow(QMainWindow):
    """Ventana principal que coordina la interfaz y el estado del proyecto."""

    def __init__(self):
        super().__init__(); self.state=new_project(); self.path=None; self.playing=False
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
        timeline_row=QHBoxLayout(); self.timeline=Timeline(self.state, self.seek, self.update_views); self.timeline.set_transport_controls(self.play_btn, self.slider); timeline_row.addWidget(self.timeline,1)
        self.track_scroll=QScrollBar(Qt.Orientation.Vertical); self.track_scroll.valueChanged.connect(self.timeline.set_row_offset); self.track_scroll.setSingleStep(1); timeline_row.addWidget(self.track_scroll)
        self.timeline_area=QWidget(); self.timeline_area.setLayout(timeline_row)
        self.vertical_split=QSplitter(Qt.Orientation.Vertical); self.vertical_split.setChildrenCollapsible(False); self.vertical_split.addWidget(self.preview); self.vertical_split.addWidget(self.timeline_area); self.vertical_split.setStretchFactor(0,1); self.vertical_split.setSizes([560,190])
        zoom_row=QHBoxLayout(); add_track=QPushButton('+ Pista'); add_track.clicked.connect(self.add_track); zoom_row.addWidget(add_track); remove_track=QPushButton('− Pista'); remove_track.clicked.connect(self.remove_track); zoom_row.addWidget(remove_track); zoom_row.addWidget(QLabel('Zoom'))
        for label,factor in [('−',1.25),('+',0.8)]:
            button=QPushButton(label); button.clicked.connect(lambda _=False,f=factor:self.timeline.zoom(f)); zoom_row.addWidget(button)
        zoom_row.addStretch()
        transport=QHBoxLayout(); transport.addWidget(self.timecode); transport.addWidget(self.trim_button)
        self.timeline_scroll=QScrollBar(Qt.Orientation.Horizontal); self.timeline_scroll.valueChanged.connect(self.timeline.set_scroll_offset)

        video_page=QWidget(); video_layout=QVBoxLayout(video_page); video_layout.setContentsMargins(0,0,0,0)
        video_layout.addWidget(self.vertical_split,1); video_layout.addLayout(zoom_row); video_layout.addLayout(transport); video_layout.addWidget(self.timeline_scroll)
        code_page=QWidget(); code_layout=QVBoxLayout(code_page); code_layout.setContentsMargins(8,8,8,8)
        self._code_view_dirty=False; self._updating_code_view=False
        self.code_view=QPlainTextEdit(); self.code_view.setReadOnly(False); self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_view.textChanged.connect(self._mark_code_view_edited)
        self.code_view.setPlaceholderText('El código de Manim de esta escena aparecerá aquí.')
        self.code_view.setStyleSheet('QPlainTextEdit{background:#15171b;color:#d8dee9;border:1px solid #363a40;border-radius:6px;padding:10px;font-family:monospace;font-size:13px;selection-background-color:#365f8c}')
        self.code_status=QLabel('Edita el código para actualizar la previsualización.')
        code_layout.addWidget(self.code_status)
        code_layout.addWidget(self.code_view)
        self._code_sync_timer=QTimer(self); self._code_sync_timer.setSingleShot(True); self._code_sync_timer.setInterval(350); self._code_sync_timer.timeout.connect(self.apply_code_to_preview)
        self._applying_code=False
        self._preview_sync_timer=QTimer(self); self._preview_sync_timer.setSingleShot(True); self._preview_sync_timer.setInterval(100); self._preview_sync_timer.timeout.connect(self._sync_preview_changes)
        self.workspace_pages=QStackedWidget(); self.workspace_pages.addWidget(video_page); self.workspace_pages.addWidget(code_page)
        self.workspace_tab_bar.currentChanged.connect(self.workspace_pages.setCurrentIndex)
        center.addWidget(self.workspace_pages,1)
        self._update_timeline_scroll(); body.addLayout(center,1)
        # Inspector lateral: creación, selección y propiedades de elementos.
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
        # Apariencia global de la ventana y controles.
        self.setStyleSheet("QWidget#root{background:#111317;color:#e7e7e7;font-family:'Segoe UI',sans-serif} QFrame,QListWidget,QLineEdit,QSpinBox,QComboBox{border-radius:7px} QPushButton,QLineEdit,QSpinBox,QListWidget,QComboBox{background:#202226;color:#eee;border:1px solid #363a40;border-radius:7px;padding:5px} QPushButton:hover{background:#30343b} QSplitter::handle:vertical{background:#34363a;height:5px;border-radius:3px} QSplitter::handle:vertical:hover{background:#777} QScrollBar:vertical{background:transparent;width:8px;margin:0} QScrollBar::handle:vertical{background:#52565c;min-height:24px;border-radius:4px} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0} QScrollBar:horizontal{background:#1b1d21;height:8px} QScrollBar::handle:horizontal{background:#52565c;min-width:24px;border-radius:4px} QSlider::groove:horizontal{height:3px;background:#464646;border-radius:2px} QSlider::handle:horizontal{background:#f5bd32;width:11px;margin:-4px 0;border-radius:6px}")
        self.timer=QTimer(self); self.timer.setInterval(40); self.timer.timeout.connect(self.tick); self.set_format_control(); self.refresh_objects(); self.refresh_code_view()

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
    def add_selected_element(self):
        row=self.element_list.currentRow()
        if row<0: return
        definitions=[('Gráfica seno','graph','sin(x)','#65d6ff'),('Gráfica coseno','graph','cos(x)','#65d6ff'),('Gráfica tangente','graph','tan(x)','#65d6ff'),('Parábola','graph','x^2','#65d6ff'),('Exponencial','graph','exp(x)','#65d6ff'),('Logaritmo','graph','log(x)','#65d6ff'),('Texto','text','Nuevo texto','#f1f4fa'),('Ejes','axes','','#8290a5'),('Punto','point','A','#ffbd69'),('Vector','vector','v','#ffbd69'),('Recta','line','y=x','#65d6ff'),('Círculo','circle','','#65d6ff'),('Elipse','ellipse','','#65d6ff'),('Polígono','polygon','','#65d6ff'),('Flecha','arrow','','#ffbd69'),('Plano cartesiano','axes','','#8290a5'),('Llaves y etiquetas','text','Etiqueta','#f1f4fa'),('Imagen','image','','#65d6ff'),('Tabla','table','','#65d6ff'),('Grupo','group','','#65d6ff')]
        name,kind,expression,color=definitions[row]; track=self.state.setdefault('tracks',['Pista 1'])[-1]
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

    # Convierte el estado del proyecto en una escena editable de Manim.
    def refresh_code_view(self, _index=None):
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
                graph_functions = {
                    'sin(x)': 'np.sin(x)',
                    'cos(x)': 'np.cos(x)',
                    'tan(x)': 'np.sin(x) * 0.5',
                    'x^2': '(x - np.pi) ** 2 / 5 - 1',
                    'exp(x)': 'np.exp(x)',
                    'log(x)': 'np.log(np.maximum(x, 0.001))',
                }
                graph_expression = graph_functions.get(expression.strip().lower())
                if graph_expression:
                    definition = (
                        f'graph_axes_{index + 1} = Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], tips=False)\n'
                        f'        {variable} = graph_axes_{index + 1}.plot(lambda x: {graph_expression}, '
                        f'x_range=[-7, 7], color={color}).move_to({location})'
                    )
            elif kind == 'text':
                font = json.dumps(str(obj.get('font_family', 'Noto Serif')))
                weight = 'BOLD' if int(obj.get('font_weight', 400)) >= 700 else 'NORMAL'
                definition = (
                    f'{variable} = Text({json.dumps(expression, ensure_ascii=False)}, '
                    f'font={font}, font_size={int(obj.get("font_size", 42))}, '
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

            object_scale=float(obj.get('scale',1.0))
            if kind not in {'text','group'} and object_scale != 1.0:
                definition += f'.scale({object_scale:.4f})'

            supported += 1
            lines.extend('        ' + part.lstrip() for part in definition.splitlines())
            start = max(0.0, float(obj.get('start', 0)))
            duration = max(0.0, float(obj.get('duration', 0)))
            end = min(total_duration, start + duration)
            if start <= total_duration and end >= start:
                events.setdefault(min(start, total_duration), []).append((1, f'self.add({variable})'))
                events.setdefault(end, []).append((0, f'self.remove({variable})'))

        lines.extend(['', '        # Aparición y desaparición según la línea de tiempo.'])
        current_time = 0.0
        for event_time in sorted(events):
            delta = event_time - current_time
            if delta > 0:
                lines.append(f'        self.wait({delta:.3f})')
            for _, statement in sorted(events[event_time]):
                lines.append(f'        {statement}')
            current_time = event_time
        if total_duration > current_time:
            lines.append(f'        self.wait({total_duration - current_time:.3f})')
        if supported == 0:
            lines.append('        self.wait(1)')
        self._updating_code_view=True
        self.code_view.setPlainText('\n'.join(lines) + '\n')
        self._updating_code_view=False
        self._code_view_dirty=False
        self.code_status.setText('Código sincronizado con la previsualización.')
        self.code_status.setStyleSheet('color:#aeb4bd')

    # Sincroniza las ediciones con una pausa corta para no parsear cada tecla.
    def _mark_code_view_edited(self):
        if not self._updating_code_view:
            self._code_view_dirty=True
            self.code_status.setText('Aplicando cambios a la previsualización…')
            self.code_status.setStyleSheet('color:#d8c27a')
            self._code_sync_timer.start()

    def preview_state_changed(self):
        self._preview_sync_timer.start()

    def _sync_preview_changes(self):
        self.update_views()

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
            and node.func.attr in {'move_to', 'scale', 'set_color'}
        ):
            transforms.append(node)
            node=node.func.value

        call_name=self._manim_call_name(node)
        if not isinstance(node, ast.Call):
            return None
        keywords={item.arg:item.value for item in node.keywords if item.arg}
        args=node.args
        color=self._code_literal(keywords.get('color'), '#65d6ff')
        expression=''
        kind=None
        obj={'name':variable.replace('_',' ').title(),'kind':'','expression':'','color':color,
             'start':0,'duration':1,'visible':True,'track':'Pista 1','position':{'x':0.52,'y':0.54},'scale':1.0}

        if call_name in {'Text','MathTex','Tex'}:
            kind='text'
            expression=self._code_literal(args[0], '') if args else ''
            obj.update(
                name=str(expression)[:24] or obj['name'],
                font_family=self._code_literal(keywords.get('font'), 'Noto Serif'),
                font_size=int(self._code_literal(keywords.get('font_size'), 42)),
                font_weight=700 if self._code_literal(keywords.get('weight'), 'NORMAL') == 'BOLD' else 400,
            )
        elif call_name=='Axes':
            kind='axes'
        elif call_name=='plot':
            kind='graph'
            if args and isinstance(args[0], ast.Lambda):
                body=args[0].body
                if isinstance(body, ast.Call):
                    function=self._manim_call_name(body)
                    expression={'sin':'sin(x)','cos':'cos(x)','tan':'tan(x)','exp':'exp(x)','log':'log(x)'}.get(function,'sin(x)')
                else:
                    calls={self._manim_call_name(item) for item in ast.walk(body) if isinstance(item,ast.Call)}
                    has_square=any(
                        isinstance(item,ast.BinOp) and isinstance(item.op,ast.Pow)
                        and self._code_literal(item.right)==2
                        for item in ast.walk(body)
                    )
                    if has_square:
                        expression='x^2'
                    elif 'sin' in calls and any(isinstance(item,ast.BinOp) and isinstance(item.op,ast.Mult) for item in ast.walk(body)):
                        expression='tan(x)'
                    else:
                        expression='sin(x)'
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

        for transform in reversed(transforms):
            method=transform.func.attr
            value=transform.args[0] if transform.args else None
            if method=='set_color':
                obj['color']=self._code_literal(value, obj['color'])
            elif method=='scale':
                obj['scale']=float(self._code_literal(value, 1.0))
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
        if kind=='text' and call_name in {'Text','MathTex','Tex'} and not transforms:
            obj['position']={'x':0.04,'y':0.1}
        return obj

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
            f'obj_{index + 1}':obj.get('track','Pista 1')
            for index,obj in enumerate(current_objects)
        }
        tracks_by_name={
            obj.get('name'):obj.get('track','Pista 1')
            for obj in current_objects if obj.get('name')
        }
        for statement in construct.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            target=statement.targets[0] if isinstance(statement, ast.Assign) and statement.targets else getattr(statement,'target',None)
            value=statement.value
            if not isinstance(target, ast.Name) or target.id.startswith('graph_axes_'):
                continue
            parsed=self._read_manim_object(value,target.id)
            if parsed is not None:
                parsed['track']=tracks_by_variable.get(
                    target.id,
                    tracks_by_name.get(parsed.get('name'), self.state.get('tracks',['Pista 1'])[-1]),
                )
                objects[target.id]=parsed

        starts={}
        active={}
        timeline=[]
        current_time=0.0

        def names_in(node):
            return list(dict.fromkeys(item.id for item in ast.walk(node) if isinstance(item, ast.Name) and item.id in objects))

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
                    animation=self._manim_call_name(argument)
                    for name in names_in(argument):
                        if animation in {'FadeOut','Uncreate','Unwrite'}:
                            if name in active:
                                obj=objects[name]
                                obj['start']=starts.get(name,0.0)
                                obj['duration']=max(0.1,current_time+run_time-obj['start'])
                                timeline.append(obj)
                                active.pop(name,None)
                        else:
                            starts[name]=current_time
                            active[name]=True
                current_time+=max(0.0,run_time)

        total_duration=max(1.0,current_time)
        for name in active:
            obj=objects[name]
            obj['start']=starts.get(name,0.0)
            obj['duration']=max(0.1,total_duration-obj['start'])
            timeline.append(obj)
        return timeline,total_duration

    def apply_code_to_preview(self):
        try:
            objects,duration=self._parse_manim_scene(self.code_view.toPlainText())
        except (SyntaxError, ValueError, TypeError, OverflowError) as error:
            detail=f'Error en el código; se conserva la última previsualización válida: {error}'
            self.code_status.setText(detail)
            self.code_status.setStyleSheet('color:#ff8585')
            return

        self._applying_code=True
        try:
            self.state['objects']=objects
            self.state['duration']=max(1.0,duration)
            self.code_status.setText('Código aplicado a la previsualización.')
            self.code_status.setStyleSheet('color:#9bd6a4')
            self.refresh_objects()
            self.preview.update()
            self.timeline.update()
            self._code_view_dirty=False
        finally:
            self._applying_code=False

    # Mantiene las vistas, el código y el historial alineados con el estado.
    def update_views(self):
        self.state['duration']=max([self.state['duration']]+[o['start']+o['duration'] for o in self.state['objects']])
        snapshot=json.dumps(self.state,sort_keys=True)
        if snapshot != self._last_snapshot:
            self._undo_stack.append(self._last_snapshot); self._undo_stack=self._undo_stack[-100:]; self._redo_stack.clear(); self._last_snapshot=snapshot
            if not self._applying_code and not self._code_view_dirty:
                self.refresh_code_view()
        self.preview.update(); self.timeline.update(); self._update_timeline_scroll()
    # Historial de deshacer/rehacer basado en instantáneas del proyecto.
    def _restore_history(self, source, destination):
        if not source:return
        destination.append(json.dumps(self.state)); self.state=json.loads(source.pop()); self._last_snapshot=json.dumps(self.state,sort_keys=True)
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
            s,f=divmod(n,30); h,s=divmod(s,3600); m,s=divmod(s,60); return f'{h:02d}:{m:02d}:{s:02d}:{f:02d}'
        self.timecode.setText(f'{tc(frame)} / {tc(total)}')
    def toggle_play(self):
        self.playing=not self.playing; self.play_btn.setText('❚❚' if self.playing else '▶'); self.play_btn.setToolTip('Pausar' if self.playing else 'Reproducir'); self.timer.start() if self.playing else self.timer.stop()
    def tick(self): self.seek((self.slider.value()+1)%101)
    def new_project(self): self.state=new_project(); self.path=None; self.preview.state=self.state; self.timeline.state=self.state; self.timeline.set_scroll_offset(0); self._update_timeline_scroll(); self.refresh_objects()
    # Persistencia: carga y guardado del formato de proyecto.
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

    # Exportación: renderiza cada fotograma de la previsualización y lo envía a ffmpeg.
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

