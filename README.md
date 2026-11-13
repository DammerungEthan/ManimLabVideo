# Manim Editor

Editor de escritorio multiplataforma para crear y editar animaciones con Manim, con una experiencia basada en línea de tiempo y previsualización.

> Estado: editor gráfico en desarrollo. Los elementos se crean desde un catálogo, se seleccionan en el preview o el timeline y se ajustan en el inspector lateral, incluidas transiciones de entrada y salida. El proyecto ofrece pistas editables, reproducción y formatos YouTube (16:9) y Reels/Shorts (9:16). El preview dibuja una representación vectorial; la exportación/renderizado final con el motor Manim sigue pendiente.

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
├── aplicacion.py          # Punto de entrada de la aplicación
├── tipografia.py          # Familias tipográficas iniciales de Manim
├── modelos/
│   └── proyecto.py        # Estado y normalización de proyectos
├── servicios/
│   ├── archivos_proyecto.py # Lectura y escritura de proyectos
│   └── ejecutor_manim.py  # Ejecución y cancelación de renders Manim
├── interfaz/
│   ├── ventana_principal.py       # Composición de la ventana
│   ├── sincronizador_manim.py     # Sincronización entre código, preview y timeline
│   ├── analizador_codigo_manim.py # Lectura de escenas Manim
│   ├── generador_fuente_manim.py  # Generación de código desde cambios gráficos
│   ├── renderizador_escena_manim.py # Ejecución y recepción de fotogramas
│   ├── vista_previa.py            # Canvas y dibujo de la escena
│   ├── interaccion_lienzo.py      # Selección, movimiento, escala y rotación
│   ├── creador_elementos.py       # Diálogos y alta de objetos
│   ├── vista_grafica_funcion.py   # Preview aislado de funciones
│   ├── texto_matematico.py        # Formato y preview de ecuaciones
│   ├── linea_tiempo.py            # Pistas y clips
│   └── editor_codigo.py           # Editor y resaltado de sintaxis
└── icons/                         # Recursos gráficos de la aplicación
```

La interfaz vive en `interfaz/`, el formato de proyecto en `modelos/` y las operaciones de entrada/salida en `servicios/`. Cada módulo concentra una responsabilidad para facilitar la edición y ampliación del editor. `aplicacion.py` solo inicia Qt y muestra la ventana principal.

## Licencia

MIT. Consulta el archivo `LICENSE`.
