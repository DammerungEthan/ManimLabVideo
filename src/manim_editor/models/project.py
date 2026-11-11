"""Modelo y valores iniciales del formato de proyecto."""
from copy import deepcopy
from manim_editor.typography import MANIM_MATH_FONT, MANIM_TEXT_FONT

DEFAULT_PROJECT = {
    "version": 1,
    "name": "Proyecto sin guardar",
    "duration": 10,
    "format": "youtube",
    "width": 1920,
    "height": 1080,
    "tracks": ["Pista 1", "Pista 2", "Pista 3", "Pista 4"],
    "objects": [
        {"name": "Gráfica seno", "kind": "graph", "expression": "sin(x)", "color": "#65d6ff", "start": 0, "duration": 8, "visible": True, "track": "Pista 1", "position": {"x": 0.52, "y": 0.54}, "scale": 1.0, "rotation": 0.0, "opacity": 1.0, "stroke_width": 3.0},
        {"name": "Ejes", "kind": "axes", "expression": "", "color": "#8290a5", "start": 0, "duration": 10, "visible": True, "track": "Pista 2", "position": {"x": 0.52, "y": 0.54}, "scale": 1.0, "rotation": 0.0, "opacity": 1.0, "stroke_width": 3.0},
        {"name": "Título", "kind": "text", "expression": "f(x) = sin(x)", "color": "#f1f4fa", "start": 0, "duration": 10, "visible": True, "track": "Pista 3", "position": {"x": 0.035, "y": 0.08}, "scale": 1.0, "rotation": 0.0, "opacity": 1.0, "stroke_width": 3.0, "font_size": 48, "font_family": "sans-serif", "font_weight": 400},
    ],
}


def new_project() -> dict:
    """Crea un proyecto independiente con los valores iniciales."""
    return deepcopy(DEFAULT_PROJECT)


def normalize_project(data: dict) -> dict:
    """Valida la estructura básica y completa campos opcionales antiguos."""
    if not isinstance(data, dict) or not isinstance(data.get("objects"), list):
        raise ValueError("El archivo no contiene un proyecto válido.")
    project = new_project()
    project.update(data)
    project.setdefault("tracks", ["Pista 1", "Pista 2", "Pista 3", "Pista 4"])
    for obj in project["objects"]:
        obj.setdefault("visible", True)
        obj.setdefault("start", 0)
        obj.setdefault("duration", project["duration"])
        obj.setdefault("color", "#65d6ff")
        obj.setdefault("expression", "")
        obj.setdefault("track", "Pista 1")
        obj.setdefault("position", {"x": 0.52, "y": 0.54})
        obj.setdefault("scale", 1.0)
        obj.setdefault("rotation", 0.0)
        obj.setdefault("opacity", 1.0)
        obj.setdefault("stroke_width", 3.0)
        obj.setdefault("font_size", 48)
        default_font = MANIM_MATH_FONT if obj.get("kind") == "equation" else MANIM_TEXT_FONT
        obj.setdefault("font_family", default_font)
        obj.setdefault("font_weight", 400)
        obj.setdefault("animation_in", "none")
        obj.setdefault("animation_out", "none")
        obj.setdefault("animation_in_duration", 0.5)
        obj.setdefault("animation_out_duration", 0.5)
        if obj["track"] not in project["tracks"]:
            project["tracks"].append(obj["track"])
    return project
