"""Renderiza escenas Python con Manim fuera del hilo de la interfaz."""
import ast
import os
import signal
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal


def _scene_class_name(source):
    """Devuelve la primera clase con construct y una clase base."""
    tree = ast.parse(source)
    scene_bases = {
        "Scene", "ThreeDScene", "MovingCameraScene", "ZoomedScene", "VectorScene",
        "LinearTransformationScene", "SpecialThreeDScene", "SampleSpaceScene",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "manim":
            for imported in node.names:
                if imported.name.endswith("Scene"):
                    scene_bases.add(imported.asname or imported.name)
    candidates = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        has_construct = any(
            isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and member.name == "construct"
            for member in node.body
        )
        base_names = [
            base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            for base in node.bases
        ]
        if has_construct and node.bases:
            candidates.append((node.name, any(name.endswith("Scene") or name in scene_bases for name in base_names)))
    for name, is_scene in candidates:
        if is_scene:
            return name
    if candidates:
        return candidates[0][0]
    raise ValueError("No encontré una clase de escena con un método construct().")


def _ensure_static_scene_renders(source, scene_name):
    """Añade una pausa breve a escenas que solo usan self.add()."""
    tree = ast.parse(source)
    scene = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == scene_name),
        None,
    )
    if scene is None:
        return source
    construct = next(
        (node for node in scene.body if isinstance(node, ast.FunctionDef) and node.name == "construct"),
        None,
    )
    if construct is None or not construct.body:
        return source
    has_timing = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr in {"play", "wait"}
        for statement in construct.body
        for node in ast.walk(statement)
    )
    if has_timing:
        return source

    lines = source.splitlines()
    last_statement = construct.body[-1]
    insert_at = (last_statement.lineno - 1) if isinstance(last_statement, ast.Return) else last_statement.end_lineno
    indent = " " * (construct.col_offset + 4)
    lines.insert(insert_at, f"{indent}self.wait(0.25)")
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


class ManimRenderWorker(QThread):
    """Ejecuta el código y extrae los fotogramas para el visor."""

    render_done = Signal(bool, str, object, str, str, str)

    def __init__(self, source, width, height, working_directory, parent=None):
        super().__init__(parent)
        self.source = source
        self.width = max(240, int(width))
        self.height = max(240, int(height))
        self.working_directory = Path(working_directory)
        self._process = None
        self._cancelled = False

    def cancel(self):
        """Detiene el proceso externo si la ventana se está cerrando."""
        self._cancelled = True
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass

    def _run_command(self, command, timeout):
        process = subprocess.Popen(
            command,
            cwd=self.working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=(os.name == "posix"),
        )
        self._process = process
        if self._cancelled:
            self.cancel()
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.communicate()
            raise RuntimeError("Manim excedió el límite de 10 minutos de renderizado.")
        finally:
            self._process = None
        return process.returncode, stdout, stderr

    def run(self):
        render_directory = Path(tempfile.mkdtemp(prefix="manim-editor-render-"))
        scene_name = ""
        try:
            scene_name = _scene_class_name(self.source)
            rendered_source = _ensure_static_scene_renders(self.source, scene_name)
            source_path = render_directory / "user_scene.py"
            media_directory = render_directory / "media"
            source_path.write_text(rendered_source, encoding="utf-8")
            command = [
                sys.executable, "-m", "manim", "render",
                "--disable_caching", "--verbosity", "warning",
                "--fps", "30", "--resolution", f"{self.width},{self.height}",
                "--format", "mp4", "--media_dir", str(media_directory),
            ]
            project_config = self.working_directory / "manim.cfg"
            if project_config.is_file():
                command.extend(["--config_file", str(project_config)])
            command.extend([str(source_path), scene_name])
            return_code, stdout, stderr = self._run_command(command, 600)
            if return_code:
                details = (stderr + "\n" + stdout).strip()
                raise RuntimeError(details or "Manim terminó con un error.")

            video_candidates = [
                path for path in media_directory.rglob("*.mp4")
                if "partial_movie_files" not in path.parts
            ]
            if not video_candidates:
                raise RuntimeError("Manim terminó, pero no generó un video MP4.")
            named_videos = [path for path in video_candidates if path.stem == scene_name]
            video_path = max(named_videos or video_candidates, key=lambda path: path.stat().st_mtime)
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("No se encontró ffmpeg para preparar los fotogramas de la vista previa.")

            frame_pattern = render_directory / "frame_%06d.png"
            extraction_code, _stdout, extraction_error = self._run_command(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video_path),
                    "-vsync", "0", "-start_number", "0", str(frame_pattern),
                ],
                300,
            )
            if extraction_code:
                raise RuntimeError(extraction_error.strip() or "ffmpeg no pudo extraer los fotogramas.")
            frames = sorted(render_directory.glob("frame_*.png"))
            if not frames:
                raise RuntimeError("El render no contiene fotogramas para mostrar.")

            self.render_done.emit(
                True, str(render_directory), [str(frame) for frame in frames],
                str(video_path), scene_name, "",
            )
        except (OSError, RuntimeError, SyntaxError, ValueError) as error:
            shutil.rmtree(render_directory, ignore_errors=True)
            self.render_done.emit(False, "", [], "", scene_name, str(error))
