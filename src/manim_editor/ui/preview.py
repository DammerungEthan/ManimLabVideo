"""Widget de vista previa para escenas matemáticas."""
import ast
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QFontMetricsF, QIcon, QPainter, QPen,
    QPainterPath, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import (
    QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QCheckBox, QLineEdit, QMenu, QPushButton, QScrollBar, QSpinBox, QSplitter,
    QToolButton, QVBoxLayout, QWidget,
)
from manim_editor.ui.math_text import EquationPreview, format_math_expression
from manim_editor.typography import MANIM_MATH_FONT, MANIM_TEXT_FONT


class FunctionPlotPreview(QWidget):
    """Muestra una gráfica matemática dentro del diálogo de inserción."""

    FUNCTIONS = {
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "asin": math.asin, "acos": math.acos, "atan": math.atan,
        "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
        "sqrt": math.sqrt, "abs": abs, "exp": math.exp,
        "log": math.log, "log10": math.log10,
    }
    CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.expression = "sin(x)"
        self.color = QColor("#65d6ff")
        self.axes_visible = True
        self.error = ""
        self.show_grid = True
        self.show_axes = True
        self.animation_type = "Create"
        self.animation_progress = 1.0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(30)
        self._animation_timer.timeout.connect(self._advance_animation_preview)
        self.setMinimumHeight(190)

    def set_function(self, expression):
        self.expression = expression.strip().replace("^", "**")
        self.error = ""
        try:
            ast.parse(self.expression or "0", mode="eval")
            valid_samples = 0
            for sample in range(65):
                try:
                    self.evaluate(self.expression, -7 + 14 * sample / 64)
                    valid_samples += 1
                except (ValueError, TypeError, ZeroDivisionError, OverflowError):
                    continue
            if valid_samples == 0:
                raise ValueError("No hay valores definidos en el intervalo visible")
        except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
            self.error = str(error)
        self.update()

    @classmethod
    def evaluate(cls, expression, x_value):
        """Evalúa una expresión con x y operaciones matemáticas seguras."""
        tree = ast.parse(expression or "0", mode="eval")

        def visit(node):
            if isinstance(node, ast.Expression):
                return visit(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.Name):
                if node.id == "x":
                    return x_value
                if node.id in cls.CONSTANTS:
                    return cls.CONSTANTS[node.id]
                raise ValueError(f"Nombre no permitido: {node.id}")
            if isinstance(node, ast.BinOp):
                left, right = visit(node.left), visit(node.right)
                operations = {
                    ast.Add: lambda: left + right,
                    ast.Sub: lambda: left - right,
                    ast.Mult: lambda: left * right,
                    ast.Div: lambda: left / right,
                    ast.FloorDiv: lambda: left // right,
                    ast.Mod: lambda: left % right,
                    ast.Pow: lambda: left ** right,
                }
                operation = operations.get(type(node.op))
                if operation is None:
                    raise ValueError("Operador no permitido")
                if isinstance(node.op, ast.Pow) and abs(right) > 100:
                    raise ValueError("El exponente debe estar entre -100 y 100")
                return operation()
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = visit(node.operand)
                return value if isinstance(node.op, ast.UAdd) else -value
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                function = cls.FUNCTIONS.get(node.func.id)
                if function is None or node.keywords or len(node.args) not in (1, 2):
                    raise ValueError("Usa funciones como sin(x), sqrt(x) o log(x, 2)")
                arguments = [visit(argument) for argument in node.args]
                return function(*arguments)
            raise ValueError("Expresión no permitida")

        value = float(visit(tree))
        if not math.isfinite(value):
            raise ValueError("La función no produce un valor finito")
        return value

    @classmethod
    def sample_expression(cls, expression, start=-7.0, end=7.0, count=601):
        points = []
        for index in range(count):
            x_value = start + (end - start) * index / (count - 1)
            try:
                y_value = cls.evaluate(expression, x_value)
                if abs(y_value) > 1e4:
                    points.append(None)
                else:
                    points.append((x_value, y_value))
            except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
                points.append(None)
        return points

    def sampled_points(self, start=-7.0, end=7.0, count=601):
        return self.sample_expression(self.expression, start, end, count)

    def set_color(self, color):
        self.color = QColor(color)
        self.update()

    def set_grid_visible(self, visible):
        self.show_grid = bool(visible)
        self.update()

    def set_axes_visible(self, visible):
        self.show_axes = bool(visible)
        self.update()

    def set_animation_type(self, animation_type):
        self.animation_type = str(animation_type)
        self.animation_progress = 0.0 if self.animation_type != "None" else 1.0
        if self.animation_type == "None":
            self._animation_timer.stop()
        else:
            self._animation_timer.start()
        self.update()

    def _advance_animation_preview(self):
        self.animation_progress += 0.03
        if self.animation_progress > 1.0:
            self.animation_progress = 0.0
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101318"))
        plot = QRectF(self.rect()).adjusted(32, 14, -14, -28)
        zero_y = plot.top() + plot.height() / 2
        zero_x = plot.left() + plot.width() / 2
        if self.show_grid:
            painter.setPen(QPen(QColor("#303945"), 1))
            for tick in range(-6, 7, 2):
                x = plot.left() + (tick + 7) * plot.width() / 14
                painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            for tick in range(-4, 5, 2):
                y = zero_y - tick * plot.height() / 8
                painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        # El área representa x=[-7,7], y=[-4,4], igual que los ejes de Manim.
        if self.show_axes:
            painter.setPen(QPen(QColor("#738093"), 1.2))
            painter.drawLine(QPointF(plot.left(), zero_y), QPointF(plot.right(), zero_y))
            painter.drawLine(QPointF(zero_x, plot.top()), QPointF(zero_x, plot.bottom()))
            for tick in range(-6, 7, 2):
                tick_x = plot.left() + (tick + 7) * plot.width() / 14
                painter.drawLine(QPointF(tick_x, zero_y - 3), QPointF(tick_x, zero_y + 3))
            for tick in (-4, -2, 2, 4):
                tick_y = zero_y - tick * plot.height() / 8
                painter.drawLine(QPointF(zero_x - 3, tick_y), QPointF(zero_x + 3, tick_y))

        path = QPainterPath()
        started = False
        previous_y = None
        samples = self.sampled_points()
        progress = self.animation_progress
        if self.animation_type in {"Create", "Write"}:
            samples = samples[:max(1, int(len(samples) * progress))]
        painter.save()
        if self.animation_type == "FadeIn":
            painter.setOpacity(progress)
        elif self.animation_type == "GrowFromCenter":
            painter.translate(zero_x, zero_y)
            painter.scale(progress, progress)
            painter.translate(-zero_x, -zero_y)
        for point in samples:
            if point is None:
                started = False
                previous_y = None
                continue
            x_value, y_value = point
            if abs(y_value) > 4 or (previous_y is not None and abs(y_value - previous_y) > 2.0):
                started = False
                previous_y = y_value
                continue
            point = QPointF(
                plot.left() + (x_value + 7) * plot.width() / 14,
                zero_y - y_value * plot.height() / 8,
            )
            if started:
                path.lineTo(point)
            else:
                path.moveTo(point)
                started = True
            previous_y = y_value
        painter.setPen(QPen(self.color, 2.5))
        painter.drawPath(path)
        painter.restore()
        if self.show_axes:
            painter.setPen(QColor("#c7ced8"))
            painter.drawText(4, self.height() - 5, "−7")
            painter.drawText(self.width() - 23, self.height() - 5, "7")
            painter.drawText(5, 15, "y")
            painter.drawText(self.width() - 14, int(zero_y) - 4, "x")
        if self.error:
            painter.setPen(QColor("#ff7b83"))
            painter.drawText(plot.adjusted(8, 8, -8, -8), Qt.AlignmentFlag.AlignCenter,
                             "Expresión inválida")


