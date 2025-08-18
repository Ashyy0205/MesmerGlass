# mesmerglass/qss.py
# Noir Glass theme tweaked: clearer spinbox buttons, larger toggle pills, warm Solar accent

QSS = r"""
/* -------- Base -------- */
* {
  font-family: "Segoe UI", "Inter", system-ui, sans-serif;
  font-size: 10.5pt;
  color: #E8ECF5;
}
QWidget     { background: #0B0F14; }
QMainWindow { background: #0B0F14; }
QScrollArea { background: transparent; border: none; }

/* No native focus glow */
*:focus { outline: 0; }
QAbstractButton:focus,
QLineEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QComboBox:focus { outline: none; }

/* -------- Cards -------- */
QGroupBox {
  background: rgba(18, 24, 32, 0.68);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px;
  margin-top: 14px;
  padding: 12px 12px 14px 12px;
}
QGroupBox::title {
  subcontrol-origin: margin;
  subcontrol-position: top left;
  padding: 0 8px;
  margin-left: 6px;
  color: #D5DEEE;
  font-weight: 600;
  letter-spacing: .2px;
}

/* -------- Field "bubbles" -------- */
QLabel { color: #C9D3E6; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
  background: rgba(16, 21, 28, 0.96);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 10px;
  padding: 6px 8px;
  selection-background-color: #FF9A3C;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
  border: 1px solid rgba(255,168,76,0.55);
  background: rgba(16, 21, 28, 0.98);  /* slightly darker when focused */
}

/* SpinBox buttons: make arrows area visible */
QSpinBox::up-button, QDoubleSpinBox::up-button {
  width: 22px; background: rgba(255,255,255,0.14);
  border-left: 1px solid rgba(255,255,255,0.12);
  border-top-right-radius: 10px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
  width: 22px; background: rgba(255,255,255,0.14);
  border-left: 1px solid rgba(255,255,255,0.12);
  border-bottom-right-radius: 10px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
  background: rgba(255,255,255,0.22);
}

/* -------- Buttons (Solar accent) -------- */
QPushButton {
  background: rgba(255,154,60,0.14);
  border: 1px solid rgba(255,154,60,0.42);
  border-radius: 12px;
  padding: 6px 12px;
}
QPushButton:hover  { background: rgba(255,154,60,0.22); }
QPushButton:pressed{ background: rgba(255,154,60,0.30); }
QPushButton:disabled { opacity: .55; }

/* -------- Sliders -------- */
QSlider::groove:horizontal {
  height: 6px; border-radius: 4px;
  background: rgba(255,255,255,0.10);
}
QSlider::sub-page:horizontal {
  border-radius: 4px;
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #FF8A00, stop:1 #FFD36B);
}
QSlider::handle:horizontal {
  width: 14px; height: 14px; margin: -6px 0;
  border-radius: 9px; background: #FF9A3C; border: 2px solid #111722;
}

/* -------- Checkboxes as toggle pills -------- */
QCheckBox::indicator { width: 36px; height: 20px; }
QCheckBox::indicator:unchecked {
  border-radius: 10px;
  background: rgba(255,255,255,0.16);
}
QCheckBox::indicator:checked {
  border-radius: 10px;
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #FF8A00, stop:1 #FFD36B);
}

/* -------- Sidebar (nav) -------- */
#Nav {
  min-width: 200px; max-width: 200px;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px;
  background: rgba(13, 18, 26, 0.6);
  padding: 4px;
}
QListWidget#Nav::item {
  padding: 10px 10px;
  border-radius: 8px;
}
QListWidget#Nav::item:selected {
  background: rgba(255,168,76,0.18);
  color: #FFE6C7;
  border: 1px solid rgba(255,168,76,0.35);
}

/* -------- Footer -------- */
#footerBar {
  background: rgba(16, 22, 30, 0.92);
  border-top: 1px solid rgba(255,255,255,0.08);
}
#statusChip {
  padding: 4px 8px;
  border-radius: 10px;
  background: rgba(255,255,255,0.10);
}
"""
