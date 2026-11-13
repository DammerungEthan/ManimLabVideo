"""Genera y actualiza el código fuente desde los elementos gráficos."""

import ast
import json
import re
from PySide6.QtGui import QFont, QFontMetricsF
from manim_editor.tipografia import MANIM_TEXT_FONT


class GeneradorFuenteManim:
    """Genera y actualiza el código fuente desde los elementos gráficos."""

    def _sync_manim_source_from_preview(self, source, preview_objects):
        """Actualiza solo las asignaciones de Mobject reconocidas en construct()."""
        if any(obj.get('kind') == 'graph' for obj in preview_objects):
            source = self._ensure_numpy_import(source)
        try:
            tree=ast.parse(source)
            baseline,_duration=self._parse_manim_scene(source)
        except (SyntaxError,TypeError,ValueError):
            return source
        baseline_by_variable={
            obj.get('manim_variable'):obj for obj in baseline if obj.get('manim_variable')
        }
        construct=next(
            (node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='construct'),
            None,
        )
        if construct is None:
            return source
        assignments={}
        for statement in construct.body:
            if isinstance(statement,ast.Assign):
                targets=statement.targets
            elif isinstance(statement,ast.AnnAssign):
                targets=[statement.target]
            else:
                continue
            for target in targets:
                if isinstance(target,ast.Name):
                    assignments[target.id]=statement.value

        source_bytes=source.encode('utf-8')
        line_offsets=[]
        offset=0
        for line in source.splitlines(keepends=True):
            line_offsets.append(offset)
            offset+=len(line.encode('utf-8'))
        replacements=[]
        for obj in preview_objects:
            variable=obj.get('manim_variable')
            original=baseline_by_variable.get(variable)
            value_node=assignments.get(variable)
            if original is None or value_node is None:
                continue
            position_changed=any(
                abs(float(obj.get('position',{}).get(axis,0.5))-float(original.get('position',{}).get(axis,0.5)))>0.0005
                for axis in ('x','y')
            )
            is_text=obj.get('kind')=='text'
            scale_changed=(
                int(obj.get('font_size',48))!=int(original.get('font_size',48))
                if is_text else
                abs(float(obj.get('scale',1.0))-float(original.get('scale',1.0)))>0.001
            )
            rotation_changed=abs(float(obj.get('rotation',0.0))-float(original.get('rotation',0.0)))>0.1
            color_changed=str(obj.get('color','#65d6ff')).lower()!=str(original.get('color','#65d6ff')).lower()
            visibility_changed=bool(obj.get('visible',True))!=bool(original.get('visible',True))
            expression_changed=(obj.get('kind') in {'graph','text','table'} and str(obj.get('expression',''))!=str(original.get('expression','')))
            graph_options_changed=(obj.get('kind')=='graph' and any(
                obj.get(key,True)!=original.get(key,True) for key in ('show_grid','show_axes')
            ))
            if expression_changed or graph_options_changed or (obj.get('kind')=='graph' and color_changed):
                expression=self._preview_object_expression(obj)
                if expression:
                    start=line_offsets[value_node.lineno-1]+value_node.col_offset
                    end=line_offsets[value_node.end_lineno-1]+value_node.end_col_offset
                    replacements.append((start,end,expression.encode('utf-8')))
                continue
            if not (position_changed or scale_changed or rotation_changed or color_changed or visibility_changed):
                continue

            base_node=value_node
            while (
                isinstance(base_node,ast.Call)
                and isinstance(base_node.func,ast.Attribute)
                and base_node.func.attr in {'move_to','scale','rotate','set_color','set_opacity'}
            ):
                base_node=base_node.func.value
            base_expression=ast.get_source_segment(source,base_node)
            if not base_expression:
                continue

            transform_expressions=original.get('manim_transform_expressions',[])
            expression=base_expression
            for method in ('move_to','scale','rotate','set_color','set_opacity'):
                if method=='move_to' and position_changed:
                    frame_width=14.222
                    width=max(1,int(self.state.get('width',1920)))
                    height=max(1,int(self.state.get('height',1080)))
                    frame_height=frame_width*height/width
                    position=obj.get('position',{'x':0.5,'y':0.5})
                    x=float(position.get('x',0.5))
                    y=float(position.get('y',0.5))
                    if is_text:
                        font=QFont(obj.get('font_family',MANIM_TEXT_FONT),int(obj.get('font_size',48)))
                        metrics=QFontMetricsF(font)
                        x+=metrics.horizontalAdvance(str(obj.get('expression','')))/2000
                        y+=metrics.height()/(2*1000*height/width)
                    scene_x=(x-0.5)*frame_width
                    scene_y=(0.5-y)*frame_height
                    expression+=f'.move_to([{scene_x:.6f}, {scene_y:.6f}, 0])'
                elif method=='scale' and scale_changed:
                    if is_text:
                        base_keywords={item.arg:item.value for item in base_node.keywords if item.arg}
                        base_size=int(self._code_literal(base_keywords.get('font_size'),48))
                        scale=float(obj.get('font_size',base_size))/max(1,base_size)
                    else:
                        scale=float(obj.get('scale',1.0))
                    if abs(scale-1.0)>0.001:
                        expression+=f'.scale({scale:.6f})'
                elif method=='rotate' and rotation_changed:
                    rotation=float(obj.get('rotation',0.0))
                    if abs(rotation)>0.1:
                        expression+=f'.rotate({rotation:.6f} * DEGREES)'
                elif method=='set_color' and color_changed:
                    expression+=f'.set_color({json.dumps(str(obj.get("color","#65d6ff")))})'
                elif method=='set_opacity' and visibility_changed:
                    expression+=f'.set_opacity({1 if obj.get("visible",True) else 0})'
                else:
                    expression+=''.join(
                        f'.{existing_method}({argument})'
                        for existing_method,argument in transform_expressions
                        if existing_method==method
                    )

            start=line_offsets[value_node.lineno-1]+value_node.col_offset
            end=line_offsets[value_node.end_lineno-1]+value_node.end_col_offset
            replacements.append((start,end,expression.encode('utf-8')))

        for start,end,replacement in sorted(replacements,reverse=True):
            source_bytes=source_bytes[:start]+replacement+source_bytes[end:]
        updated_source=source_bytes.decode('utf-8')
        for obj in preview_objects:
            if obj.get('manim_variable') or obj.get('kind')=='manim_scene':
                continue
            variable=self._next_preview_variable(updated_source)
            expression=self._preview_object_expression(obj)
            if not expression:
                continue
            source_before_insert=updated_source
            updated_source,actual_start=self._insert_preview_object(
                updated_source,variable,expression,float(obj.get('start',0.0)),float(obj.get('duration',1.0)),
                obj.get('animation','None'),float(obj.get('animation_duration',1.0)),
            )
            if (
                updated_source != source_before_insert
                and re.search(rf'\b{re.escape(variable)}\s*=',updated_source)
            ):
                obj['manim_variable']=variable
                obj['start']=actual_start
                self._pending_preview_seek=actual_start
        updated_source=self._sync_object_metadata(updated_source,preview_objects)
        return self._sync_simple_timeline_to_code(updated_source,preview_objects)

    @staticmethod
    def _sync_object_metadata(source, objects):
        """Guarda nombre y color del clip en comentarios legibles por el editor."""
        source_lines=[line for line in source.splitlines() if not line.lstrip().startswith('# manim-editor-object:')]
        metadata=[]
        for obj in objects:
            variable=obj.get('manim_variable')
            if not variable or obj.get('kind')=='manim_scene':
                continue
            record={'variable':variable,'name':obj.get('name',variable),
                    'clip_color':obj.get('clip_color',obj.get('color','#65d6ff')),
                    'track':obj.get('track','Pista 1')}
            metadata.append('# manim-editor-object: '+json.dumps(record,ensure_ascii=False))
        if metadata:
            source_lines.extend(['', *metadata])
        return '\n'.join(source_lines).rstrip()+'\n'

    def _sync_simple_timeline_to_code(self,source,preview_objects):
        """Reescribe esperas y animaciones sencillas usando los tiempos del timeline."""
        variables={
            obj.get('manim_variable'):obj
            for obj in preview_objects
            if obj.get('manim_variable') and obj.get('kind')!='manim_scene'
        }
        if not variables:
            return source
        try:
            tree=ast.parse(source)
            parsed_objects,_duration=self._parse_manim_scene(source)
        except (SyntaxError,TypeError,ValueError):
            return source
        code_times={
            obj.get('manim_variable'):obj
            for obj in parsed_objects if obj.get('manim_variable')
        }
        timing_changed=any(
            variable not in code_times
            or abs(float(obj.get('start',0))-float(code_times[variable].get('start',0)))>0.01
            or abs(float(obj.get('duration',0))-float(code_times[variable].get('duration',0)))>0.01
            or obj.get('animation','None')!=code_times[variable].get('animation','None')
            for variable,obj in variables.items()
        )
        if not timing_changed:
            return source
        construct=next(
            (node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='construct'),
            None,
        )
        if construct is None:
            return source

        timing_nodes=[]
        for statement in construct.body:
            if not isinstance(statement,ast.Expr) or not isinstance(statement.value,ast.Call):
                continue
            call=statement.value
            if not isinstance(call.func,ast.Attribute) or not isinstance(call.func.value,ast.Name) or call.func.value.id!='self':
                continue
            action=call.func.attr
            if action in {'wait','add','remove','play'}:
                timing_nodes.append(statement)
            elif timing_nodes:
                # Una llamada de escena intercalada con el timeline puede tener
                # efectos laterales; en ese caso no movemos los bloques de código.
                return source
        if not timing_nodes:
            return source

        first_timing=min(node.lineno for node in timing_nodes)
        if any(
            statement.lineno>=first_timing
            and statement not in timing_nodes
            and not isinstance(statement,ast.Pass)
            for statement in construct.body
        ):
            # Solo reconstruye la cola temporal cuando las definiciones de
            # objetos ya están completas antes de la primera acción.
            return source

        events=[]
        intro_names=set()
        ending_names=set()
        current_time=0.0
        animation_order=0
        for statement in timing_nodes:
            call=statement.value
            action=call.func.attr
            if action=='wait':
                current_time+=max(0.0,float(self._code_literal(call.args[0],1.0))) if call.args else 1.0
                continue
            if action in {'add','remove'}:
                # La adición/eliminación se reconstruye a partir de cada clip.
                referenced={
                    node.id for argument in call.args for node in ast.walk(argument)
                    if isinstance(node,ast.Name) and node.id in variables
                }
                if action=='add':
                    for variable in referenced:
                        obj=variables[variable]
                        animation=obj.get('animation','None')
                        if animation not in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}:
                            continue
                        run_time=max(0.1,min(float(obj.get('animation_duration',1.0)),float(obj.get('duration',1.0))))
                        start=max(0.0,float(obj.get('start',current_time)))
                        events.append((start,2,animation_order,
                                       f'self.play({animation}({variable}), run_time={run_time:.3f})',
                                       run_time,{variable},{variable},set()))
                        animation_order+=1
                        intro_names.add(variable)
                if not referenced:
                    events.append((current_time,1 if action=='add' else 0,animation_order,
                                   ast.unparse(call),0.0,set(),set(),set()))
                    animation_order+=1
                else:
                    untracked_args=[
                        ast.unparse(argument) for argument in call.args
                        if not any(
                            isinstance(node,ast.Name) and node.id in variables
                            for node in ast.walk(argument)
                        )
                    ]
                    if untracked_args:
                        events.append((current_time,1 if action=='add' else 0,animation_order,
                                       f'self.{action}({", ".join(untracked_args)})',0.0,set(),set(),set()))
                        animation_order+=1
                continue

            run_time=max(0.01,float(next(
                (self._code_literal(item.value,1.0) for item in call.keywords if item.arg=='run_time'),
                1.0,
            )))
            referenced={
                node.id for argument in call.args for node in ast.walk(argument)
                if isinstance(node,ast.Name) and node.id in variables
            }
            if not referenced:
                events.append((current_time,2,animation_order,ast.unparse(call),run_time,set(),set(),set()))
                animation_order+=1
                current_time+=run_time
                continue
            desired_starts=[]
            local_intro=set()
            local_ending=set()
            for argument in call.args:
                for animation_node in ast.walk(argument):
                    if not isinstance(animation_node,ast.Call):
                        continue
                    animation_name=self._manim_call_name(animation_node)
                    anim_variables={
                        node.id for node in ast.walk(animation_node)
                        if isinstance(node,ast.Name) and node.id in variables
                    }
                    if animation_name in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}:
                        local_intro.update(anim_variables)
                    if animation_name in {'FadeOut','Uncreate','Unwrite'}:
                        local_ending.update(anim_variables)
            for variable in referenced:
                obj=variables[variable]
                old=code_times.get(variable,{'start':current_time})
                start=max(0.0,float(obj.get('start',0)))
                end=start+max(0.1,float(obj.get('duration',0.1)))
                if referenced.issubset(local_ending) and variable in local_ending:
                    desired_starts.append(max(start,end-run_time))
                else:
                    offset=max(0.0,current_time-float(old.get('start',current_time)))
                    desired_starts.append(start+offset)
            if max(desired_starts)-min(desired_starts)>0.01:
                # Un play agrupado no se puede separar sin cambiar su animación.
                return source
            target_start=desired_starts[0]
            if not all(obj.get('visible',True) for variable,obj in variables.items() if variable in referenced):
                return source
            call_text=ast.unparse(call)
            if len(referenced)==1:
                variable=next(iter(referenced))
                desired=variables[variable].get('animation','None')
                previous=code_times.get(variable,{}).get('animation','None')
                if desired!=previous and previous in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}:
                    if desired in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}:
                        call_text=re.sub(
                            rf'\b{re.escape(previous)}\s*\(\s*{re.escape(variable)}\s*\)',
                            f'{desired}({variable})',call_text,count=1,
                        )
                    elif previous+'(' in call_text:
                        call_text=f'self.add({variable})'
                        run_time=0.0
                        local_intro.discard(variable)
                        local_ending.discard(variable)
                        intro_names.discard(variable)
                        ending_names.discard(variable)
            events.append((target_start,2,animation_order,call_text,run_time,referenced,local_intro,local_ending))
            animation_order+=1
            intro_names.update(local_intro)
            ending_names.update(local_ending)
            current_time+=run_time

        total_duration=max(0.1,float(self.state.get('duration',1)))
        for variable,obj in variables.items():
            if not obj.get('visible',True):
                continue
            start=max(0.0,float(obj.get('start',0)))
            end=start+max(0.1,float(obj.get('duration',0.1)))
            total_duration=max(total_duration,end)
            if variable not in intro_names:
                events.append((start,1,animation_order,f'self.add({variable})',0.0,{variable},set(),set()))
                animation_order+=1
            if variable not in ending_names:
                events.append((end,0,animation_order,f'self.remove({variable})',0.0,{variable},set(),set()))
                animation_order+=1

        events.sort(key=lambda event:(event[0],event[1],event[2]))

        indent=' '*(construct.col_offset+4)
        schedule=[]
        schedule_time=0.0
        for event_time,_priority,_order,statement,run_time,_names,_intro,_ending in events:
            if event_time<schedule_time-0.01:
                # Las animaciones Manim son secuenciales en construct(); no
                # podemos solapar dos plays cambiando solo sus tiempos.
                return source
            if event_time>schedule_time:
                schedule.append(f'{indent}self.wait({event_time-schedule_time:.3f})\n')
            schedule.append(f'{indent}{statement}\n')
            schedule_time=event_time+run_time
        if total_duration>schedule_time:
            schedule.append(f'{indent}self.wait({total_duration-schedule_time:.3f})\n')

        lines=source.splitlines(keepends=True)
        first_timing_line=min(node.lineno-1 for node in timing_nodes)
        timing_lines={
            line for node in timing_nodes for line in range(node.lineno-1,node.end_lineno)
        }
        rewritten=[]
        inserted=False
        for index,line in enumerate(lines):
            if index==first_timing_line and not inserted:
                rewritten.extend(schedule)
                inserted=True
            if index not in timing_lines:
                rewritten.append(line)
        if not inserted:
            return source
        return ''.join(rewritten)

    @staticmethod
    def _next_preview_variable(source):
        names=set(re.findall(r'\bpreview_obj_(\d+)\b',source))
        index=1
        while str(index) in names:
            index+=1
        return f'preview_obj_{index}'

    def _preview_object_expression(self,obj):
        """Forma una expresión Manim para un objeto creado desde la previsualización."""
        kind=obj.get('kind')
        color=json.dumps(str(obj.get('color','#65d6ff')))
        expression=str(obj.get('expression',''))
        if kind=='graph':
            try:
                graph_expression=self._function_expression_to_numpy(expression)
            except (SyntaxError,ValueError,TypeError):
                return None
            width=max(1,int(self.state.get('width',1920)))
            height=max(1,int(self.state.get('height',1080)))
            frame_width=14.222
            frame_height=frame_width*height/width
            axes=(
                'Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], '
                f'x_length={frame_width:.6f}, y_length={frame_height:.6f}, tips=False)'
            )
            components=[]
            if obj.get('show_grid',True):
                components.append(
                    'NumberPlane(x_range=[-7, 7, 2], y_range=[-4, 4, 2], '
                    f'x_length={frame_width:.6f}, y_length={frame_height:.6f}, '
                    'axis_config={"stroke_opacity": 0}, '
                    'background_line_style={"stroke_color": "#586273", "stroke_opacity": 0.35})'
                )
            if obj.get('show_axes',True):
                components.append(axes)
            components.append(f'{axes}.plot(lambda x: {graph_expression}, x_range=[-7, 7], color={color})')
            base=f'VGroup({", ".join(components)})' if len(components)>1 else components[0]
        elif kind=='text':
            weight='BOLD' if int(obj.get('font_weight',400))>=700 else 'NORMAL'
            base=(
                f'Text({json.dumps(expression,ensure_ascii=False)}, '
                f'font={json.dumps(str(obj.get("font_family",MANIM_TEXT_FONT)))}, '
                f'font_size={int(obj.get("font_size",48))}, weight={json.dumps(weight)}, color={color})'
            )
        elif kind=='axes':
            base=f'Axes(x_range=[-7, 7, 1], y_range=[-4, 4, 1], tips=False).set_color({color})'
        elif kind=='point':
            base=f'Dot(color={color})'
        elif kind=='line':
            base=f'Line(LEFT, RIGHT, color={color})'
        elif kind=='vector':
            base=f'Arrow(ORIGIN, RIGHT, color={color})'
        elif kind=='arrow':
            base=f'Arrow(LEFT, RIGHT, color={color})'
        elif kind=='circle':
            base=f'Circle(color={color})'
        elif kind=='ellipse':
            base=f'Ellipse(width=2, height=1, color={color})'
        elif kind=='polygon':
            base=f'Polygon(LEFT, UP, RIGHT, color={color})'
        elif kind=='table':
            base=f'Table([[{json.dumps(expression,ensure_ascii=False)}]], include_outer_lines=True).set_color({color})'
        else:
            return None

        position=obj.get('position',{'x':0.5,'y':0.5})
        x=float(position.get('x',0.5))
        y=float(position.get('y',0.5))
        width=max(1,int(self.state.get('width',1920)))
        height=max(1,int(self.state.get('height',1080)))
        frame_width=14.222
        frame_height=frame_width*height/width
        if kind=='text':
            font=QFont(obj.get('font_family',MANIM_TEXT_FONT),int(obj.get('font_size',48)))
            metrics=QFontMetricsF(font)
            x+=metrics.horizontalAdvance(expression)/2000
            y+=metrics.height()/(2*1000*height/width)
        scene_x=(x-0.5)*frame_width
        scene_y=(0.5-y)*frame_height
        result=f'{base}.move_to([{scene_x:.6f}, {scene_y:.6f}, 0])'
        if not obj.get('visible',True):
            result+='.set_opacity(0)'
        if kind!='text' and abs(float(obj.get('scale',1.0))-1.0)>0.001:
            result+=f'.scale({float(obj["scale"]):.6f})'
        rotation=float(obj.get('rotation',0.0))
        if abs(rotation)>0.1:
            result+=f'.rotate({rotation:.6f} * DEGREES)'
        return result

    @staticmethod
    def _function_expression_to_numpy(expression):
        """Convierte una fórmula de f(x) en una expresión vectorizada para Manim."""
        tree=ast.parse(str(expression).strip().replace('^','**'),mode='eval')
        functions={
            'sin','cos','tan','asin','acos','atan','sinh','cosh','tanh',
            'sqrt','abs','exp','log','log10','floor','ceil','min','max',
        }
        constants={'pi':'np.pi','e':'np.e','tau':'(2 * np.pi)'}

        class Translator(ast.NodeTransformer):
            def visit_Name(self,node):
                if node.id in constants:
                    return ast.copy_location(ast.parse(constants[node.id],mode='eval').body,node)
                if node.id in functions:
                    numpy_name={'min':'minimum','max':'maximum'}.get(node.id,node.id)
                    return ast.copy_location(
                        ast.Attribute(value=ast.Name(id='np',ctx=ast.Load()),attr=numpy_name,ctx=ast.Load()),node
                    )
                if node.id!='x':
                    raise ValueError(f'Nombre no permitido en la función: {node.id}')
                return node

            def visit_Call(self,node):
                if not isinstance(node.func,ast.Name) or node.func.id not in functions:
                    raise ValueError('Solo se permiten funciones matemáticas conocidas.')
                expected={
                    'min':2,'max':2,'log':(1,2),
                }.get(node.func.id,1)
                if isinstance(expected,tuple):
                    if len(node.args) not in expected:
                        raise ValueError('Número de argumentos incorrecto.')
                elif len(node.args)!=expected:
                    raise ValueError('Número de argumentos incorrecto.')
                if node.keywords:
                    raise ValueError('No se permiten argumentos con nombre.')
                if node.func.id=='log' and len(node.args)==2:
                    numerator=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='np',ctx=ast.Load()),attr='log',ctx=ast.Load()),
                        args=[self.visit(node.args[0])],keywords=[],
                    )
                    denominator=ast.Call(
                        func=ast.Attribute(value=ast.Name(id='np',ctx=ast.Load()),attr='log',ctx=ast.Load()),
                        args=[self.visit(node.args[1])],keywords=[],
                    )
                    return ast.copy_location(ast.BinOp(left=numerator,op=ast.Div(),right=denominator),node)
                return self.generic_visit(node)

            def visit_Attribute(self,node):
                raise ValueError('No se permiten atributos en la función.')

        translated=Translator().visit(tree)
        return ast.unparse(ast.fix_missing_locations(translated))

    @staticmethod
    def _ensure_numpy_import(source):
        """Asegura el alias np que requieren las gráficas vectorizadas."""
        try:
            tree=ast.parse(source)
        except SyntaxError:
            return source
        if any(
            isinstance(node,ast.Import)
            and any(alias.name=='numpy' and alias.asname=='np' for alias in node.names)
            for node in tree.body
        ):
            return source
        insertion_line=0
        if tree.body and isinstance(tree.body[0],ast.Expr) and isinstance(tree.body[0].value,ast.Constant) and isinstance(tree.body[0].value.value,str):
            insertion_line=tree.body[0].end_lineno
        future_lines=[node.end_lineno for node in tree.body if isinstance(node,ast.ImportFrom) and node.module=='__future__']
        if future_lines:
            insertion_line=max(insertion_line,max(future_lines))
        lines=source.splitlines(keepends=True)
        lines.insert(insertion_line,'import numpy as np\n')
        return ''.join(lines)

    def _insert_preview_object(self,source,variable,expression,start,duration,animation='None',animation_duration=1.0):
        """Inserta el objeto en construct() cerca del instante elegido en la línea de tiempo."""
        try:
            tree=ast.parse(source)
        except SyntaxError:
            return source,start
        construct=next(
            (node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='construct'),
            None,
        )
        if construct is None:
            return source,start
        indent=' '*(construct.col_offset+4)
        block=[f'{indent}{variable} = {expression}']
        if animation in {'Create','FadeIn','Write','GrowFromCenter'}:
            run_time=max(0.1,min(float(animation_duration),max(0.1,float(duration))))
            block.append(f'{indent}self.play({animation}({variable}), run_time={run_time:.3f})')
        else:
            block.append(f'{indent}self.add({variable})')
        target=max(0.0,start)
        current=0.0
        insertion_index=construct.end_lineno
        actual_start=current
        timed_actions={'wait','play'}
        for statement in construct.body:
            if isinstance(statement,ast.Return):
                insertion_index=statement.lineno-1
                actual_start=current
                break
            if not isinstance(statement,ast.Expr) or not isinstance(statement.value,ast.Call):
                continue
            call=statement.value
            if not isinstance(call.func,ast.Attribute) or not isinstance(call.func.value,ast.Name) or call.func.value.id!='self':
                continue
            action=call.func.attr
            if action in {'add','remove'} and target<=current+0.0001:
                insertion_index=statement.lineno-1
                actual_start=current
                break
            if action not in timed_actions:
                continue
            elapsed=(
                max(0.0,float(self._code_literal(call.args[0],1.0)))
                if action=='wait' and call.args else
                max(0.0,float(next((self._code_literal(item.value,1.0) for item in call.keywords if item.arg=='run_time'),1.0)))
                if action=='play' else 1.0
            )
            if target<=current+0.0001:
                insertion_index=statement.lineno-1
                actual_start=current
                break
            if target<current+elapsed:
                # Insertar al cerrar una animación evita dividir su secuencia.
                insertion_index=statement.end_lineno
                actual_start=current+elapsed
                break
            current+=elapsed
            actual_start=current

        lines=source.splitlines(keepends=True)
        future_timing=False
        for statement in construct.body:
            if statement.lineno-1<insertion_index:
                continue
            if isinstance(statement,ast.Expr) and isinstance(statement.value,ast.Call):
                call=statement.value
                if isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id=='self' and call.func.attr in timed_actions:
                    future_timing=True
                    break
        if not future_timing:
            block.append(f'{indent}self.wait({max(0.1,min(1.0,duration)):.3f})')
        block_text='\n'.join(block)+'\n'
        if insertion_index>0 and insertion_index<=len(lines) and not lines[insertion_index-1].endswith(('\n','\r')):
            lines[insertion_index-1]+='\n'
        lines.insert(insertion_index,block_text)
        return ''.join(lines),actual_start
