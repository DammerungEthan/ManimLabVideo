"""Carga y guardado del formato .manimproj."""
import json
from pathlib import Path

from manim_editor.models.project import normalize_project


def load_project(path: str | Path) -> dict:
    """Lee JSON y completa los campos opcionales del formato actual."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalize_project(data)


def save_project(path: str | Path, project: dict) -> None:
    """Guarda el estado del proyecto en JSON legible para personas."""
    Path(path).write_text(
        json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
    )
