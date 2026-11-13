"""Gestos de ratón y geometría de selección del lienzo."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QTransform


class InteraccionLienzo:
    """Mueve, escala, rota y selecciona elementos de la previsualización."""

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
