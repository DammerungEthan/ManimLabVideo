"""Diálogos y acciones para insertar elementos en la escena."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
from manim_editor.interfaz.vista_grafica_funcion import FunctionPlotPreview
from manim_editor.interfaz.texto_matematico import EquationPreview
from manim_editor.tipografia import MANIM_MATH_FONT, MANIM_TEXT_FONT


class CreadorElementos:
    """Añade texto, ecuaciones, funciones y figuras al estado del proyecto."""

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
