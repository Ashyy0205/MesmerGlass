from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QComboBox, QSlider, QGroupBox, QHBoxLayout, QColorDialog

try:  # pragma: no cover
    UnitSpin  # type: ignore[name-defined]
except NameError:  # pragma: no cover
    from ..widgets import UnitSpin

def _card(title: str) -> QGroupBox: return QGroupBox(title)

def _pct_label(v: int) -> QLabel:
    lab = QLabel(f"{v}%"); lab.setMinimumWidth(42)
    lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); return lab

def _row(caption: str, widget, extra=None) -> QWidget:
    w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(8,4,8,4); lay.setSpacing(8)
    lab = QLabel(caption); lab.setMinimumWidth(140)
    lay.addWidget(lab); lay.addWidget(widget,1)
    if extra is not None: lay.addWidget(extra)
    return w

class TextFxPage(QWidget):
    textChanged = pyqtSignal(str)
    textScaleChanged = pyqtSignal(int)
    fxModeChanged = pyqtSignal(str)
    fxIntensityChanged = pyqtSignal(int)
    flashIntervalChanged = pyqtSignal(int)
    flashWidthChanged = pyqtSignal(int)
    loadPackRequested = pyqtSignal()
    createPackRequested = pyqtSignal()
    colorChanged = pyqtSignal(str)

    def __init__(self, *, text: str, text_scale_pct: int, fx_mode: str, fx_intensity: int, flash_interval_ms: int, flash_width_ms: int, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(10)

        # Pack group
        card_pack = _card("Message Pack"); pv = QVBoxLayout(card_pack); pv.setContentsMargins(12,10,12,12); pv.setSpacing(4)
        row = QWidget(); hl = QHBoxLayout(row); hl.setContentsMargins(8,6,8,6); hl.setSpacing(8)
        lab = QLabel("Current pack"); lab.setMinimumWidth(110)
        self.lab_pack_name = QLabel("(none)")
        btn_load = QPushButton("Load…"); btn_load.setToolTip("Load a message pack (weighted random per flash)")
        btn_create = QPushButton("Create Pack…"); btn_create.setToolTip("Open pack editor")
        hl.addWidget(lab); hl.addWidget(self.lab_pack_name,1); hl.addWidget(btn_load); hl.addWidget(btn_create)
        pv.addWidget(row); root.addWidget(card_pack)

        # Text & FX group
        card_txtfx = _card("Text & FX"); cv = QVBoxLayout(card_txtfx); cv.setContentsMargins(12,10,12,12); cv.setSpacing(4)
        self.lab_text = QLabel(text); self.lab_text.hide()
        self._color_value = "#FFFFFF"; self.btn_color = QPushButton("Text Colour…")
        self.lab_color_preview = QLabel(self._color_value); self.lab_color_preview.setMinimumWidth(70)
        self.lab_color_preview.setStyleSheet(f"background:{self._color_value}; border:1px solid #555; padding:2px;")
        cv.addWidget(_row("Text colour", self.btn_color, self.lab_color_preview))
        self.sld_txt_scale = QSlider(Qt.Orientation.Horizontal); self.sld_txt_scale.setRange(8,60); self.sld_txt_scale.setValue(int(text_scale_pct))
        self.lab_txt_scale = _pct_label(self.sld_txt_scale.value()); cv.addWidget(_row("Size (% height)", self.sld_txt_scale, self.lab_txt_scale))
        self.cmb_fx = QComboBox(); self.cmb_fx.addItems(["Breath + Sway","Shimmer","Tunnel","Subtle"]); self.cmb_fx.setCurrentText(fx_mode); cv.addWidget(_row("FX style", self.cmb_fx))
        self.sld_fx_int = QSlider(Qt.Orientation.Horizontal); self.sld_fx_int.setRange(0,100); self.sld_fx_int.setValue(int(fx_intensity))
        self.lab_fx_pct = _pct_label(self.sld_fx_int.value()); cv.addWidget(_row("FX intensity", self.sld_fx_int, self.lab_fx_pct))
        root.addWidget(card_txtfx)

        # Flash group
        card_flash = _card("Flash"); fv = QVBoxLayout(card_flash); fv.setContentsMargins(12,10,12,12); fv.setSpacing(4)
        self.spin_interval = UnitSpin(200,10000,flash_interval_ms,"ms",step=50,tooltip="Time between flashes",width=160); fv.addWidget(_row("Interval", self.spin_interval))
        self.spin_width = UnitSpin(50,3000,flash_width_ms,"ms",step=25,tooltip="Flash visible duration",width=160); fv.addWidget(_row("Width", self.spin_width))
        root.addWidget(card_flash); root.addStretch(1)

        # Wiring
        self.sld_txt_scale.valueChanged.connect(self._on_txt_scale)
        self.cmb_fx.currentTextChanged.connect(self.fxModeChanged.emit)
        self.sld_fx_int.valueChanged.connect(self._on_fx_int)
        self.spin_interval.valueChanged.connect(self.flashIntervalChanged.emit)
        self.spin_width.valueChanged.connect(self.flashWidthChanged.emit)
        btn_load.clicked.connect(self.loadPackRequested.emit)
        btn_create.clicked.connect(self.createPackRequested.emit)
        self.btn_color.clicked.connect(self._choose_color)
        self._btn_load_pack = btn_load; self._btn_create_pack = btn_create

    def set_text(self, text: str):
        try: self.lab_text.setText(text)
        except Exception: pass
        self.textChanged.emit(text)
    def set_pack_name(self, name: str | None): self.lab_pack_name.setText(name or "(none)")
    def _on_txt_scale(self, v: int): self.lab_txt_scale.setText(f"{v}%"); self.textScaleChanged.emit(v)
    def _on_fx_int(self, v: int): self.lab_fx_pct.setText(f"{v}%"); self.fxIntensityChanged.emit(v)
    def is_auto_cycle_enabled(self) -> bool: return True
    def cycle_interval_secs(self) -> int: return 5
    def _choose_color(self):
        try:
            col = QColorDialog.getColor();
            if not col.isValid(): return
            self._color_value = col.name(); self.lab_color_preview.setText(self._color_value)
            self.lab_color_preview.setStyleSheet(f"background:{self._color_value}; border:1px solid #555; padding:2px;")
            self.colorChanged.emit(self._color_value)
        except Exception: pass


        def _row(caption: str, widget, extra=None) -> QWidget:
            w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(8, 4, 8, 4); lay.setSpacing(8)
            lab = QLabel(caption); lab.setMinimumWidth(140)
            lay.addWidget(lab)
            lay.addWidget(widget, 1)
            if extra is not None:
                lay.addWidget(extra)
            return w


        class TextFxPage(QWidget):
            textChanged = pyqtSignal(str)
            textScaleChanged = pyqtSignal(int)
            fxModeChanged = pyqtSignal(str)
            fxIntensityChanged = pyqtSignal(int)
            flashIntervalChanged = pyqtSignal(int)
            flashWidthChanged = pyqtSignal(int)
            loadPackRequested = pyqtSignal()
            createPackRequested = pyqtSignal()
            colorChanged = pyqtSignal(str)

            def __init__(self, *, text: str, text_scale_pct: int, fx_mode: str, fx_intensity: int, flash_interval_ms: int, flash_width_ms: int, parent=None):
                super().__init__(parent)
                root = QVBoxLayout(self); root.setContentsMargins(6, 6, 6, 6); root.setSpacing(10)

                # Message Pack group (no cycle spin)
                card_pack = _card("Message Pack")
                pv = QVBoxLayout(card_pack); pv.setContentsMargins(12, 10, 12, 12); pv.setSpacing(4)
                row = QWidget(); hl = QHBoxLayout(row); hl.setContentsMargins(8, 6, 8, 6); hl.setSpacing(8)
                lab = QLabel("Current pack"); lab.setMinimumWidth(110)
                self.lab_pack_name = QLabel("(none)")
                btn_load = QPushButton("Load…"); btn_load.setToolTip("Load a message pack JSON (weighted random selection)")
                btn_create = QPushButton("Create Pack…"); btn_create.setToolTip("Open editor to create / save a new message pack")
                hl.addWidget(lab); hl.addWidget(self.lab_pack_name, 1); hl.addWidget(btn_load); hl.addWidget(btn_create)
                pv.addWidget(row)
                root.addWidget(card_pack)

                # Text & FX group
                card_txtfx = _card("Text & FX")
                cv = QVBoxLayout(card_txtfx); cv.setContentsMargins(12, 10, 12, 12); cv.setSpacing(4)
                from PyQt6.QtCore import Qt, pyqtSignal
                from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QComboBox, QSlider, QGroupBox, QHBoxLayout, QColorDialog

                try:  # pragma: no cover
                    UnitSpin  # type: ignore[name-defined]
                except NameError:  # pragma: no cover
                    from ..widgets import UnitSpin

                def _card(title: str) -> QGroupBox: return QGroupBox(title)

                def _pct_label(v: int) -> QLabel:
                    lab = QLabel(f"{v}%"); lab.setMinimumWidth(42)
                    lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); return lab

                def _row(caption: str, widget, extra=None) -> QWidget:
                    w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(8,4,8,4); lay.setSpacing(8)
                    lab = QLabel(caption); lab.setMinimumWidth(140)
                    lay.addWidget(lab); lay.addWidget(widget, 1)
                    if extra is not None: lay.addWidget(extra)
                    return w

                class TextFxPage(QWidget):
                    textChanged = pyqtSignal(str)
                    textScaleChanged = pyqtSignal(int)
                    fxModeChanged = pyqtSignal(str)
                    fxIntensityChanged = pyqtSignal(int)
                    flashIntervalChanged = pyqtSignal(int)
                    flashWidthChanged = pyqtSignal(int)
                    loadPackRequested = pyqtSignal()
                    createPackRequested = pyqtSignal()
                    colorChanged = pyqtSignal(str)

                    def __init__(self, *, text: str, text_scale_pct: int, fx_mode: str, fx_intensity: int, flash_interval_ms: int, flash_width_ms: int, parent=None):
                        super().__init__(parent)
                        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(10)

                        # Pack group
                        card_pack = _card("Message Pack"); pv = QVBoxLayout(card_pack); pv.setContentsMargins(12,10,12,12); pv.setSpacing(4)
                        row = QWidget(); hl = QHBoxLayout(row); hl.setContentsMargins(8,6,8,6); hl.setSpacing(8)
                        lab = QLabel("Current pack"); lab.setMinimumWidth(110)
                        self.lab_pack_name = QLabel("(none)")
                        btn_load = QPushButton("Load…"); btn_load.setToolTip("Load a message pack JSON (weighted random per flash)")
                        btn_create = QPushButton("Create Pack…"); btn_create.setToolTip("Open editor to create/save a message pack")
                        hl.addWidget(lab); hl.addWidget(self.lab_pack_name,1); hl.addWidget(btn_load); hl.addWidget(btn_create)
                        pv.addWidget(row); root.addWidget(card_pack)

                        # Text / FX
                        card_txtfx = _card("Text & FX"); cv = QVBoxLayout(card_txtfx); cv.setContentsMargins(12,10,12,12); cv.setSpacing(4)
                        self.lab_text = QLabel(text); self.lab_text.hide()
                        self._color_value = "#FFFFFF"; self.btn_color = QPushButton("Text Colour…")
                        self.lab_color_preview = QLabel(self._color_value); self.lab_color_preview.setMinimumWidth(70)
                        self.lab_color_preview.setStyleSheet(f"background:{self._color_value}; border:1px solid #555; padding:2px;")
                        cv.addWidget(_row("Text colour", self.btn_color, self.lab_color_preview))
                        self.sld_txt_scale = QSlider(Qt.Orientation.Horizontal); self.sld_txt_scale.setRange(8,60); self.sld_txt_scale.setValue(int(text_scale_pct))
                        self.lab_txt_scale = _pct_label(self.sld_txt_scale.value()); cv.addWidget(_row("Size (% height)", self.sld_txt_scale, self.lab_txt_scale))
                        self.cmb_fx = QComboBox(); self.cmb_fx.addItems(["Breath + Sway","Shimmer","Tunnel","Subtle"]); self.cmb_fx.setCurrentText(fx_mode); cv.addWidget(_row("FX style", self.cmb_fx))
                        self.sld_fx_int = QSlider(Qt.Orientation.Horizontal); self.sld_fx_int.setRange(0,100); self.sld_fx_int.setValue(int(fx_intensity))
                        self.lab_fx_pct = _pct_label(self.sld_fx_int.value()); cv.addWidget(_row("FX intensity", self.sld_fx_int, self.lab_fx_pct))
                        root.addWidget(card_txtfx)

                        # Flash
                        card_flash = _card("Flash"); fv = QVBoxLayout(card_flash); fv.setContentsMargins(12,10,12,12); fv.setSpacing(4)
                        self.spin_interval = UnitSpin(200,10000,flash_interval_ms,"ms",step=50,tooltip="Time between flashes",width=160); fv.addWidget(_row("Interval", self.spin_interval))
                        self.spin_width = UnitSpin(50,3000,flash_width_ms,"ms",step=25,tooltip="Flash visible duration",width=160); fv.addWidget(_row("Width", self.spin_width))
                        root.addWidget(card_flash); root.addStretch(1)

                        # Wire
                        self.sld_txt_scale.valueChanged.connect(self._on_txt_scale)
                        self.cmb_fx.currentTextChanged.connect(self.fxModeChanged.emit)
                        self.sld_fx_int.valueChanged.connect(self._on_fx_int)
                        self.spin_interval.valueChanged.connect(self.flashIntervalChanged.emit)
                        self.spin_width.valueChanged.connect(self.flashWidthChanged.emit)
                        btn_load.clicked.connect(self.loadPackRequested.emit)
                        btn_create.clicked.connect(self.createPackRequested.emit)
                        self.btn_color.clicked.connect(self._choose_color)
                        self._btn_load_pack = btn_load; self._btn_create_pack = btn_create

                    def set_text(self, text: str):
                        try: self.lab_text.setText(text)
                        except Exception: pass
                        self.textChanged.emit(text)
                    def set_pack_name(self, name: str | None): self.lab_pack_name.setText(name or "(none)")
                    def _on_txt_scale(self, v: int): self.lab_txt_scale.setText(f"{v}%"); self.textScaleChanged.emit(v)
                    def _on_fx_int(self, v: int): self.lab_fx_pct.setText(f"{v}%"); self.fxIntensityChanged.emit(v)
                    def is_auto_cycle_enabled(self) -> bool: return True
                    def cycle_interval_secs(self) -> int: return 5  # legacy
                    def _choose_color(self):
                        try:
                            col = QColorDialog.getColor()
                            if not col.isValid(): return
                            self._color_value = col.name(); self.lab_color_preview.setText(self._color_value)
                            self.lab_color_preview.setStyleSheet(f"background:{self._color_value}; border:1px solid #555; padding:2px;")
                            self.colorChanged.emit(self._color_value)
                        except Exception: pass