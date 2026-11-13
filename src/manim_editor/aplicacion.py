"""Punto de entrada de la aplicación de escritorio."""
import sys

from PySide6.QtWidgets import QApplication

from manim_editor.interfaz.ventana_principal import MainWindow


def main() -> int:
    """Crea la aplicación y muestra la ventana principal."""
    application = QApplication(sys.argv)
    application.setApplicationName("Manim Editor")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
