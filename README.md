# Manim Editor

Editor de escritorio multiplataforma para crear y editar animaciones con Manim, con una experiencia basada en línea de tiempo y previsualización.

> Estado: editor gráfico en desarrollo. Los elementos se crean desde un catálogo, se seleccionan en el preview o el timeline y se ajustan en el inspector lateral. El proyecto ofrece pistas editables, reproducción y formatos YouTube (16:9) y Reels/Shorts (9:16). El preview dibuja una representación vectorial; la exportación/renderizado final con el motor Manim sigue pendiente.

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

La interfaz está construida con PySide6. Por ahora, la edición se hace desde controles gráficos; no hay editor de código en la aplicación.

### Estructura del código

```text
src/manim_editor/
├── app.py                 # Punto de entrada del comando manim-editor
├── models/                # Estado inicial y normalización de proyectos
├── services/              # Persistencia y servicios del proyecto
├── ui/
│   ├── main_window.py     # Composición de la ventana y coordinación del estado
│   ├── element_catalog.py # Catálogo de elementos insertables
│   ├── inspector.py       # Propiedades editables del clip seleccionado
│   ├── preview.py         # Dibujo e interacción con los elementos
│   ├── timeline.py        # Pistas, clips, selección y cabezal de reproducción
│   └── video_export.py    # Exportación del preview con ffmpeg
└── icons/                 # Recursos gráficos de la aplicación
```

Los cambios de interfaz van en `ui/`, las reglas del formato del proyecto en `models/` y las operaciones de entrada/salida en `services/`. `app.py` solo inicia Qt y muestra `MainWindow`.

## Licencia

MIT. Consulta el archivo `LICENSE`.
