# Manim Editor

Editor de escritorio multiplataforma para crear y editar animaciones con Manim, con una experiencia basada en línea de tiempo y previsualización.

> Estado: prototipo de interfaz. Incluye visor vectorial de ejemplo, controles de reproducción, línea de tiempo esquemática e inspector. Permite elegir formato YouTube horizontal (1920 × 1080) o Reels/Shorts vertical (1080 × 1920). La integración con el motor Manim aún está pendiente.

## Requisitos

- Python 3.10 o posterior
- Linux o Windows

## Preparar el entorno

Ejecuta los comandos desde la carpeta raíz del repositorio, donde está `pyproject.toml` (no desde `src/manim_editor`). Si tu terminal está dentro de `src/manim_editor`, vuelve a la raíz con `cd ../..`.

```bash
python3 -m venv .venv
```

Activa el entorno:

- Linux (Bash/Zsh): `source .venv/bin/activate`
- Linux (Fish): `source .venv/bin/activate.fish`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

Instala la app en modo editable y ejecútala:

```bash
python -m pip install -e .
manim-editor
```

En Fish, después de activar el entorno, usa `python3 -m pip install -e .` y luego `manim-editor`. También puedes omitir la activación y ejecutar directamente:

```fish
.venv/bin/python -m pip install -e .
.venv/bin/manim-editor
```

En Windows, si el comando `python` no está disponible, prueba `py -m pip install -e .`.

## Desarrollo

La interfaz está construida con PySide6. Manim se integrará como motor de escenas y renderizado en una etapa posterior.

## Licencia

MIT. Consulta el archivo `LICENSE`.
