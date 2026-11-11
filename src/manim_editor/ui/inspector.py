"""Panel lateral para editar propiedades del clip seleccionado en vivo."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)


class Inspector(QWidget):
    def __init__(self, on_change, parent=None):
        super().__init__(parent)
        self.on_change = on_change
        self.object_data = None
        self._loading = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("PROPIEDADES DEL ELEMENTO"))
        self.empty = QLabel("Selecciona un clip en el timeline para editarlo.")
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.form = QFormLayout()
        self.name = QLineEdit(); self.expression = QLineEdit()
        self.start = self._number(0, 100000, 0.1)
        self.duration = self._number(0.03, 100000, 0.1, 5)
        # Las posiciones del canvas se guardan como proporción del lienzo (0 a 1).
        self.x = self._number(0, 1, 0.01); self.y = self._number(0, 1, 0.01)
        self.scale = self._number(0.05, 20, 0.05, 1)
        self.rotation = self._number(-3600, 3600, 1)
        self.opacity = self._number(0, 1, 0.05, 1)
        self.stroke = self._number(0.1, 30, 0.5, 3)
        self.font_size = self._integer(8, 300, 42)
        self.x_min = self._number(-1000, 1000, 0.5, -7)
        self.x_max = self._number(-1000, 1000, 0.5, 7)
        self.color = QPushButton("Elegir color")
        self.visible = QCheckBox("Visible")
        for label, widget in [("Nombre", self.name), ("Texto / función", self.expression),
                              ("Inicio (s)", self.start), ("Duración (s)", self.duration),
                              ("Posición X · lienzo", self.x), ("Posición Y · lienzo", self.y),
                              ("Escala", self.scale), ("Rotación °", self.rotation),
                              ("Opacidad", self.opacity), ("Grosor", self.stroke),
                              ("Tamaño texto", self.font_size), ("X mínimo", self.x_min),
                              ("X máximo", self.x_max), ("Color", self.color),
                              ("", self.visible)]:
            self.form.addRow(label, widget)
        layout.addLayout(self.form); layout.addStretch()
        for widget in (self.name, self.expression): widget.textChanged.connect(self._commit_text)
        for widget, key in ((self.start,"start"),(self.duration,"duration"),(self.x,"x"),
                            (self.y,"y"),(self.scale,"scale"),(self.rotation,"rotation"),
                            (self.opacity,"opacity"),(self.stroke,"stroke_width"),
                            (self.font_size,"font_size"),(self.x_min,"x_min"),(self.x_max,"x_max")):
            widget.valueChanged.connect(lambda value, field=key: self._commit(field, value))
        self.visible.toggled.connect(lambda value:self._commit("visible",value))
        self.color.clicked.connect(self._choose_color)
        self.set_object(None)

    @staticmethod
    def _integer(minimum, maximum, value=0):
        widget=QSpinBox(); widget.setRange(minimum,maximum); widget.setValue(value); return widget

    @staticmethod
    def _number(minimum, maximum, step, value=0):
        widget=QDoubleSpinBox(); widget.setRange(minimum,maximum); widget.setSingleStep(step); widget.setValue(value); widget.setDecimals(2); return widget

    def set_object(self, data):
        self.object_data=data; self._loading=True
        enabled=data is not None; self.empty.setVisible(not enabled)
        for index in range(self.form.count()):
            widget=self.form.itemAt(index, QFormLayout.ItemRole.FieldRole)
            if widget and widget.widget(): widget.widget().setVisible(enabled)
            label=self.form.itemAt(index, QFormLayout.ItemRole.LabelRole)
            if label and label.widget(): label.widget().setVisible(enabled)
        if data:
            self.name.setText(data.get("name","")); self.expression.setText(data.get("expression",""))
            self.start.setValue(float(data.get("start",0))); self.duration.setValue(float(data.get("duration",5)))
            position=data.get("position") if isinstance(data.get("position"),dict) else {}
            self.x.setValue(float(position.get("x",data.get("x",0.52))))
            self.y.setValue(float(position.get("y",data.get("y",0.54))))
            self.scale.setValue(float(data.get("scale",1))); self.rotation.setValue(float(data.get("rotation",0)))
            self.opacity.setValue(float(data.get("opacity",1))); self.stroke.setValue(float(data.get("stroke_width",3)))
            self.font_size.setValue(int(data.get("font_size",42))); self.visible.setChecked(data.get("visible",True))
            self.x_min.setValue(float(data.get("x_min",-7))); self.x_max.setValue(float(data.get("x_max",7)))
            color=data.get("color","#65d6ff"); self.color.setText(color); self.color.setStyleSheet(f"background:{color};border-radius:6px")
        self._loading=False

    def _commit_text(self):
        if not self._loading and self.object_data is not None:
            self.object_data.update(name=self.name.text(),expression=self.expression.text()); self.on_change()

    def _commit(self, key, value):
        if not self._loading and self.object_data is not None:
            self.object_data[key]=value
            if key in ("x", "y"):
                position=self.object_data.setdefault("position",{"x":0.52,"y":0.54})
                position[key]=value
            self.on_change()

    def _choose_color(self):
        if self.object_data is None:return
        chosen=QColorDialog.getColor(QColor(self.object_data.get("color","#65d6ff")),self)
        if chosen.isValid(): self._commit("color",chosen.name()); self.set_object(self.object_data)
