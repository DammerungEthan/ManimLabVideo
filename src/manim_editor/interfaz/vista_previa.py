"""Widget de vista previa para escenas matemáticas."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPainter, QPen,
    QPainterPath, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import (
    QLabel, QMenu, QPushButton, QScrollBar, QSplitter, QToolButton, QWidget,
)
from manim_editor.interfaz.texto_matematico import format_math_expression
from manim_editor.interfaz.creador_elementos import CreadorElementos
from manim_editor.interfaz.interaccion_lienzo import InteraccionLienzo
from manim_editor.interfaz.vista_grafica_funcion import FunctionPlotPreview
from manim_editor.tipografia import MANIM_MATH_FONT, MANIM_TEXT_FONT


class Preview(CreadorElementos, InteraccionLienzo, QWidget):
    """Dibuja la escena y permite seleccionar, mover y redimensionar objetos."""

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.progress = 0.38
        self.setMinimumSize(420, 270)
        self._expanded = False
        self._original_splitter = None
        self._original_splitter_sizes = None
        self._hidden_app_widgets = []
        self.selected_index = None
        self._object_bounds = {}
        self._object_frame_bounds = {}
        self._object_positions = {}
        self._object_rotation_anchors = {}
        self._object_selection_corners = {}
        self._object_alignment_centers = {}
        self._drag_mode = None
        self._drag_origin = None
        self._drag_position = None
        self._drag_bounds = None
        self._drag_scale = 1.0
        self._drag_font_size = 48
        self._drag_rotation = 0.0
        self._rotation_origin_angle = 0.0
        self._resize_corner = None
        self._active_guides = {}
        self._rendered_frame = QPixmap()
        self._editing_enabled = True
        self.zoom_level = 100

        self.size_button = QPushButton("⛶", self)
        self.size_button.setToolTip("Ampliar vista previa")
        self.size_button.setAccessibleName("Ampliar vista previa")
        self.size_button.setFixedSize(36, 32)
        self.size_button.setStyleSheet(
            "QPushButton { background: #202735; color: #e7ebf2; "
            "border: 1px solid #536174; border-radius: 5px; font-size: 18px; }"
            "QPushButton:hover { background: #354052; }"
        )
        self.size_button.clicked.connect(self.toggle_size)

        self.text_button = QPushButton("T+", self)
        self.text_button.setToolTip("Agregar texto a la escena")
        self.text_button.setAccessibleName("Agregar texto a la escena")
        self.text_button.setFixedSize(36, 32)
        self.text_button.setStyleSheet(
            "QPushButton { background: #202735; color: #e7ebf2; "
            "border: 1px solid #536174; border-radius: 5px; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #354052; }"
        )
        self.text_button.clicked.connect(self.add_text)

        self.shape_button = QToolButton(self)
        self.shape_button.setText("◇")
        self.shape_button.setToolTip("Agregar figura geométrica")
        self.shape_button.setAccessibleName("Agregar figura geométrica")
        self.shape_button.setFixedSize(36, 32)
        self.shape_button.setStyleSheet(
            "QToolButton { background: #202735; color: #e7ebf2; "
            "border: 1px solid #536174; border-radius: 5px; font-size: 18px; }"
            "QToolButton:hover { background: #354052; }"
        )
        self.shape_menu = QMenu(self.shape_button)
        self.shape_button.setMenu(self.shape_menu)
        self.shape_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._add_shape_menu_actions()

        self.function_button = QPushButton("ƒ", self)
        self.function_button.setToolTip("Generar y previsualizar una función")
        self.function_button.setAccessibleName("Generar función")
        self.function_button.setFixedSize(36, 32)
        self.function_button.setStyleSheet(
            "QPushButton { background: #202735; color: #e7ebf2; "
            "border: 1px solid #536174; border-radius: 5px; font-size: 18px; }"
            "QPushButton:hover { background: #354052; }"
        )
        self.function_button.clicked.connect(self.open_function_generator)

        self.equation_button = QPushButton("∑", self)
        self.equation_button.setToolTip("Agregar una ecuación matemática")
        self.equation_button.setAccessibleName("Agregar ecuación")
        self.equation_button.setFixedSize(36, 32)
        self.equation_button.setStyleSheet(
            "QPushButton { background: #202735; color: #e7ebf2; "
            "border: 1px solid #536174; border-radius: 5px; font-size: 18px; }"
            "QPushButton:hover { background: #354052; }"
        )
        self.equation_button.clicked.connect(self.open_equation_generator)

        self.zoom_bar = QScrollBar(Qt.Orientation.Vertical, self)
        self.zoom_bar.setRange(50, 200)
        self.zoom_bar.setValue(self.zoom_level)
        self.zoom_bar.setSingleStep(5)
        self.zoom_bar.setPageStep(10)
        self.zoom_bar.setFixedSize(12, 100)
        self.zoom_bar.setToolTip("Zoom de la vista previa: 100 %")
        self.zoom_bar.setStyleSheet(
            "QScrollBar:vertical { background: #353535; width: 10px; margin: 0; border: 1px solid #777; border-radius: 5px; }"
            "QScrollBar::handle:vertical { background: #a0a0a0; min-height: 20px; border-radius: 5px; }"
            "QScrollBar::handle:vertical:hover { background: #c0c0c0; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #3a3a3a; }"
        )
        self.zoom_bar.valueChanged.connect(self.set_zoom)
        self.zoom_label = QLabel(f"{self.zoom_level}%", self)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet("color: #d0d0d0; font-size: 11px;")
        self.zoom_label.setFixedSize(42, 20)
        self._position_size_button()

    def _position_size_button(self):
        render_only = self.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        for control in (
            self.size_button, self.text_button, self.shape_button,
            self.function_button, self.equation_button,
            self.zoom_bar, self.zoom_label,
        ):
            control.setVisible(not render_only)
        if render_only:
            return
        right = self.width() - 8
        button_x = right - self.size_button.width()
        first_y = 8
        self.size_button.move(button_x, first_y)
        text_y = max(8, (self.height() - self.text_button.height()) // 2)
        self.text_button.move(right - self.text_button.width(), text_y)
        self.shape_button.move(
            right - self.shape_button.width(),
            text_y + self.text_button.height() + 6,
        )
        self.function_button.move(
            right - self.function_button.width(),
            text_y + 2 * (self.text_button.height() + 6),
        )
        self.equation_button.move(
            right - self.equation_button.width(),
            text_y + 3 * (self.text_button.height() + 6),
        )
        self.zoom_bar.move(
            self.width() - self.zoom_bar.width() - 8,
            self.height() - self.zoom_bar.height() - self.zoom_label.height() - 12,
        )
        self.zoom_label.move(
            self.width() - self.zoom_label.width() - 8,
            self.height() - self.zoom_label.height() - 4,
        )

    def set_zoom(self, value):
        self.zoom_level = value
        self.zoom_bar.setToolTip(f"Zoom de la vista previa: {value} %")
        self.zoom_label.setText(f"{value}%")
        self.update()

    def set_rendered_frame(self, frame):
        """Muestra un fotograma del render real de Manim, si existe."""
        self._rendered_frame = QPixmap(frame) if frame is not None else QPixmap()
        self._object_bounds.clear()
        self._object_frame_bounds.clear()
        self._object_positions.clear()
        self._object_rotation_anchors.clear()
        self._object_selection_corners.clear()
        self._object_alignment_centers.clear()
        self.update()

    def set_editing_enabled(self, enabled):
        """Evita editar el fotograma anterior mientras el código está pendiente de render."""
        self._editing_enabled = bool(enabled)
        self.text_button.setEnabled(self._editing_enabled)
        self.shape_button.setEnabled(self._editing_enabled)
        self.function_button.setEnabled(self._editing_enabled)
        if not self._editing_enabled:
            self.selected_index = None
            self._drag_mode = None
        self.update()

    def _preview_geometry(self):
        w, h = self.width(), self.height()
        video_width = max(1, self.state.get("width", 1920))
        video_height = max(1, self.state.get("height", 1080))
        aspect = video_width / video_height
        frame_width = 1000.0
        frame_height = frame_width / aspect
        render_only = self.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        if render_only:
            viewport_x, viewport_y = 0.0, 0.0
            viewport_width, viewport_height = max(1, w - 36), max(1, h - 48)
            zoom = 1.0
        else:
            viewport_x, viewport_y = 0.0, 10.0
            viewport_width, viewport_height = max(1, w - 100), max(1, h - 20)
            zoom = self.zoom_level / 100
        fit_width = min(viewport_width, viewport_height * aspect)
        fit_height = fit_width / aspect
        cw, ch = fit_width * zoom, fit_height * zoom
        ox = viewport_x + (viewport_width - cw) / 2
        oy = viewport_y + (viewport_height - ch) / 2
        return {
            "widget_width": w,
            "widget_height": h,
            "x": ox,
            "y": oy,
            "width": cw,
            "height": ch,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "scale_x": cw / frame_width,
            "scale_y": ch / frame_height,
            "viewport": QRectF(viewport_x, viewport_y, viewport_width, viewport_height),
        }

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_size_button()

    def toggle_size(self):
        if self._expanded:
            self._restore_size()
        else:
            self._expand_size()

    def _hide_surrounding_app_ui(self):
        window = self.window()
        preserved = {self, *self.findChildren(QWidget)}
        ancestor = self.parentWidget()
        while ancestor is not None:
            preserved.add(ancestor)
            ancestor = ancestor.parentWidget()

        self._hidden_app_widgets = []
        for widget in window.findChildren(QWidget):
            if widget not in preserved and widget.isVisible():
                self._hidden_app_widgets.append(widget)
                widget.hide()

    def _restore_surrounding_app_ui(self):
        for widget in self._hidden_app_widgets:
            widget.show()
        self._hidden_app_widgets = []

    def _expand_size(self):
        parent = self.parentWidget()
        if not isinstance(parent, QSplitter):
            return
        # Guarda el contenedor y su distribución para restaurarlos al cerrar.
        self._original_splitter = parent
        self._original_splitter_sizes = parent.sizes()
        self._expanded = True
        self.size_button.setText("❐")
        self.size_button.setToolTip("Volver al tamaño original")
        self.size_button.setAccessibleName("Volver al tamaño original")
        self._hide_surrounding_app_ui()
        for index in range(parent.count()):
            widget = parent.widget(index)
            if widget is not self:
                widget.hide()
        expanded_sizes = [0] * parent.count()
        expanded_sizes[parent.indexOf(self)] = max(1, parent.height())
        parent.setSizes(expanded_sizes)
        self.show()
        self.updateGeometry()

    def _restore_size(self):
        splitter = self._original_splitter
        if splitter is None:
            return

        for index in range(splitter.count()):
            widget = splitter.widget(index)
            if widget is not self:
                widget.show()
        if self._original_splitter_sizes:
            splitter.setSizes(self._original_splitter_sizes)
        self._original_splitter = None
        self._original_splitter_sizes = None
        self._restore_surrounding_app_ui()
        self._expanded = False
        self.size_button.setText("⛶")
        self.size_button.setToolTip("Ampliar vista previa")
        self.size_button.setAccessibleName("Ampliar vista previa")
        self.show()
        self.update()


    @staticmethod

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#000000"))
        frame = self._preview_geometry()
        frame_rect = QRectF(frame["x"], frame["y"], frame["width"], frame["height"])
        viewport = frame["viewport"]
        self._object_bounds = {}
        self._object_frame_bounds = {}
        self._object_positions = {}
        self._object_rotation_anchors = {}
        self._object_selection_corners = {}
        self._object_alignment_centers = {}
        rendered_frame = not self._rendered_frame.isNull()
        if rendered_frame:
            p.save()
            p.setClipRect(viewport)
            p.fillRect(frame_rect, QColor("#000000"))
            p.drawPixmap(frame_rect, self._rendered_frame, QRectF(self._rendered_frame.rect()))
            p.restore()
            p.setPen(QPen(QColor("#536174"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(frame_rect)
        # Dibuja los objetos en coordenadas del lienzo y guarda sus límites
        # para hit-testing, selección y redimensionado.
        p.save()
        p.setClipRect(viewport)
        if not rendered_frame:
            p.fillRect(frame_rect, QColor("#000000"))
        p.translate(frame["x"], frame["y"])
        p.scale(frame["scale_x"], frame["scale_y"])
        if rendered_frame:
            # El video ya contiene estos objetos; dibujamos solo su geometría
            # de selección para permitir moverlos sin duplicarlos en pantalla.
            p.setOpacity(0)

        frame_width = frame["frame_width"]
        frame_height = frame["frame_height"]
        now = self.progress * self.state.get("duration", 10)
        base_scale = min(frame_width, frame_height) * .30
        text_index = 0
        for index, obj in enumerate(self.state.get("objects", [])):
            kind = obj.get("kind")
            position = self._position_for(obj, index, text_index, frame)
            if kind == "text":
                text_index += 1
            if not obj.get("visible", True):
                continue
            if now < obj.get("start", 0) or now > obj.get("start", 0) + obj.get("duration", 0):
                continue

            # Calcula transiciones de entrada/salida sobre el tiempo local del clip.
            clip_duration = max(0.03, float(obj.get("duration", 0)))
            local_time = now - float(obj.get("start", 0))
            enter_kind = obj.get("animation_in", "none")
            exit_kind = obj.get("animation_out", "none")
            enter_duration = min(clip_duration, max(0.05, float(obj.get("animation_in_duration", 0.5))))
            exit_duration = min(clip_duration, max(0.05, float(obj.get("animation_out_duration", 0.5))))
            enter_effect = (0.0, 0.0, 1.0, 1.0, 0.0)
            exit_effect = (0.0, 0.0, 1.0, 1.0, 0.0)
            if enter_kind != "none" and local_time < enter_duration:
                enter_effect = self._animation_effect(
                    enter_kind, local_time / enter_duration, True, frame_width, frame_height
                )
            remaining_time = clip_duration - local_time
            if exit_kind != "none" and remaining_time < exit_duration:
                exit_effect = self._animation_effect(
                    exit_kind, 1.0 - remaining_time / exit_duration,
                    False, frame_width, frame_height,
                )
            enter_dx, enter_dy, enter_scale, enter_opacity, enter_rotation = enter_effect
            exit_dx, exit_dy, exit_scale, exit_opacity, exit_rotation = exit_effect

            x = position["x"] * frame_width
            y = position["y"] * frame_height
            x += enter_dx + exit_dx
            y += enter_dy + exit_dy
            scale = base_scale * float(obj.get("scale", 1.0)) * enter_scale * exit_scale
            rotation = float(obj.get("rotation", 0.0)) + enter_rotation + exit_rotation
            if kind in {"text", "equation"}:
                display_expression = (
                    format_math_expression(obj.get("expression", ""))
                    if kind == "equation" else obj.get("expression", "")
                )
                equation_font_weight = QFont.Weight.Normal
                pivot_font = QFont(
                    obj.get("font_family", MANIM_MATH_FONT if kind == "equation" else MANIM_TEXT_FONT),
                    round(obj.get("font_size", 48) * float(obj.get("scale", 1.0))),
                    QFont.Weight(obj.get("font_weight", int(equation_font_weight))),
                )
                if kind == "equation":
                    pivot_font.setStyle(QFont.Style.StyleItalic)
                pivot_metrics = QFontMetricsF(pivot_font)
                pivot_expression = display_expression
                pivot_width = max(12.0, pivot_metrics.horizontalAdvance(pivot_expression))
                pivot_height = max(12.0, pivot_metrics.height())
                if kind == "equation":
                    x -= pivot_width / 2
                    y -= pivot_height / 2
                pivot_x, pivot_y = x + pivot_width / 2, y + pivot_height / 2
            elif kind == "table":
                pivot_metrics = QFontMetricsF(QFont(MANIM_TEXT_FONT, 24))
                pivot_expression = obj.get("expression", "")
                pivot_width = max(48.0, pivot_metrics.horizontalAdvance(pivot_expression) + 20)
                pivot_x, pivot_y = x + pivot_width / 2, y + 24
            else:
                pivot_x, pivot_y = x, y
            p.save()
            p.translate(pivot_x, pivot_y)
            p.rotate(-rotation)
            p.translate(-pivot_x, -pivot_y)
            if kind == "axes":
                p.setPen(QPen(QColor(obj.get("color", "#8290a5")), 1))
                p.drawLine(int(x - scale * 1.3), int(y), int(x + scale * 1.3), int(y))
                p.drawLine(int(x), int(y - scale * 1.15), int(x), int(y + scale * 1.15))
                bounds = QRectF(x - scale * 1.3, y - scale * 1.15,
                                scale * 2.6, scale * 2.3)
            elif kind == "graph":
                unit = min(frame_width / 14.222, frame_height / 8) * float(obj.get("scale", 1.0))
                left, right = x - 7 * unit, x + 7 * unit
                top, bottom = y - 4 * unit, y + 4 * unit
                animation = obj.get("animation", "None")
                animation_duration = max(0.01, float(obj.get("animation_duration", 1.0)))
                animation_progress = min(1.0, max(0.0, (now - float(obj.get("start", 0))) / animation_duration))
                if animation == "None" or now >= float(obj.get("start", 0)) + animation_duration:
                    animation_progress = 1.0
                p.save()
                if animation == "FadeIn":
                    p.setOpacity(animation_progress)
                elif animation == "GrowFromCenter":
                    p.translate(x, y)
                    p.scale(animation_progress, animation_progress)
                    p.translate(-x, -y)
                if obj.get("show_grid", True):
                    p.setPen(QPen(QColor("#303945"), max(1.0, unit * 0.008)))
                    for tick in range(-6, 8, 2):
                        p.drawLine(QPointF(x + tick * unit, top),
                                   QPointF(x + tick * unit, bottom))
                    for tick in range(-4, 5, 2):
                        p.drawLine(QPointF(left, y - tick * unit),
                                   QPointF(right, y - tick * unit))
                if obj.get("show_axes", True):
                    p.setPen(QPen(QColor("#586273"), max(1.0, unit * 0.012)))
                    p.drawLine(QPointF(left, y), QPointF(right, y))
                    p.drawLine(QPointF(x, top), QPointF(x, bottom))
                    for tick in range(-6, 7, 2):
                        p.drawLine(QPointF(x + tick * unit, y - 3),
                                   QPointF(x + tick * unit, y + 3))
                    for tick in (-4, -2, 2, 4):
                        p.drawLine(QPointF(x - 3, y - tick * unit),
                                   QPointF(x + 3, y - tick * unit))

                graph_path = QPainterPath()
                started = False
                previous_y = None
                graph_points = FunctionPlotPreview.sample_expression(
                    str(obj.get("expression", "sin(x)")).replace("^", "**")
                )
                if animation in {"Create", "Write"}:
                    graph_points = graph_points[:max(1, round(len(graph_points) * animation_progress))]
                for point in graph_points:
                    if point is None:
                        started = False
                        previous_y = None
                        continue
                    x_value, y_value = point
                    if abs(y_value) > 4 or (
                        previous_y is not None and abs(y_value - previous_y) > 2.0
                    ):
                        started = False
                        previous_y = y_value
                        continue
                    graph_point = QPointF(x + x_value * unit, y - y_value * unit)
                    if started:
                        graph_path.lineTo(graph_point)
                    else:
                        graph_path.moveTo(graph_point)
                        started = True
                    previous_y = y_value
                p.setPen(QPen(QColor(obj.get("color", "#65d6ff")), max(2.0, unit * 0.035)))
                p.drawPath(graph_path)
                p.restore()
                bounds = QRectF(left, top, right - left, bottom - top)
            elif kind in {"text", "equation"}:
                is_equation = kind == "equation"
                font = QFont(
                    obj.get("font_family", MANIM_MATH_FONT if is_equation else MANIM_TEXT_FONT),
                    round(obj.get("font_size", 48) * float(obj.get("scale", 1.0))),
                    QFont.Weight(obj.get("font_weight", int(QFont.Weight.Normal))),
                )
                if is_equation:
                    font.setStyle(QFont.Style.StyleItalic)
                metrics = QFontMetricsF(font)
                expression = (
                    format_math_expression(obj.get("expression", ""))
                    if is_equation else obj.get("expression", "")
                )
                p.setPen(QColor(obj.get("color", "#f1f4fa")))
                p.setFont(font)
                p.drawText(x, y + metrics.ascent(), expression)
                bounds = QRectF(x, y, max(12.0, metrics.horizontalAdvance(expression)),
                                max(12.0, metrics.height()))
            elif kind == "point":
                radius = max(4.0, 8.0 * float(obj.get("scale", 1.0)))
                color = QColor(obj.get("color", "#ffbd69"))
                p.setPen(QPen(color, 1))
                p.setBrush(color)
                bounds = QRectF(x - radius, y - radius, radius * 2, radius * 2)
                p.drawEllipse(bounds)
            elif kind in {"circle", "ellipse"}:
                radius_x = scale * .45
                radius_y = radius_x if kind == "circle" else radius_x * .58
                bounds = QRectF(x - radius_x, y - radius_y, radius_x * 2, radius_y * 2)
                p.setPen(QPen(QColor(obj.get("color", "#65d6ff")), 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(bounds)
            elif kind in {"line", "vector", "arrow"}:
                half_width = scale * .6
                color = QColor(obj.get("color", "#65d6ff"))
                p.setPen(QPen(color, 3))
                p.drawLine(int(x - half_width), int(y), int(x + half_width), int(y))
                if kind in {"vector", "arrow"}:
                    head = max(8.0, scale * .10)
                    p.drawLine(int(x + half_width), int(y), int(x + half_width - head), int(y - head * .65))
                    p.drawLine(int(x + half_width), int(y), int(x + half_width - head), int(y + head * .65))
                bounds = QRectF(x - half_width, y - scale * .12,
                                half_width * 2, scale * .24)
            elif kind == "polygon":
                half_width = scale * .55
                half_height = scale * .5
                points = (
                    (x, y - half_height),
                    (x - half_width, y + half_height),
                    (x + half_width, y + half_height),
                )
                color = QColor(obj.get("color", "#65d6ff"))
                p.setPen(QPen(color, 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                for start, end in zip(points, points[1:] + points[:1]):
                    p.drawLine(int(start[0]), int(start[1]), int(end[0]), int(end[1]))
                bounds = QRectF(x - half_width, y - half_height,
                                half_width * 2, half_height * 2)
            elif kind == "table":
                expression = obj.get("expression", "")
                font = QFont(MANIM_TEXT_FONT, 24)
                metrics = QFontMetricsF(font)
                bounds = QRectF(x, y, max(48.0, metrics.horizontalAdvance(expression) + 20), 48)
                p.setPen(QPen(QColor(obj.get("color", "#65d6ff")), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(bounds)
                p.setFont(font)
                p.drawText(x + 10, y + 32, expression)
            else:
                p.restore()
                continue

            p.restore()
            rotation_transform = QTransform()
            rotation_transform.translate(pivot_x, pivot_y)
            rotation_transform.rotate(-rotation)
            rotation_transform.translate(-pivot_x, -pivot_y)
            rotated_bounds = rotation_transform.mapRect(bounds)
            self._object_positions[index] = position
            self._object_frame_bounds[index] = bounds
            frame_corners = (
                bounds.topLeft(), bounds.topRight(),
                bounds.bottomRight(), bounds.bottomLeft(),
            )
            rotated_corners = [rotation_transform.map(corner) for corner in frame_corners]
            self._object_selection_corners[index] = [
                QPointF(frame["x"] + corner.x() * frame["scale_x"],
                        frame["y"] + corner.y() * frame["scale_y"])
                for corner in rotated_corners
            ]
            self._object_alignment_centers[index] = rotation_transform.map(bounds.center())
            self._object_rotation_anchors[index] = QPointF(
                frame["x"] + pivot_x * frame["scale_x"],
                frame["y"] + pivot_y * frame["scale_y"],
            )
            self._object_bounds[index] = QRectF(
                frame["x"] + rotated_bounds.x() * frame["scale_x"],
                frame["y"] + rotated_bounds.y() * frame["scale_y"],
                rotated_bounds.width() * frame["scale_x"],
                rotated_bounds.height() * frame["scale_y"],
            )

        p.restore()
        if self._active_guides:
            p.save()
            p.setClipRect(frame_rect)
            guide_pen = QPen(QColor("#ff5f87"), 1, Qt.PenStyle.DashLine)
            p.setPen(guide_pen)
            if "vertical" in self._active_guides:
                guide_x = frame["x"] + self._active_guides["vertical"] * frame["scale_x"]
                p.drawLine(int(guide_x), int(frame_rect.top()),
                           int(guide_x), int(frame_rect.bottom()))
            if "horizontal" in self._active_guides:
                guide_y = frame["y"] + self._active_guides["horizontal"] * frame["scale_y"]
                p.drawLine(int(frame_rect.left()), int(guide_y),
                           int(frame_rect.right()), int(guide_y))
            p.restore()
        p.setPen(QPen(QColor("#536174"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(frame_rect)
        if self.selected_index in self._object_bounds:
            selected_corners = self._object_selection_corners[self.selected_index]
            p.setPen(QPen(QColor("#65d6ff"), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolygon(QPolygonF(selected_corners))
            top_mid, rotation_handle = self._rotation_handle_position(selected_corners)
            p.drawLine(top_mid, rotation_handle)
            p.setBrush(QColor("#65d6ff"))
            p.drawEllipse(rotation_handle, 6, 6)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setBrush(QColor("#e7ebf2"))
            for corner in selected_corners:
                p.drawRect(QRectF(corner.x() - 4, corner.y() - 4, 8, 8))
