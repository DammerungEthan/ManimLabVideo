"""Conversión ligera de LaTeX común a texto matemático y su preview gráfico."""
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget
from manim_editor.typography import MANIM_MATH_FONT, MANIM_TEXT_FONT


GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "theta": "θ", "lambda": "λ", "mu": "μ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "phi": "φ",
    "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Sigma": "Σ", "Phi": "Φ", "Omega": "Ω",
}
SYMBOLS = {
    "infty": "∞", "cdot": "·", "times": "×", "div": "÷",
    "pm": "±", "mp": "∓", "le": "≤", "leq": "≤", "ge": "≥",
    "geq": "≥", "neq": "≠", "approx": "≈", "equiv": "≡",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "partial": "∂", "nabla": "∇", "sum": "∑", "prod": "∏",
    "int": "∫", "in": "∈", "notin": "∉", "forall": "∀",
    "exists": "∃", "emptyset": "∅", "cup": "∪", "cap": "∩",
}
SUPERSCRIPT_CHARS = set("0123456789+-=()nixy")
SUBSCRIPT_CHARS = set("0123456789+-=()nixy")
SUPERSCRIPTS = str.maketrans(
    "0123456789+-=()nixy", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱˣʸ"
)
SUBSCRIPTS = str.maketrans(
    "0123456789+-=()nixy", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ"
)


def format_math_expression(expression):
    """Convierte comandos LaTeX usuales a glifos, raíces y fracciones legibles."""
    source = expression.strip()
    position = 0

    def read_group():
        nonlocal position
        while position < len(source) and source[position].isspace():
            position += 1
        if position >= len(source):
            return ""
        if source[position] != "{":
            return read_atom()
        position += 1
        content = read_sequence(stop_at_brace=True)
        if position < len(source) and source[position] == "}":
            position += 1
        return content

    def read_atom():
        nonlocal position
        if position >= len(source):
            return ""
        if source[position] == "{":
            return read_group()
        if source[position] == "\\":
            position += 1
            match = re.match(r"[A-Za-z]+|.", source[position:])
            if not match:
                return ""
            command = match.group(0)
            position += len(command)
            if command in {"frac", "dfrac", "tfrac"}:
                numerator, denominator = read_group(), read_group()
                return f"({numerator})⁄({denominator})"
            if command == "sqrt":
                return f"√({read_group()})"
            if command in {"text", "mathrm", "mathbf", "mathit", "operatorname"}:
                return read_group()
            if command in {"left", "right", "displaystyle", "limits"}:
                return ""
            if command in GREEK:
                return GREEK[command]
            if command in SYMBOLS:
                return SYMBOLS[command]
            return command
        char = source[position]
        position += 1
        return char

    def read_sequence(stop_at_brace=False):
        nonlocal position
        output = []
        while position < len(source):
            char = source[position]
            if stop_at_brace and char == "}":
                break
            if char in "^_":
                position += 1
                value = read_group()
                table = SUPERSCRIPTS if char == "^" else SUBSCRIPTS
                converted = value.translate(table)
                supported_chars = SUPERSCRIPT_CHARS if char == "^" else SUBSCRIPT_CHARS
                supported = all(item in supported_chars for item in value)
                output.append(converted if supported else f"{char}({value})")
                continue
            output.append(read_atom())
        return "".join(output)

    return read_sequence()


class EquationPreview(QWidget):
    """Vista previa centrada de una ecuación, con color editable en vivo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.expression = r"x^2 + y^2 = r^2"
        self.color = QColor("#f1f4fa")
        self.setMinimumHeight(150)

    def set_expression(self, expression):
        self.expression = expression
        self.update()

    def set_color(self, color):
        self.color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#101318"))
        painter.drawRoundedRect(self.rect(), 8, 8)
        painter.setPen(QColor("#708096"))
        painter.setFont(QFont(MANIM_TEXT_FONT, 9))
        painter.drawText(12, 20, "VISTA PREVIA DE LA ECUACIÓN")
        font = QFont(MANIM_MATH_FONT, 28)
        font.setStyle(QFont.Style.StyleItalic)
        painter.setFont(font)
        painter.setPen(self.color)
        painter.drawText(
            self.rect().adjusted(12, 28, -12, -12),
            Qt.AlignmentFlag.AlignCenter,
            format_math_expression(self.expression) or "…",
        )
