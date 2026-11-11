"""Exporta la previsualización gráfica como video H.264 mediante ffmpeg."""
import os
import shutil
import subprocess
import tempfile

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from manim_editor.ui.preview import Preview


def export_preview_video(state, output_path, parent, playback_timer):
    """Renderiza cada instante del preview y devuelve (resultado, detalle)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "error", "No se encontró ffmpeg. Instálalo y vuelve a intentarlo."

    width = max(1, int(state.get("width", 1920)))
    height = max(1, int(state.get("height", 1080)))
    duration = max(0.1, float(state.get("duration", 10)))
    fps = 30
    frame_count = max(1, int(round(duration * fps)))
    temporary_path = None
    process = None
    canceled = False
    error_message = None
    was_playing = playback_timer.isActive()
    playback_timer.stop()

    progress = QProgressDialog("Renderizando fotogramas…", "Cancelar", 0, frame_count, parent)
    progress.setWindowTitle("Exportar video MP4")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.show()

    try:
        output_directory = os.path.dirname(os.path.abspath(output_path))
        with tempfile.NamedTemporaryFile(
            prefix=".manim-editor-", suffix=".mp4", dir=output_directory, delete=False
        ) as temporary:
            temporary_path = temporary.name

        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pixel_format", "rgba",
            "-video_size", f"{width}x{height}", "-framerate", str(fps),
            "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            temporary_path,
        ]
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )

        render_preview = Preview(state)
        render_preview.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        render_preview.resize(width + 36, height + 48)
        render_preview.selected_index = None
        render_preview.size_button.hide()
        render_preview.text_button.hide()
        render_preview.show()
        QApplication.processEvents()

        for frame_number in range(frame_count):
            if progress.wasCanceled():
                canceled = True
                break
            render_preview.progress = frame_number / max(1, frame_count - 1)
            image = QImage(width + 36, height + 48, QImage.Format.Format_RGBA8888)
            image.fill(QColor("#000000"))
            painter = QPainter(image)
            try:
                render_preview.render(painter, QPoint(0, 0))
            finally:
                painter.end()
            process.stdin.write(image.copy(18, 0, width, height).bits().tobytes())
            progress.setValue(frame_number + 1)
            QApplication.processEvents()

        if canceled:
            process.stdin.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        else:
            process.stdin.close()
            error_output = process.stderr.read().decode("utf-8", errors="replace").strip()
            return_code = process.wait()
            if return_code:
                raise RuntimeError(error_output or f"ffmpeg terminó con código {return_code}.")
            os.replace(temporary_path, output_path)
            temporary_path = None
    except (OSError, RuntimeError, ValueError) as error:
        error_message = str(error)
        if process and process.poll() is None:
            process.kill()
            process.wait()
    finally:
        progress.close()
        if was_playing:
            playback_timer.start()
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)

    if error_message:
        return "error", error_message
    return ("canceled", "") if canceled else ("success", "")


def show_export_result(parent, result, output_path):
    """Muestra el resultado del diálogo de exportación."""
    status, detail = result
    if status == "error":
        QMessageBox.critical(parent, "No se pudo exportar el video", detail)
    elif status == "canceled":
        QMessageBox.information(parent, "Exportación cancelada", "Se canceló la exportación.")
    else:
        QMessageBox.information(parent, "Video exportado", f"El video se guardó en:\n{output_path}")
