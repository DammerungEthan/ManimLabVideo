"""Widget de vista previa para escenas matemáticas."""
import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QPushButton, QScrollBar, QSpinBox, QSplitter, QWidget,
)


class Preview(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.progress = 0.38
        self.setMinimumSize(420, 270)
        self._expanded = False
        self._original_parent = None
        self._original_layout = None
        self._original_index = -1
        self._original_splitter = None
        self._original_splitter_sizes = None
        self._hidden_app_widgets = []
        self._original_window_flags = self.windowFlags()
        self.selected_index = None
        self._object_bounds = {}
        self._object_frame_bounds = {}
        self._object_positions = {}
        self._drag_mode = None
        self._drag_origin = None
        self._drag_position = None
        self._drag_bounds = None
        self._drag_scale = 1.0
        self._drag_font_size = 16
        self._resize_corner = None
        self._active_guides = set()
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
        for control in (self.size_button, self.text_button, self.zoom_bar, self.zoom_label):
            control.setVisible(not render_only)
        if render_only:
            return
        right = self.width() - 8
        button_x = right - self.size_button.width()
        first_y = 8
        self.size_button.move(button_x, first_y)
        self.text_button.move(
            right - self.text_button.width(),
            first_y + self.size_button.height() + 8,
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

    def _find_containing_layout(self, layout):
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is self:
                return layout, index
            child_layout = item.layout()
            if child_layout is not None:
                result = self._find_containing_layout(child_layout)
                if result is not None:
                    return result
        return None

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
        if font_family.findText("Computer Modern", Qt.MatchFlag.MatchFixedString) < 0:
            font_family.addItem("Computer Modern")
        font_family.setCurrentText("Noto Serif")
        font_size = QSpinBox()
        font_size.setRange(8, 300)
        font_size.setValue(42)
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
        self.state.setdefault("objects", []).append({
            "name": expression[:24],
            "kind": "text",
            "expression": expression,
            "color": "#f1f4fa",
            "start": 0,
            "duration": max(1, int(self.state.get("duration", 10))),
            "visible": True,
            "position": {"x": 0.04, "y": min(0.85, (36 + text_count * 56) / frame["frame_height"])},
            "scale": 1.0,
            "font_family": font_family.currentText(),
            "font_size": font_size.value(),
            "font_weight": font_weight.currentData(),
        })
        self.update()
        self._update_related_views()

    def _update_related_views(self):
        view_window = self._original_parent.window() if self._expanded else self.window()
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

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

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
            rect = self._object_bounds[self.selected_index]
            handle_size = 10
            corners = (
                (rect.topLeft(), "top_left"),
                (rect.topRight(), "top_right"),
                (rect.bottomRight(), "bottom_right"),
                (rect.bottomLeft(), "bottom_left"),
            )
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
        self._drag_font_size = int(obj.get("font_size", 16))
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None or self.selected_index is None:
            return super().mouseMoveEvent(event)

        frame = self._preview_geometry()
        obj = self.state["objects"][self.selected_index]
        dx = event.position().x() - self._drag_origin.x()
        dy = event.position().y() - self._drag_origin.y()
        if self._drag_mode == "move":
            bounds = self._drag_bounds
            x = self._drag_position["x"] * frame["frame_width"] + dx / frame["scale_x"]
            y = self._drag_position["y"] * frame["frame_height"] + dy / frame["scale_y"]
            if obj.get("kind") == "text":
                x = max(0, min(frame["frame_width"] - bounds.width(), x))
                y = max(0, min(frame["frame_height"] - bounds.height(), y))
            else:
                x = max(bounds.width() / 2, min(frame["frame_width"] - bounds.width() / 2, x))
                y = max(bounds.height() / 2, min(frame["frame_height"] - bounds.height() / 2, y))
            anchor_x = self._drag_position["x"] * frame["frame_width"]
            anchor_y = self._drag_position["y"] * frame["frame_height"]
            center_offset_x = bounds.center().x() - anchor_x
            center_offset_y = bounds.center().y() - anchor_y
            center_x = frame["frame_width"] / 2 - center_offset_x
            center_y = frame["frame_height"] / 2 - center_offset_y
            snap_tolerance = 8
            self._active_guides.clear()
            if abs((x - center_x) * frame["scale_x"]) <= snap_tolerance:
                x = center_x
                self._active_guides.add("vertical")
            if abs((y - center_y) * frame["scale_y"]) <= snap_tolerance:
                y = center_y
                self._active_guides.add("horizontal")
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
        pointer_x = (point.x() - frame["x"]) / frame["scale_x"]
        pointer_y = (point.y() - frame["y"]) / frame["scale_y"]
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
        p.save()
        p.setClipRect(viewport)
        p.fillRect(frame_rect, QColor("#000000"))
        p.translate(frame["x"], frame["y"])
        p.scale(frame["scale_x"], frame["scale_y"])

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

            x = position["x"] * frame_width
            y = position["y"] * frame_height
            scale = base_scale * float(obj.get("scale", 1.0))
            if kind == "axes":
                p.setPen(QPen(QColor(obj.get("color", "#8290a5")), 1))
                p.drawLine(int(x - scale * 1.3), int(y), int(x + scale * 1.3), int(y))
                p.drawLine(int(x), int(y - scale * 1.15), int(x), int(y + scale * 1.15))
                bounds = QRectF(x - scale * 1.3, y - scale * 1.15,
                                scale * 2.6, scale * 2.3)
            elif kind == "graph":
                funcs = {
                    "sin(x)": math.sin,
                    "cos(x)": math.cos,
                    "tan(x)": lambda value: math.sin(value) * .5,
                    "x^2": lambda value: ((value - math.pi) ** 2 / 5) - 1,
                }
                expression = obj.get("expression", "sin(x)").strip().lower()
                fn = funcs.get(expression, math.sin)
                points = [
                    (x - scale + 2 * scale * i / 219,
                     y - scale * .48 * fn(i / 219 * math.tau * 1.5))
                    for i in range(max(2, int(220 * self.progress)))
                ]
                p.setPen(QPen(QColor(obj.get("color", "#65d6ff")), 3))
                for start, end in zip(points, points[1:]):
                    p.drawLine(int(start[0]), int(start[1]), int(end[0]), int(end[1]))
                bounds = QRectF(x - scale, y - scale * .5, scale * 2, scale)
            elif kind == "text":
                font = QFont(
                    obj.get("font_family", "Sans Serif"),
                    obj.get("font_size", 16),
                    QFont.Weight(obj.get("font_weight", int(QFont.Weight.DemiBold))),
                )
                metrics = QFontMetricsF(font)
                expression = obj.get("expression", "")
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
                font = QFont("Sans Serif", 24)
                metrics = QFontMetricsF(font)
                bounds = QRectF(x, y, max(48.0, metrics.horizontalAdvance(expression) + 20), 48)
                p.setPen(QPen(QColor(obj.get("color", "#65d6ff")), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(bounds)
                p.setFont(font)
                p.drawText(x + 10, y + 32, expression)
            else:
                continue

            self._object_positions[index] = position
            self._object_frame_bounds[index] = bounds
            self._object_bounds[index] = QRectF(
                frame["x"] + bounds.x() * frame["scale_x"],
                frame["y"] + bounds.y() * frame["scale_y"],
                bounds.width() * frame["scale_x"],
                bounds.height() * frame["scale_y"],
            )

        p.restore()
        if self._active_guides:
            p.save()
            p.setClipRect(frame_rect)
            guide_pen = QPen(QColor("#ff5f87"), 1, Qt.PenStyle.DashLine)
            p.setPen(guide_pen)
            if "vertical" in self._active_guides:
                center_x = frame_rect.center().x()
                p.drawLine(int(center_x), int(frame_rect.top()),
                           int(center_x), int(frame_rect.bottom()))
            if "horizontal" in self._active_guides:
                center_y = frame_rect.center().y()
                p.drawLine(int(frame_rect.left()), int(center_y),
                           int(frame_rect.right()), int(center_y))
            p.restore()
        p.setPen(QPen(QColor("#536174"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(frame_rect)
        if self.selected_index in self._object_bounds:
            selected_rect = self._object_bounds[self.selected_index]
            p.setPen(QPen(QColor("#65d6ff"), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(selected_rect)
            p.setBrush(QColor("#e7ebf2"))
            for corner in (selected_rect.topLeft(), selected_rect.topRight(),
                           selected_rect.bottomRight(), selected_rect.bottomLeft()):
                p.drawRect(QRectF(corner.x() - 4, corner.y() - 4, 8, 8))
