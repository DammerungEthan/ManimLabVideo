"""Lee y convierte fragmentos de código Manim a datos editables."""

import ast
import math

from PySide6.QtGui import QFont, QFontMetricsF
from manim_editor.tipografia import MANIM_MATH_FONT, MANIM_TEXT_FONT


class AnalizadorCodigoManim:
    """Utilidades para inspeccionar escenas y extraer sus objetos."""

    @staticmethod
    def _code_literal(node, default=None):
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            return default

    @staticmethod
    def _manim_call_name(node):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                return function.id
            if isinstance(function, ast.Attribute):
                return function.attr
        return ''

    def _read_manim_object(self, node, variable):
        transforms=[]
        while (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {'move_to', 'scale', 'set_color', 'set_opacity', 'rotate'}
        ):
            transforms.append(node)
            node=node.func.value

        call_name=self._manim_call_name(node)
        if not isinstance(node, ast.Call):
            return None
        nested_plot=next(
            (item for item in ast.walk(node)
             if isinstance(item,ast.Call) and self._manim_call_name(item)=='plot'),
            None,
        )
        nested_names={
            self._manim_call_name(item)
            for item in ast.walk(node) if isinstance(item,ast.Call)
        }
        keywords={item.arg:item.value for item in node.keywords if item.arg}
        args=node.args
        color_names={
            'WHITE':'#FFFFFF','BLACK':'#000000','RED':'#FC6255','MAROON':'#C55AAB',
            'YELLOW':'#FFFF00','GOLD':'#F0AC5F','GREEN':'#83C167','TEAL':'#5CD0B3',
            'BLUE':'#58C4DD','PURPLE':'#9A72AC','PINK':'#D147BD','ORANGE':'#FF862F',
            'GREY':'#888888','GRAY':'#888888',
        }
        color_node=keywords.get('color')
        color=self._code_literal(color_node, color_names.get(getattr(color_node,'id',''), '#65d6ff'))
        expression=''
        kind=None
        obj={'name':variable.replace('_',' ').title(),'kind':'','expression':'','color':color,'clip_color':color,'animation':'None',
             'start':0,'duration':1,'visible':True,'track':'Pista 1','position':{'x':0.52,'y':0.54},'scale':1.0,
             'manim_variable':variable}

        if call_name in {'Text','MathTex','Tex'}:
            kind='equation' if call_name in {'MathTex', 'Tex'} else 'text'
            expression=self._code_literal(args[0], '') if args else ''
            obj['position']={'x':0.5,'y':0.5}
            obj.update(
                name=str(expression)[:24] or obj['name'],
                font_family=(MANIM_MATH_FONT if kind == 'equation' else
                             self._code_literal(keywords.get('font'), MANIM_TEXT_FONT)),
                font_size=int(self._code_literal(keywords.get('font_size'), 48)),
                font_weight=700 if self._code_literal(keywords.get('weight'), 'NORMAL') == 'BOLD' else 400,
            )
        elif call_name=='Axes':
            kind='axes'
        elif call_name=='plot' or nested_plot is not None:
            kind='graph'
            plot_call=node if call_name=='plot' else nested_plot
            if plot_call.args and isinstance(plot_call.args[0],ast.Lambda):
                expression=self._numpy_expression_to_function(plot_call.args[0].body)
            plot_color=next((item.value for item in plot_call.keywords if item.arg=='color'),None)
            if plot_color is not None:
                obj['color']=self._code_literal(
                    plot_color,color_names.get(getattr(plot_color,'id',''),obj['color'])
                )
            obj['show_grid']='NumberPlane' in nested_names
            plot_base=plot_call.func.value if isinstance(plot_call.func,ast.Attribute) else None
            plot_base_ids={id(item) for item in ast.walk(plot_base)} if plot_base is not None else set()
            obj['show_axes']=any(
                isinstance(item,ast.Call)
                and self._manim_call_name(item)=='Axes'
                and id(item) not in plot_base_ids
                for item in ast.walk(node)
            )
        else:
            kind={
                'Dot':'point','Arrow':'arrow','Line':'line','Circle':'circle',
                'Ellipse':'ellipse','Polygon':'polygon','Table':'table','MathTable':'table','VGroup':'group',
            }.get(call_name)
        if kind is None:
            return None
        obj['kind']=kind
        obj['expression']=str(expression)
        if kind=='table' and args:
            table_data=self._code_literal(args[0],[])
            if table_data and isinstance(table_data[0],(list,tuple)) and table_data[0]:
                obj['expression']=str(table_data[0][0])

        point_node=keywords.get('point')
        if kind=='point' and point_node is not None:
            point=self._code_literal(point_node)
            if isinstance(point,(list,tuple)) and len(point)>=2:
                frame_width=14.222
                frame_height=frame_width*max(1,int(self.state.get('height',1080)))/max(1,int(self.state.get('width',1920)))
                obj['position']={'x':max(0,min(1,float(point[0])/frame_width+0.5)), 'y':max(0,min(1,0.5-float(point[1])/frame_height))}

        opacity=1.0
        for transform in reversed(transforms):
            method=transform.func.attr
            value=transform.args[0] if transform.args else None
            if method=='set_color':
                color_node=value
                obj['color']=self._code_literal(value, color_names.get(getattr(value,'id',''),obj['color']))
            elif method=='scale':
                obj['scale']=float(self._code_literal(value, 1.0))
            elif method=='rotate':
                if (
                    isinstance(value, ast.BinOp)
                    and isinstance(value.op, ast.Mult)
                    and isinstance(value.right, ast.Name)
                    and value.right.id == 'DEGREES'
                ):
                    obj['rotation']=float(self._code_literal(value.left, 0.0))
                else:
                    angle=self._code_literal(value)
                    if isinstance(angle,(int,float)):
                        obj['rotation']=math.degrees(float(angle))
            elif method=='set_opacity':
                opacity=float(self._code_literal(value,1.0))
            elif method=='move_to':
                point=self._code_literal(value)
                if isinstance(point, (list, tuple)) and len(point)>=2:
                    x,y=float(point[0]),float(point[1])
                elif isinstance(value, ast.Name):
                    x,y={'ORIGIN':(0,0),'UP':(0,1),'DOWN':(0,-1),'LEFT':(-1,0),'RIGHT':(1,0)}.get(value.id,(0,0))
                else:
                    x,y=0,0
                frame_width=14.222
                frame_height=frame_width*max(1,int(self.state.get('height',1080)))/max(1,int(self.state.get('width',1920)))
                obj['position']={'x':max(0,min(1,x/frame_width+0.5)), 'y':max(0,min(1,0.5-y/frame_height))}
        obj['manim_transform_expressions']=[
            (transform.func.attr,ast.unparse(transform.args[0]))
            for transform in reversed(transforms)
            if transform.args
        ]
        obj['visible']=opacity>0.001
        if color_node is not None:
            obj['manim_color_expression']=ast.unparse(color_node)
        if kind in {'text', 'equation'} and call_name in {'Text','MathTex','Tex'}:
            base_font_size=int(self._code_literal(keywords.get('font_size'),48))
            obj['font_size']=max(8,round(base_font_size*obj.get('scale',1.0)))
            obj['scale']=1.0
            font=QFont(
                obj.get('font_family', MANIM_MATH_FONT if kind == 'equation' else MANIM_TEXT_FONT),
                obj['font_size'],
                QFont.Weight(obj.get('font_weight',400)),
            )
            metrics=QFontMetricsF(font)
            center=obj['position']
            frame_width=1000.0
            frame_height=frame_width*max(1,int(self.state.get('height',1080)))/max(1,int(self.state.get('width',1920)))
            obj['position']={
                'x':center['x']-metrics.horizontalAdvance(obj['expression'])/(2*frame_width),
                'y':center['y']-metrics.height()/(2*frame_height),
            }
        return obj

    @staticmethod
    @staticmethod
    def _numpy_expression_to_function(node):
        """Recupera la sintaxis f(x) desde el cuerpo de una lambda generada."""
        class Translator(ast.NodeTransformer):
            numpy_names={'minimum':'min','maximum':'max'}

            def visit_Attribute(self,attribute):
                if isinstance(attribute.value,ast.Name) and attribute.value.id in {'np','numpy'}:
                    name=self.numpy_names.get(attribute.attr,attribute.attr)
                    if name=='pi':
                        return ast.copy_location(ast.Name(id='pi',ctx=ast.Load()),attribute)
                    if name=='e':
                        return ast.copy_location(ast.Name(id='e',ctx=ast.Load()),attribute)
                    if name in {
                        'sin','cos','tan','asin','acos','atan','sinh','cosh','tanh',
                        'sqrt','abs','exp','log','log10','floor','ceil','min','max',
                    }:
                        return ast.copy_location(ast.Name(id=name,ctx=ast.Load()),attribute)
                return self.generic_visit(attribute)

        translated=Translator().visit(node)
        try:
            return ast.unparse(ast.fix_missing_locations(translated))
        except (TypeError,ValueError):
            return 'sin(x)'

    # Convierte asignaciones y animaciones reconocidas en objetos del timeline.
    def _parse_manim_scene(self, source):
        tree=ast.parse(source)
        construct=next(
            (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name=='construct'),
            None,
        )
        if construct is None:
            raise ValueError('No se encontró el método construct(self) de la escena.')

        objects={}
        current_objects=self.state.get('objects',[])
        tracks_by_variable={
            obj.get('manim_variable'):obj.get('track','Pista 1')
            for obj in current_objects if obj.get('manim_variable')
        }
        tracks_by_variable.update({
            f'obj_{index + 1}':obj.get('track','Pista 1')
            for index,obj in enumerate(current_objects)
        })
        tracks_by_name={
            obj.get('name'):obj.get('track','Pista 1')
            for obj in current_objects if obj.get('name')
        }
        tracks=self.state.setdefault('tracks',['Pista 1'])
        used_tracks={obj.get('track') for obj in current_objects if obj.get('track')}

        def track_for(variable, obj):
            previous=tracks_by_variable.get(variable,tracks_by_name.get(obj.get('name')))
            if previous:
                used_tracks.add(previous)
                return previous
            available=next((track for track in reversed(tracks) if track not in used_tracks),None)
            if available is None:
                number=1
                while f'Pista {number}' in tracks:
                    number+=1
                available=f'Pista {number}'
                tracks.append(available)
            used_tracks.add(available)
            return available
        for statement in construct.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            target=statement.targets[0] if isinstance(statement, ast.Assign) and statement.targets else getattr(statement,'target',None)
            value=statement.value
            if not isinstance(target, ast.Name) or target.id.startswith('graph_axes_'):
                continue
            parsed=self._read_manim_object(value,target.id)
            if parsed is not None:
                parsed['track']=track_for(target.id,parsed)
                objects[target.id]=parsed

        starts={}
        active={}
        timeline=[]
        current_time=0.0

        def names_in(node):
            return list(dict.fromkeys(item.id for item in ast.walk(node) if isinstance(item, ast.Name) and item.id in objects))

        def animation_names(node):
            return {
                item.func.id if isinstance(item.func, ast.Name) else item.func.attr
                for item in ast.walk(node)
                if isinstance(item, ast.Call)
                and isinstance(item.func, (ast.Name, ast.Attribute))
            }

        def animated_names(node, animation_types):
            return {
                name
                for item in ast.walk(node)
                if isinstance(item, ast.Call)
                and self._manim_call_name(item) in animation_types
                for name in names_in(item)
            }

        for statement in construct.body:
            if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                continue
            call=statement.value
            if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name) or call.func.value.id!='self':
                continue
            action=call.func.attr
            if action=='wait':
                current_time+=max(0.0,float(self._code_literal(call.args[0],1.0))) if call.args else 1.0
            elif action=='add':
                for argument in call.args:
                    for name in names_in(argument):
                        starts[name]=current_time
                        active[name]=True
            elif action=='remove':
                for argument in call.args:
                    for name in names_in(argument):
                        if name in active:
                            obj=objects[name]
                            obj['start']=starts.get(name,0.0)
                            obj['duration']=max(0.1,current_time-obj['start'])
                            timeline.append(obj)
                            active.pop(name,None)
            elif action=='play':
                run_time=next((float(self._code_literal(item.value,1.0)) for item in call.keywords if item.arg=='run_time'),1.0)
                for argument in call.args:
                    nested_animations=animation_names(argument)
                    ending_objects=animated_names(argument,{'FadeOut','Uncreate','Unwrite'})
                    intro_objects=animated_names(argument,{'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'})
                    has_succession='Succession' in nested_animations
                    for name in names_in(argument):
                        if name in ending_objects and (name not in intro_objects or has_succession):
                            if name in active:
                                obj=objects[name]
                                obj['start']=starts.get(name,0.0)
                                obj['duration']=max(0.1,current_time+run_time-obj['start'])
                                timeline.append(obj)
                                active.pop(name,None)
                        else:
                            intro_animation=next((
                                self._manim_call_name(item)
                                for item in ast.walk(argument)
                                if isinstance(item,ast.Call)
                                and self._manim_call_name(item) in {'Create','Write','ShowCreation','FadeIn','GrowFromCenter','GrowArrow'}
                                and name in names_in(item)
                            ),None)
                            if intro_animation:
                                objects[name]['animation']={
                                    'ShowCreation':'Create','GrowArrow':'GrowFromCenter',
                                }.get(intro_animation,intro_animation)
                            # Los plays posteriores animan el mismo Mobject; no
                            # deben cambiar el inicio de su clip en el timeline.
                            if name not in active:
                                starts[name]=current_time
                            active[name]=True
                current_time+=max(0.0,run_time)

        editor_metadata={}
        for line in source.splitlines():
            if not line.lstrip().startswith('# manim-editor-object:'):
                continue
            try:
                record=json.loads(line.split(':',1)[1].strip())
            except (ValueError,TypeError):
                continue
            editor_metadata[record.get('variable')]=record
        for obj in timeline:
            record=editor_metadata.get(obj.get('manim_variable'),{})
            if record.get('name'):
                obj['name']=str(record['name'])
            if record.get('clip_color'):
                obj['clip_color']=str(record['clip_color'])
            if record.get('track'):
                obj['track']=str(record['track'])
                if obj['track'] not in self.state.setdefault('tracks',['Pista 1']):
                    self.state['tracks'].append(obj['track'])
        total_duration=max(1.0,current_time)
        for name in active:
            obj=objects[name]
            obj['start']=starts.get(name,0.0)
            obj['duration']=max(0.1,total_duration-obj['start'])
            timeline.append(obj)
        return timeline,total_duration
