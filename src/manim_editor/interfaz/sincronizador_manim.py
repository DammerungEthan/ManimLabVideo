"""Sincronización entre el proyecto gráfico, código fuente y render de Manim."""

import json
from manim_editor.interfaz.analizador_codigo_manim import AnalizadorCodigoManim
from manim_editor.interfaz.generador_fuente_manim import GeneradorFuenteManim
from manim_editor.interfaz.renderizador_escena_manim import RenderizadorEscenaManim
from manim_editor.tipografia import MANIM_TEXT_FONT


class SincronizadorManim(GeneradorFuenteManim, AnalizadorCodigoManim, RenderizadorEscenaManim):
    """Métodos de sincronización que se mezclan con la ventana principal."""

    # Convierte el estado del proyecto en una escena editable de Manim.
    def refresh_code_view(self, _index=None):
        saved_source = self.state.get('manim_source')
        if isinstance(saved_source, str) and saved_source.strip():
            self._updating_code_view=True
            self.code_view.setPlainText(saved_source)
            self._updating_code_view=False
            self._code_user_editing=False
            self._code_view_dirty=not bool(self._manim_video_path)
            self.preview.set_editing_enabled(not self._code_view_dirty)
            if self._code_view_dirty:
                self.code_status.setText('Código cargado. Ejecútalo para reconstruir la previsualización.')
                self.code_status.setStyleSheet('color:#d8c27a')
            else:
                self.code_status.setText('Código de Manim cargado desde el proyecto.')
                self.code_status.setStyleSheet('color:#aeb4bd')
            return
        lines = [
            'from manim import *',
            'import numpy as np',
            '',
            '',
            'class VideoManim(Scene):',
            '    def construct(self):',
            '        self.camera.background_color = "#000000"',
        ]
        width = max(1, int(self.state.get('width', 1920)))
        height = max(1, int(self.state.get('height', 1080)))
        scene_width = 14.222
        scene_height = scene_width * height / width
        frame_height = 1000 / (width / height)
        total_duration = max(0.0, float(self.state.get('duration', 10)))
        events = {}
        supported = 0
        text_index = 0

        for index, obj in enumerate(self.state.get('objects', [])):
            kind = obj.get('kind', '')
            if kind == 'manim_scene':
                continue
            if kind == 'text':
                text_index += 1
            if not obj.get('visible', True):
                continue

            position = obj.get('position')
            if not isinstance(position, dict):
                if kind == 'text':
                    position = {'x': 0.035, 'y': min(0.85, (36 + (text_index - 1) * 28) / frame_height)}
                else:
                    position = {'x': 0.52, 'y': 0.54}
            x = (float(position.get('x', 0.5)) - 0.5) * scene_width
            y = (0.5 - float(position.get('y', 0.5))) * scene_height
            location = f'[{x:.3f}, {y:.3f}, 0]'
            color = json.dumps(str(obj.get('color', '#65d6ff')))
            variable = f'obj_{index + 1}'
            expression = str(obj.get('expression', ''))
            definition = None

            if kind == 'axes':
                definition = f'{variable} = Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], tips=False).set_color({color}).move_to({location})'
            elif kind == 'graph':
                try:
                    graph_expression = self._function_expression_to_numpy(expression)
                    axes_expression=(
                        f'Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], '
                        f'x_length={scene_width:.6f}, y_length={scene_height:.6f}, tips=False)'
                    )
                    components=[]
                    if obj.get('show_grid',True):
                        components.append(
                            f'NumberPlane(x_range=[-7, 7, 2], y_range=[-4, 4, 2], '
                            f'x_length={scene_width:.6f}, y_length={scene_height:.6f}, '
                            f'axis_config={{"stroke_opacity": 0}}, '
                            f'background_line_style={{"stroke_color": "#586273", "stroke_opacity": 0.35}})'
                        )
                    if obj.get('show_axes',True):
                        components.append(axes_expression)
                    components.append(
                        f'{axes_expression}.plot(lambda x: {graph_expression}, x_range=[-7, 7], color={color})'
                    )
                    group=f'VGroup({", ".join(components)})' if len(components)>1 else components[0]
                    definition=f'{variable} = {group}.move_to({location})'
                except (SyntaxError, ValueError, TypeError):
                    definition = None
            elif kind == 'equation':
                definition = (
                    f'{variable} = MathTex({json.dumps(expression, ensure_ascii=False)}, '
                    f'font_size={int(obj.get("font_size", 48))}, color={color}).move_to({location})'
                )
            elif kind == 'text':
                font = json.dumps(str(obj.get('font_family', MANIM_TEXT_FONT)))
                weight = 'BOLD' if int(obj.get('font_weight', 400)) >= 700 else 'NORMAL'
                definition = (
                    f'{variable} = Text({json.dumps(expression, ensure_ascii=False)}, '
                    f'font={font}, font_size={int(obj.get("font_size", 48))}, '
                    f'weight={json.dumps(weight)}, color={color}).move_to({location})'
                )
            elif kind == 'point':
                definition = f'{variable} = Dot(point={location}, color={color})'
            elif kind == 'vector':
                definition = f'{variable} = Arrow(ORIGIN, RIGHT, color={color}).move_to({location})'
            elif kind == 'line':
                definition = f'{variable} = Line(LEFT, RIGHT, color={color}).move_to({location})'
            elif kind == 'circle':
                definition = f'{variable} = Circle(color={color}).move_to({location})'
            elif kind == 'ellipse':
                definition = f'{variable} = Ellipse(width=2, height=1, color={color}).move_to({location})'
            elif kind == 'arrow':
                definition = f'{variable} = Arrow(LEFT, RIGHT, color={color}).move_to({location})'
            elif kind == 'polygon':
                definition = f'{variable} = Polygon(LEFT, UP, RIGHT, color={color}).move_to({location})'
            elif kind == 'table':
                definition = f'{variable} = Table([[{json.dumps(expression, ensure_ascii=False)}]], include_outer_lines=True).move_to({location})'
            elif kind == 'group':
                definition = f'{variable} = VGroup()'

            if definition is None:
                lines.append(f'        # No hay conversión Manim disponible para el tipo: {kind or "desconocido"}.')
                continue
            obj['manim_variable']=variable

            object_scale=float(obj.get('scale',1.0))
            if kind not in {'text','group'} and object_scale != 1.0:
                definition += f'.scale({object_scale:.4f})'
            object_rotation=float(obj.get('rotation',0.0))
            if object_rotation != 0.0:
                definition += f'.rotate({object_rotation:.4f} * DEGREES)'

            supported += 1
            lines.extend('        ' + part.lstrip() for part in definition.splitlines())
            start = max(0.0, float(obj.get('start', 0)))
            duration = max(0.0, float(obj.get('duration', 0)))
            end = min(total_duration, start + duration)
            if start <= total_duration and end >= start:
                animation=obj.get('animation','None')
                if animation in {'Create','FadeIn','Write','GrowFromCenter'} and duration>0:
                    run_time=max(0.1,min(float(obj.get('animation_duration',1.0)),duration))
                    events.setdefault(min(start,total_duration),[]).append(
                        (1,f'self.play({animation}({variable}), run_time={run_time:.3f})',run_time)
                    )
                else:
                    events.setdefault(min(start,total_duration),[]).append((1,f'self.add({variable})',0.0))
                events.setdefault(end,[]).append((0,f'self.remove({variable})',0.0))

        lines.extend(['', '        # Aparición y desaparición según la línea de tiempo.'])
        current_time = 0.0
        for event_time in sorted(events):
            delta = event_time - current_time
            if delta > 0:
                lines.append(f'        self.wait({delta:.3f})')
            plays=[]
            for priority,statement,run_time in sorted(events[event_time],key=lambda item:(item[0],item[1])):
                if statement.startswith('self.play('):
                    plays.append((statement,run_time))
                    continue
                lines.append(f'        {statement}')
            if plays:
                if len(plays)==1:
                    lines.append(f'        {plays[0][0]}')
                else:
                    animations=[]
                    for statement,_run_time in plays:
                        animation_call=statement[len('self.play('):].split(', run_time=',1)[0]
                        animations.append(animation_call)
                    run_time=max(item[1] for item in plays)
                    lines.append(
                        f'        self.play(AnimationGroup({", ".join(animations)}, lag_ratio=0), run_time={run_time:.3f})'
                    )
                current_time=event_time+max(item[1] for item in plays)
            else:
                current_time=event_time
        if total_duration > current_time:
            lines.append(f'        self.wait({total_duration - current_time:.3f})')
        if supported == 0:
            lines.append('        self.wait(1)')
        generated_source=self._sync_object_metadata('\n'.join(lines) + '\n',self.state.get('objects',[]))
        self._updating_code_view=True
        self.code_view.setPlainText(generated_source)
        self._updating_code_view=False
        self._code_user_editing=False
        self._code_view_dirty=False
        self.preview.set_editing_enabled(True)
        self.code_status.setText('Código sincronizado con la previsualización.')
        self.code_status.setStyleSheet('color:#aeb4bd')

    # Renderiza automáticamente cuando termina una pausa en la escritura.
    def _mark_code_view_edited(self):
        if not self._updating_code_view:
            self._pending_preview_seek=None
            self._code_user_editing=True
            self._code_view_dirty=True
            self.preview.set_editing_enabled(False)
            self._render_generation+=1
            self._auto_render_pending=True
            self._code_render_timer.start()
            self.code_status.setText('Renderizando al terminar de escribir…')
            self.code_status.setStyleSheet('color:#d8c27a')

    def _render_edited_code(self):
        self.render_code_scene(automatic=True)

    def _show_last_manim_error(self):
        if self._last_manim_error:
            self._show_manim_error(self._last_manim_error)

    def preview_state_changed(self):
        self._preview_sync_timer.start()

    def _timeline_state_changed(self):
        """Propaga cambios de clips a la vista, al código y al historial."""
        self._pending_timeline_sync=True
        timing_signature=self._timeline_timing_signature()
        timing_changed=timing_signature!=self._timeline_timing_snapshot
        self._timeline_timing_snapshot=timing_signature
        editable_preview=all(
            obj.get('kind')!='manim_scene' for obj in self.state.get('objects',[])
        )
        if timing_changed and editable_preview:
            # El fotograma guardado conserva los tiempos anteriores; mientras
            # Manim se actualiza, pinta los clips con sus tiempos nuevos.
            self._timeline_preview_override=True
            self.preview.set_rendered_frame(None)
        self._preview_sync_timer.start()
        self.update_views()
        self.seek(float(self.timeline.position))

    def _timeline_timing_signature(self):
        return tuple(
            (obj.get('manim_variable'),obj.get('name'),
             round(float(obj.get('start',0)),4),round(float(obj.get('duration',0)),4))
            for obj in self.state.get('objects',[])
        )

    def _sync_preview_changes(self):
        timeline_sync=self._pending_timeline_sync
        self._pending_timeline_sync=False
        source=(
            self.code_view.toPlainText()
            if timeline_sync and self._code_user_editing
            else self.state.get('manim_source')
        )
        if source and (timeline_sync or not self._code_user_editing):
            # Los cambios de tiempo se aplican al texto actual, incluso si el
            # usuario tiene ediciones pendientes de renderizar.
            updated_source=self._sync_manim_source_from_preview(source,self.state.get('objects',[]))
            if updated_source and updated_source!=source:
                self._pending_preview_seek=float(self.timeline.position)
                self.state['manim_source']=updated_source
                self._updating_code_view=True
                self.code_view.setPlainText(updated_source)
                self._updating_code_view=False
                self._code_view_dirty=True
                self._render_generation+=1
                self._auto_render_pending=True
                self._code_render_timer.start(700)
                self.code_status.setText('Cambios de la previsualización aplicados al código; preparando el render…')
                self.code_status.setStyleSheet('color:#d8c27a')
        elif not source and not self._code_view_dirty:
            # La escena creada desde el lienzo también se refleja en el código
            # aunque el proyecto aún no tenga una fuente Manim guardada.
            self.refresh_code_view()
        self.update_views()

