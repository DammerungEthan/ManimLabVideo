"""Catálogo visual de elementos que se pueden insertar en la escena."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ElementPreset:
    label: str
    kind: str
    expression: str = ""
    color: str = "#65d6ff"

    @property
    def category(self):
        """Agrupa el catálogo para que insertar elementos sea rápido."""
        if self.kind == "graph":
            return "Gráficas"
        if self.kind in {"text", "equation"}:
            return "Texto y fórmulas"
        if self.kind in {"axes", "number_plane", "table"}:
            return "Herramientas matemáticas"
        return "Geometría"


ELEMENTS = [
    ElementPreset("Función seno", "graph", "sin(x)"),
    ElementPreset("Seno doble", "graph", "sin(2*x)"),
    ElementPreset("Función coseno", "graph", "cos(x)"),
    ElementPreset("Tangente", "graph", "tan(x)"),
    ElementPreset("Parábola", "graph", "x^2"),
    ElementPreset("Función cúbica", "graph", "x^3 / 8"),
    ElementPreset("Inversa", "graph", "1/x"),
    ElementPreset("Exponencial", "graph", "exp(x)"),
    ElementPreset("Campana gaussiana", "graph", "exp(-x^2)"),
    ElementPreset("Logaritmo", "graph", "log(x)"),
    ElementPreset("Raíz cuadrada", "graph", "sqrt(x)"),
    ElementPreset("Raíz de valor absoluto", "graph", "sqrt(abs(x))"),
    ElementPreset("Valor absoluto", "graph", "abs(x)"),
    ElementPreset("Texto", "text", "Escribe aquí", "#f1f4fa"),
    ElementPreset("Ecuación", "equation", r"x^2 + y^2 = r^2", "#f1f4fa"),
    ElementPreset("Título", "text", "Título de la escena", "#f1f4fa"),
    ElementPreset("Etiqueta", "text", "Etiqueta", "#f1f4fa"),
    ElementPreset("Punto", "point", "A", "#ffbd69"),
    ElementPreset("Vector", "vector", "v", "#ffbd69"),
    ElementPreset("Recta", "line", "y = x"),
    ElementPreset("Flecha", "arrow", "", "#ffbd69"),
    ElementPreset("Círculo", "circle"),
    ElementPreset("Elipse", "ellipse"),
    ElementPreset("Cuadrado", "square"),
    ElementPreset("Rectángulo", "rectangle"),
    ElementPreset("Polígono", "polygon"),
    ElementPreset("Triángulo", "polygon", "Triángulo", "#ffbd69"),
    ElementPreset("Ejes cartesianos", "axes", "", "#8290a5"),
    ElementPreset("Plano cartesiano", "number_plane", "", "#8290a5"),
    ElementPreset("Tabla", "table"),
    ElementPreset("Imagen", "image"),
    ElementPreset("Grupo", "group"),
]
