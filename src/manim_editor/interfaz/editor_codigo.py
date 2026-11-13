"""Editor de Python con resaltado e indentación básica para escenas Manim."""

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit


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

