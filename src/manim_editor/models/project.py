"""Modelo y valores iniciales del formato de proyecto."""
from copy import deepcopy

DEFAULT_PROJECT = {
    "version": 1,
    "name": "Proyecto sin guardar",
    "duration": 10,
    "format": "youtube",
    "width": 1920,
    "height": 1080,
    "tracks": ["Pista 1"],
    "objects": [
        {"name": "Gráfica seno", "kind": "graph", "expression": "sin(x)", "color": "#65d6ff", "start": 0, "duration": 8, "visible": True},
        {"name": "Ejes", "kind": "axes", "expression": "", "color": "#8290a5", "start": 0, "duration": 10, "visible": True},
        {"name": "Título", "kind": "text", "expression": "f(x) = sin(x)", "color": "#f1f4fa", "start": 0, "duration": 10, "visible": True},
    ],
}


def new_project() -> dict:
    """Crea un proyecto independiente con los valores iniciales."""
    return deepcopy(DEFAULT_PROJECT)


def normalize_project(data: dict) -> dict:
    """Completa campos opcionales para mantener compatibilidad entre versiones."""
    if not isinstance(data, dict) or not isinstance(data.get("objects"), list):
        raise ValueError("El archivo no contiene un proyecto válido.")
    project = new_project()
    project.update(data)
    project.setdefault("tracks", ["Pista 1"])
    for obj in project["objects"]:
        obj.setdefault("visible", True)
        obj.setdefault("start", 0)
        obj.setdefault("duration", project["duration"])
        obj.setdefault("color", "#65d6ff")
        obj.setdefault("expression", "")
        obj.setdefault("track", "Pista 1")
        if obj["track"] not in project["tracks"]:
            project["tracks"].append(obj["track"])
    return project
