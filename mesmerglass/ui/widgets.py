from PyQt6.QtCore import Qt, QEasingCurve, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QIntValidator
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QToolButton, QLabel, QLineEdit,
    QSizePolicy, QFrame
)
from PyQt6.QtCore import QPropertyAnimation


class ToggleSwitch(QWidget):
    """Consistent animated on/off switch (46x26)."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 26)
        self._checked = bool(checked)
        self._pos = 1.0 if self._checked else 0.0
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def get_pos(self): return self._pos
    def set_pos(self, v: float):
        self._pos = max(0.0, min(1.0, float(v)))
        self.update()
    pos = pyqtProperty(float, fget=get_pos, fset=set_pos)

    def isChecked(self): return self._checked
    def setChecked(self, b: bool):
        b = bool(b)
        if b == self._checked: return
        self._checked = b
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if b else 0.0)
        self._anim.start()
        self.toggled.emit(self._checked)

    def mousePressEvent(self, _):
        self.setChecked(not self._checked)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing, True)
        r = self.rect().adjusted(1, 1, -1, -1)
        # Track
        p.setPen(Qt.PenStyle.NoPen)
        if self._checked:
            p.setBrush(QColor(255, 154, 60, 230))  # Solar accent
        else:
            p.setBrush(QColor(255, 255, 255, 48))
        p.drawRoundedRect(r, r.height()/2, r.height()/2)
        # Knob
        d = r.height() - 6
        x0 = r.left() + 3
        x1 = r.right() - d - 2
        kx = int(x0 + (x1 - x0) * self._pos)
        ky = r.top() + 3
        p.setBrush(QColor(14, 19, 27)); p.setPen(QPen(QColor(17, 23, 34)))
        p.drawEllipse(kx, ky, d, d)


class UnitSpin(QFrame):
    """
    Compact numeric input with integrated ▲/▼ and a visible unit suffix.
    Looks/behaves like one rounded 'bubble'. Emits valueChanged(int).
    """
    valueChanged = pyqtSignal(int)

    def __init__(self, minimum: int, maximum: int, value: int,
                 unit: str = "", step: int = 1, tooltip: str = "",
                 width: int = 140, parent=None):
        super().__init__(parent)
        self._min, self._max, self._step = int(minimum), int(maximum), int(step)
        self._val = max(self._min, min(self._max, int(value)))
        self._unit = unit

        self.setToolTip(tooltip)
        self.setFixedWidth(width)
        self.setObjectName("UnitSpin")
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.edit = QLineEdit(str(self._val))
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setValidator(QIntValidator(self._min, self._max, self))
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.edit.setObjectName("UnitSpinEdit")
        self.edit.textEdited.connect(self._on_text)

        self.unit_lbl = QLabel(self._unit)
        self.unit_lbl.setMinimumWidth(18)
        self.unit_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.unit_lbl.setObjectName("UnitSpinUnit")

        self.btn_up = QToolButton();  self.btn_up.setText("▲")
        self.btn_dn = QToolButton();  self.btn_dn.setText("▼")
        for b in (self.btn_up, self.btn_dn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedSize(22, 16)
            b.setObjectName("UnitSpinBtn")

        self.btn_up.clicked.connect(lambda: self._step_by(+self._step))
        self.btn_dn.clicked.connect(lambda: self._step_by(-self._step))

        left = QHBoxLayout(); left.setContentsMargins(8, 6, 4, 6); left.setSpacing(6)
        left_w = QWidget(); left_w.setLayout(left)
        left.addWidget(self.edit, 1); left.addWidget(self.unit_lbl, 0)

        right = QVBoxLayout(); right.setContentsMargins(2, 4, 6, 4); right.setSpacing(2)
        right_w = QWidget(); right_w.setLayout(right)
        right.addWidget(self.btn_up); right.addWidget(self.btn_dn)

        root = QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        root.addWidget(left_w, 1); root.addWidget(right_w, 0)

        # unified bubble styling so arrows clearly belong to this field
        self.setStyleSheet("""
        #UnitSpin {
            background: rgba(16,21,28,0.96);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
        }
        #UnitSpinEdit { background: transparent; border: none; padding: 0; color: #E8ECF5; }
        #UnitSpinUnit { color: #C9D3E6; }
        #UnitSpinBtn {
            background: rgba(255,255,255,0.14);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 6px;
            padding: 0;
        }
        #UnitSpinBtn:hover { background: rgba(255,255,255,0.22); }
        """)

    # API
    def value(self) -> int: return self._val
    def setValue(self, v: int):
        v = max(self._min, min(self._max, int(v)))
        if v == self._val: return
        self._val = v
        self.edit.setText(str(self._val))
        self.valueChanged.emit(self._val)

    def setRange(self, minimum: int, maximum: int):
        self._min, self._max = int(minimum), int(maximum)
        self.edit.setValidator(QIntValidator(self._min, self._max, self))
        self.setValue(self._val)

    def _on_text(self, s: str):
        try:
            self.setValue(int(s or "0"))
        except ValueError:
            pass

    def _step_by(self, d: int):
        self.setValue(self._val + d)
