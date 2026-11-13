"""Vista previa aislada para gráficas de funciones matemáticas."""

import ast
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


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