class Preview(QWidget):
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

    def add_text(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Agregar texto")
        form = QFormLayout(dialog)

        content = QLineEdit()
        content.setPlaceholderText("Escribe el texto para la escena")
        font_family = QComboBox()
        font_families = sorted(QFontDatabase.families(), key=str.casefold)
        font_family.addItems(font_families)
        for family in (MANIM_TEXT_FONT, "Computer Modern"):
            if font_family.findText(family, Qt.MatchFlag.MatchFixedString) < 0:
                font_family.addItem(family)
        font_family.setCurrentText(MANIM_TEXT_FONT)
        font_size = QSpinBox()
        font_size.setRange(8, 300)
        font_size.setValue(48)
        font_weight = QComboBox()
        for label, weight in (
            ("Fino", QFont.Weight.Light),
            ("Normal", QFont.Weight.Normal),
            ("Medio", QFont.Weight.Medium),
            ("Seminegrita", QFont.Weight.DemiBold),
            ("Negrita", QFont.Weight.Bold),
            ("Extra negrita", QFont.Weight.Black),
        ):
            font_weight.addItem(label, int(weight))
        font_weight.setCurrentIndex(1)

        def update_font_previews(*_):
            # La lista sirve para reconocer la familia; el tamaño elegido se
            # aplica al texto de la escena, no a la muestra del desplegable.
            weight = QFont.Weight(font_weight.currentData())
            for index in range(font_family.count()):
                family = font_family.itemText(index)
                font_family.setItemData(
                    index,
                    QFont(family, 12, weight),
                    Qt.ItemDataRole.FontRole,
                )
            font_family.setFont(QFont(font_family.currentText(), 12, weight))

        font_family.currentTextChanged.connect(update_font_previews)
        font_weight.currentIndexChanged.connect(update_font_previews)
        update_font_previews()

        form.addRow("Texto", content)
        form.addRow("Fuente", font_family)
        form.addRow("Tamaño", font_size)
        form.addRow("Grosor", font_weight)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        expression = content.text().strip()
        if not expression:
            return

        text_count = sum(obj.get("kind") == "text" for obj in self.state.get("objects", []))
        frame = self._preview_geometry()
        start = self.progress * self.state.get("duration", 10)
        self.state.setdefault("objects", []).append({
            "name": expression[:24],
            "kind": "text",
            "expression": expression,
            "color": "#f1f4fa",
            "start": start,
            "duration": max(0.1, self.state.get("duration", 10) - start),
            "visible": True,
            "track": self._track_for_new_object(),
            "position": {"x": 0.04, "y": min(0.85, (36 + text_count * 56) / frame["frame_height"])},
            "scale": 1.0,
            "font_family": font_family.currentText(),
            "font_size": font_size.value(),
            "font_weight": font_weight.currentData(),
        })
        self.update()
        self._update_related_views()

    def _add_shape_menu_actions(self):
        """Crea las opciones de figuras que el preview sabe dibujar."""
        shapes = (
            ("Punto", "point", "A", "#ffbd69"),
            ("Recta", "line", "y=x", "#65d6ff"),
            ("Vector", "vector", "v", "#ffbd69"),
            ("Flecha", "arrow", "", "#ffbd69"),
            ("Círculo", "circle", "", "#65d6ff"),
            ("Elipse", "ellipse", "", "#65d6ff"),
            ("Triángulo", "polygon", "", "#65d6ff"),
            ("Ejes cartesianos", "axes", "", "#8290a5"),
        )
        for label, kind, expression, color in shapes:
            action = self.shape_menu.addAction(self._shape_icon(kind, color), "")
            action.setToolTip(label)
            action.setStatusTip(label)
            action.triggered.connect(
                lambda _checked=False, item=(label, kind, expression, color):
                    self.add_geometric_shape(*item)
            )

    def open_function_generator(self):
        """Permite elegir una función, revisar su gráfica e insertarla."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Generar función")
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        function_input = QLineEdit("sin(x)", dialog)
        function_input.setPlaceholderText("Ej.: sin(x) + x^2/5")
        form.addRow("f(x) =", function_input)
        show_grid = QCheckBox("Mostrar cuadrícula", dialog)
        show_grid.setChecked(True)
        show_axes = QCheckBox("Mostrar ejes", dialog)
        show_axes.setChecked(True)
        animation_choice = QComboBox(dialog)
        for label, value in (
            ("Dibujar (Create)", "Create"),
            ("Aparecer (FadeIn)", "FadeIn"),
            ("Escribir (Write)", "Write"),
            ("Crecer desde el centro", "GrowFromCenter"),
            ("Sin animación", "None"),
        ):
            animation_choice.addItem(label, value)
        form.addRow("", show_grid)
        form.addRow("", show_axes)
        form.addRow("Animación", animation_choice)
        layout.addLayout(form)

        plot_preview = FunctionPlotPreview(dialog)
        plot_preview.set_animation_type(animation_choice.currentData())
        layout.addWidget(plot_preview)
        function_input.textChanged.connect(plot_preview.set_function)
        show_grid.toggled.connect(plot_preview.set_grid_visible)
        show_axes.toggled.connect(plot_preview.set_axes_visible)
        animation_choice.currentIndexChanged.connect(
            lambda _index: plot_preview.set_animation_type(animation_choice.currentData())
        )
        syntax_hint = QLabel(
            "Usa x, pi, e y funciones como sin, cos, tan, sqrt, exp y log.", dialog
        )
        syntax_hint.setWordWrap(True)
        syntax_hint.setStyleSheet("color: #aab4c2; font-size: 11px;")
        layout.addWidget(syntax_hint)

        color = QColor("#65d6ff")
        color_button = QPushButton(dialog)

        def update_color_button():
            color_button.setText(color.name())
            color_button.setStyleSheet(
                f"background: {color.name()}; color: #111; padding: 5px;"
            )
            plot_preview.set_color(color)

        def choose_color():
            nonlocal color
            selected = QColorDialog.getColor(color, dialog, "Color de la función")
            if selected.isValid():
                color = selected
                update_color_button()

        color_button.setText("Elegir color")
        color_button.clicked.connect(choose_color)
        update_color_button()
        layout.addWidget(color_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel, parent=dialog
        )
        insert_button = QPushButton("Insertar en previsualización", dialog)
        buttons.addButton(insert_button, QDialogButtonBox.ButtonRole.AcceptRole)
        insert_button.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def validate_expression(expression):
            normalized = expression.strip().replace("^", "**")
            valid = bool(normalized) and len(normalized) <= 256
            if valid:
                try:
                    ast.parse(normalized, mode="eval")
                    valid_samples = 0
                    for sample in range(33):
                        x_value = -7 + 14 * sample / 32
                        try:
                            FunctionPlotPreview.evaluate(normalized, x_value)
                            valid_samples += 1
                        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
                            continue
                    valid = valid_samples > 0
                except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
                    valid = False
            plot_preview.set_function(normalized)
            insert_button.setEnabled(valid)
            if not valid:
                syntax_hint.setText(
                    "Revisa la expresión. Solo se permiten operaciones matemáticas y funciones conocidas."
                )
                syntax_hint.setStyleSheet("color: #ff7b83; font-size: 11px;")
            else:
                syntax_hint.setText(
                    "Usa x, pi, e y funciones como sin, cos, tan, sqrt, exp y log."
                )
                syntax_hint.setStyleSheet("color: #aab4c2; font-size: 11px;")

        function_input.textChanged.connect(validate_expression)
        validate_expression(function_input.text())

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        expression = function_input.text().strip().replace("^", "**")
        duration = max(0.1, float(self.state.get("duration", 10)))
        start = min(duration, self.progress * duration)
        self.state.setdefault("objects", []).append({
            "name": expression,
            "kind": "graph",
            "expression": expression,
            "color": color.name(),
            "show_grid": show_grid.isChecked(),
            "show_axes": show_axes.isChecked(),
            "animation": animation_choice.currentData(),
            "animation_duration": 1.0,
            "start": start,
            "duration": max(0.1, duration - start),
            "visible": True,
            "track": self._track_for_new_object(),
            "position": {"x": 0.5, "y": 0.5},
            "scale": 1.0,
        })
        self.selected_index = len(self.state["objects"]) - 1
        self.on_selection_changed(self.selected_index)
        self.update()
        self._update_related_views()

    def open_equation_generator(self):
        """Crea una ecuación con muestra tipográfica y selector de color."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Agregar ecuación")
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        equation_input = QLineEdit(r"x^2 + y^2 = r^2", dialog)
        equation_input.setMaxLength(256)
        equation_input.setPlaceholderText(r"Ej.: \frac{x^2}{2} + \sqrt{y} = \pi")
        form.addRow("Ecuación", equation_input)
        layout.addLayout(form)

        equation_preview = EquationPreview(dialog)
        layout.addWidget(equation_preview)
        equation_input.textChanged.connect(equation_preview.set_expression)
        hint = QLabel(
            r"Admite potencias, subíndices, \frac, \sqrt, letras griegas y símbolos comunes.",
            dialog,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aab4c2; font-size: 11px;")
        layout.addWidget(hint)

        color = QColor("#f1f4fa")
        color_button = QPushButton(dialog)

        def update_equation_color():
            color_button.setText(color.name())
            color_button.setStyleSheet(
                f"background: {color.name()}; color: #111; padding: 5px;"
            )
            equation_preview.set_color(color)

        def choose_equation_color():
            nonlocal color
            selected = QColorDialog.getColor(color, dialog, "Color de la ecuación")
            if selected.isValid():
                color = selected
                update_equation_color()

        color_button.setText("Elegir color")
        color_button.clicked.connect(choose_equation_color)
        update_equation_color()
        layout.addWidget(color_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel, parent=dialog
        )
        insert_button = QPushButton("Insertar en previsualización", dialog)
        buttons.addButton(insert_button, QDialogButtonBox.ButtonRole.AcceptRole)
        insert_button.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        expression = equation_input.text().strip()
        if not expression:
            return

        duration = max(0.1, float(self.state.get("duration", 10)))
        start = min(duration, self.progress * duration)
        self.state.setdefault("objects", []).append({
            "name": expression[:24],
            "kind": "equation",
            "expression": expression,
            "color": color.name(),
            "start": start,
            "duration": max(0.1, duration - start),
            "visible": True,
            "track": self._track_for_new_object(),
            "position": {"x": 0.5, "y": 0.5},
            "scale": 1.0,
            "font_size": 48,
            "font_family": MANIM_MATH_FONT,
        })
        self.selected_index = len(self.state["objects"]) - 1
        self.on_selection_changed(self.selected_index)
        self.update()
        self._update_related_views()

    @staticmethod
    def _shape_icon(kind, color):
        """Dibuja un icono compacto para una figura del menú."""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if kind == "point":
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(16, 16), 4, 4)
        elif kind == "line":
            painter.drawLine(QPointF(5, 26), QPointF(27, 6))
        elif kind == "vector":
            painter.drawLine(QPointF(6, 25), QPointF(25, 6))
            painter.drawLine(QPointF(25, 6), QPointF(17, 8))
            painter.drawLine(QPointF(25, 6), QPointF(23, 14))
        elif kind == "arrow":
            painter.drawLine(QPointF(4, 16), QPointF(27, 16))
            painter.drawLine(QPointF(27, 16), QPointF(19, 9))
            painter.drawLine(QPointF(27, 16), QPointF(19, 23))
        elif kind == "circle":
            painter.drawEllipse(QPointF(16, 16), 10, 10)
        elif kind == "ellipse":
            painter.drawEllipse(QRectF(4, 10, 24, 12))
        elif kind == "polygon":
            painter.drawPolygon([
                QPointF(16, 4), QPointF(4, 27), QPointF(28, 27),
            ])
        elif kind == "axes":
            painter.drawLine(QPointF(4, 24), QPointF(28, 24))
            painter.drawLine(QPointF(8, 28), QPointF(8, 4))
            painter.drawLine(QPointF(28, 24), QPointF(24, 21))
            painter.drawLine(QPointF(28, 24), QPointF(24, 27))
            painter.drawLine(QPointF(8, 4), QPointF(5, 8))
            painter.drawLine(QPointF(8, 4), QPointF(11, 8))

        painter.end()
        return QIcon(pixmap)

    def _track_for_new_object(self):
        """Usa una pista vacía o crea una para separar los elementos nuevos."""
        tracks = self.state.setdefault("tracks", ["Pista 1"])
        used_tracks = {
            obj.get("track", tracks[0])
            for obj in self.state.get("objects", [])
        }
        unused_track = next(
            (track for track in reversed(tracks) if track not in used_tracks),
            None,
        )
        if unused_track is not None:
            return unused_track

        number = 1
        while f"Pista {number}" in tracks:
            number += 1
        new_track = f"Pista {number}"
        tracks.append(new_track)
        return new_track

    def add_geometric_shape(self, name, kind, expression, color):
        """Añade una figura centrada y sincroniza la lista y el timeline."""
        duration = max(0.1, float(self.state.get("duration", 10)))
        start = min(duration, self.progress * duration)
        self.state.setdefault("objects", []).append({
            "name": name,
            "kind": kind,
            "expression": expression,
            "color": color,
            "start": start,
            "duration": max(0.1, duration - start),
            "visible": True,
            "track": self._track_for_new_object(),
            "position": {"x": 0.5, "y": 0.5},
            "scale": 1.0,
        })
        self.update()
        self._update_related_views()

    def _update_related_views(self):
        view_window = (
            self._original_splitter.window()
            if self._expanded and self._original_splitter is not None
            else self.window()
        )
        for widget in view_window.findChildren(QWidget):
            if widget is not self and getattr(widget, "state", None) is self.state:
                widget.update()
        state_changed = getattr(view_window, "preview_state_changed", None)
        if callable(state_changed):
            state_changed()

    @staticmethod
    def _position_for(obj, index, text_index, frame):
        position = obj.get("position")
        if isinstance(position, dict):
            return {
                "x": float(position.get("x", 0.52)),
                "y": float(position.get("y", 0.54)),
            }
        if obj.get("kind") == "text":
            return {
                "x": 0.035,
                "y": min(0.85, (36 + text_index * 28) / frame["frame_height"]),
            }
        return {"x": 0.52, "y": 0.54}

    def _set_position(self, index, x, y, frame):
        obj = self.state["objects"][index]
        obj["position"] = {
            "x": max(0.0, min(1.0, x / frame["frame_width"])),
            "y": max(0.0, min(1.0, y / frame["frame_height"])),
        }

    @staticmethod
    def _rotation_handle_position(corners):
        top_mid = (corners[0] + corners[1]) / 2
        center = sum(corners, QPointF()) / 4
        direction = top_mid - center
        length = math.hypot(direction.x(), direction.y()) or 1.0
        handle = top_mid + direction * (22 / length)
        if handle.y() < 8:
            handle = QPointF(handle.x(), 8)
        return top_mid, handle

    @staticmethod
    def _animation_effect(kind, progress, entering, frame_width, frame_height):
        """Devuelve desplazamiento, escala, opacidad y giro para una transición."""
        progress = max(0.0, min(1.0, progress))
        remaining = 1.0 - progress
        if kind == "fade":
            return 0.0, 0.0, 1.0, progress if entering else remaining, 0.0
        if kind.startswith("slide_"):
            direction = kind.removeprefix("slide_")
            distance = remaining if entering else progress
            offsets = {
                "left": (-frame_width * distance, 0.0),
                "right": (frame_width * distance, 0.0),
                "up": (0.0, -frame_height * distance),
                "down": (0.0, frame_height * distance),
            }
            dx, dy = offsets[direction]
            return dx, dy, 1.0, 1.0, 0.0
        if kind == "scale":
            factor = 0.15 + 0.85 * (progress if entering else remaining)
            return 0.0, 0.0, factor, 1.0, 0.0
        if kind == "rotate":
            degrees = -360.0 * remaining if entering else 360.0 * progress
            return 0.0, 0.0, 1.0, 1.0, degrees
        return 0.0, 0.0, 1.0, 1.0, 0.0

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        if not self._editing_enabled:
            event.accept()
            return

        point = event.position()
        self._drag_mode = None
        self._resize_corner = None
        self._active_guides.clear()
        if not self._preview_geometry()["viewport"].contains(point):
            self.selected_index = None
            self.update()
            event.accept()
            return
        if self.selected_index in self._object_bounds:
            corners = self._object_selection_corners[self.selected_index]
            _top_mid, rotation_handle = self._rotation_handle_position(corners)
            if math.hypot(
                point.x() - rotation_handle.x(),
                point.y() - rotation_handle.y(),
            ) <= 11:
                self._drag_mode = "rotate"
            handle_size = 10
            corners = tuple(zip(corners, ("top_left", "top_right", "bottom_right", "bottom_left")))
            if self._drag_mode is None:
                for corner, name in corners:
                    handle = QRectF(corner.x() - handle_size, corner.y() - handle_size,
                                    handle_size * 2, handle_size * 2)
                    if handle.contains(point):
                        self._drag_mode = "resize"
                        self._resize_corner = name
                        break

        if self._drag_mode is None:
            hit_index = next(
                (index for index, rect in sorted(
                    self._object_bounds.items(),
                    key=lambda item: item[1].width() * item[1].height(),
                )
                 if rect.adjusted(-5, -5, 5, 5).contains(point)),
                None,
            )
            if hit_index is None:
                self.selected_index = None
                self.update()
                event.accept()
                return
            self.selected_index = hit_index
            self._drag_mode = "move"

        self._drag_origin = point
        self._drag_position = dict(self._object_positions[self.selected_index])
        self._drag_bounds = QRectF(self._object_frame_bounds[self.selected_index])
        obj = self.state["objects"][self.selected_index]
        self._drag_scale = float(obj.get("scale", 1.0))
        self._drag_font_size = int(obj.get("font_size", 48))
        self._drag_rotation = float(obj.get("rotation", 0.0))
        if self._drag_mode == "rotate":
            anchor = self._object_rotation_anchors[self.selected_index]
            self._rotation_origin_angle = math.atan2(
                point.y() - anchor.y(), point.x() - anchor.x(),
            )
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None or self.selected_index is None:
            return super().mouseMoveEvent(event)

        frame = self._preview_geometry()
        obj = self.state["objects"][self.selected_index]
        dx = event.position().x() - self._drag_origin.x()
        dy = event.position().y() - self._drag_origin.y()
        if self._drag_mode == "rotate":
            anchor = self._object_rotation_anchors[self.selected_index]
            current_angle = math.atan2(
                event.position().y() - anchor.y(),
                event.position().x() - anchor.x(),
            )
            # Qt dibuja con el eje Y hacia abajo; invierte el signo para
            # guardar ángulos positivos en el sentido matemático de Manim.
            delta = -math.degrees(current_angle - self._rotation_origin_angle)
            rotation = (self._drag_rotation + delta + 180) % 360 - 180
            nearest_axis = round(rotation / 90) * 90
            self._active_guides.clear()
            if abs(rotation - nearest_axis) <= 4:
                rotation = (nearest_axis + 180) % 360 - 180
                pivot_x = (anchor.x() - frame["x"]) / frame["scale_x"]
                pivot_y = (anchor.y() - frame["y"]) / frame["scale_y"]
                self._active_guides["vertical"] = pivot_x
                self._active_guides["horizontal"] = pivot_y
            obj["rotation"] = rotation
        elif self._drag_mode == "move":
            bounds = self._drag_bounds
            x = self._drag_position["x"] * frame["frame_width"] + dx / frame["scale_x"]
            y = self._drag_position["y"] * frame["frame_height"] + dy / frame["scale_y"]
            if obj.get("kind") == "text":
                x = max(0, min(frame["frame_width"] - bounds.width(), x))
                y = max(0, min(frame["frame_height"] - bounds.height(), y))
            else:
                x = max(bounds.width() / 2, min(frame["frame_width"] - bounds.width() / 2, x))
                y = max(bounds.height() / 2, min(frame["frame_height"] - bounds.height() / 2, y))
            # Ajusta el ancla del objeto al centro y muestra guías magnéticas.
            anchor_x = self._drag_position["x"] * frame["frame_width"]
            anchor_y = self._drag_position["y"] * frame["frame_height"]
            # El giro y las guías usan el centro visual del elemento. En los
            # textos la posición guardada es la esquina superior izquierda.
            center_offset_x = bounds.center().x() - anchor_x
            center_offset_y = bounds.center().y() - anchor_y
            snap_tolerance = 8
            self._active_guides.clear()
            targets_x = [(frame["frame_width"] / 2, None)]
            targets_y = [(frame["frame_height"] / 2, None)]
            for other_index, other_center in self._object_alignment_centers.items():
                if other_index != self.selected_index:
                    targets_x.append((other_center.x(), other_index))
                    targets_y.append((other_center.y(), other_index))
            center_x, center_y = x + center_offset_x, y + center_offset_y
            nearest_x = min(targets_x, key=lambda item: abs(item[0] - center_x))
            nearest_y = min(targets_y, key=lambda item: abs(item[0] - center_y))
            if abs((nearest_x[0] - center_x) * frame["scale_x"]) <= snap_tolerance:
                x += nearest_x[0] - center_x
                self._active_guides["vertical"] = nearest_x[0]
            if abs((nearest_y[0] - center_y) * frame["scale_y"]) <= snap_tolerance:
                y += nearest_y[0] - center_y
                self._active_guides["horizontal"] = nearest_y[0]
            self._set_position(
                self.selected_index,
                x,
                y,
                frame,
            )
        else:
            self._active_guides.clear()
            self._resize_selected(obj, event.position(), frame)
        self.update()
        self._update_related_views()
        event.accept()

    def _resize_selected(self, obj, point, frame):
        bounds = self._drag_bounds
        signs = {
            "top_left": (-1, -1),
            "top_right": (1, -1),
            "bottom_right": (1, 1),
            "bottom_left": (-1, 1),
        }
        sign_x, sign_y = signs[self._resize_corner]
        pointer = QPointF(
            (point.x() - frame["x"]) / frame["scale_x"],
            (point.y() - frame["y"]) / frame["scale_y"],
        )
        rotation_anchor = self._object_rotation_anchors[self.selected_index]
        anchor_x = (rotation_anchor.x() - frame["x"]) / frame["scale_x"]
        anchor_y = (rotation_anchor.y() - frame["y"]) / frame["scale_y"]
        inverse_rotation = QTransform()
        inverse_rotation.translate(anchor_x, anchor_y)
        inverse_rotation.rotate(float(obj.get("rotation", 0.0)))
        inverse_rotation.translate(-anchor_x, -anchor_y)
        pointer = inverse_rotation.map(pointer)
        pointer_x, pointer_y = pointer.x(), pointer.y()
        fixed_x = bounds.right() if sign_x < 0 else bounds.left()
        fixed_y = bounds.bottom() if sign_y < 0 else bounds.top()
        new_width = max(8.0, abs(pointer_x - fixed_x))
        new_height = max(8.0, abs(pointer_y - fixed_y))
        ratio_x = new_width / max(1.0, bounds.width())
        ratio_y = new_height / max(1.0, bounds.height())
        factor = (ratio_x + ratio_y) / 2

        if obj.get("kind") == "text":
            original_size = max(1, self._drag_font_size)
            new_size = max(8, min(300, round(original_size * factor)))
            factor = new_size / original_size
            obj["font_size"] = new_size
            width = bounds.width() * factor
            height = bounds.height() * factor
            left = fixed_x - width if sign_x < 0 else fixed_x
            top = fixed_y - height if sign_y < 0 else fixed_y
            left = max(0, min(frame["frame_width"] - width, left))
            top = max(0, min(frame["frame_height"] - height, top))
            self._set_position(self.selected_index, left, top, frame)
        else:
            factor = max(0.1, min(4.0, factor))
            obj["scale"] = self._drag_scale * factor
            center_x = fixed_x + sign_x * bounds.width() * factor / 2
            center_y = fixed_y + sign_y * bounds.height() * factor / 2
            width = bounds.width() * factor
            height = bounds.height() * factor
            center_x = max(width / 2, min(frame["frame_width"] - width / 2, center_x))
            center_y = max(height / 2, min(frame["frame_height"] - height / 2, center_y))
            self._set_position(self.selected_index, center_x, center_y, frame)

    def mouseReleaseEvent(self, event):
        if self._drag_mode is not None:
            self._drag_mode = None
            self._drag_origin = None
            self._drag_position = None
            self._drag_bounds = None
            self._active_guides.clear()
            self.update()
            self._update_related_views()
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
