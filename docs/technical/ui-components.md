# UI Components Documentation

## Overview
MesmerGlass uses PyQt6 for its user interface, providing a modular, responsive design with multiple specialized components.

## Main Components

### 1. Launcher Window
```python
class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MesmerGlass")
        self._build_ui()
```

#### Core Features
- Tab-based interface
- Media controls
- Device settings
- Launch/Stop functionality
- Status indicators

### 2. Page Components

#### MediaPage
```python
class MediaPage(QWidget):
    """Handles video selection and opacity controls"""
    def __init__(self):
        super().__init__()
        self._setup_video_controls()
        self._setup_opacity_sliders()
```

#### TextFxPage
```python
class TextFxPage(QWidget):
    """Text effects and animation controls"""
    textChanged = pyqtSignal(str)
    fxModeChanged = pyqtSignal(str)
    fxIntensityChanged = pyqtSignal(float)
```

#### AudioPage
```python
class AudioPage(QWidget):
    """Dual audio track controls"""
    vol1Changed = pyqtSignal(float)
    vol2Changed = pyqtSignal(float)
```

#### DevicePage
```python
class DevicePage(QWidget):
    """Device connection and control settings"""
    deviceConnected = pyqtSignal(str)
    intensityChanged = pyqtSignal(float)
```

### 3. Common Widgets

#### Custom Sliders
```python
class OpacitySlider(QSlider):
    """Custom slider with percentage display"""
    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.setRange(0, 100)
        self.valueChanged.connect(self._update_label)
```

#### File Selectors
```python
class FileSelector(QWidget):
    """File selection with preview"""
    fileSelected = pyqtSignal(str)
    
    def show_dialog(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", 
            "Media Files (*.mp4 *.mov *.mp3 *.wav)"
        )
```

## Styling

### Theme System
```python
def apply_theme(widget):
    """Apply consistent styling"""
    widget.setStyleSheet("""
        QMainWindow {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QGroupBox {
            border: 1px solid #3f3f3f;
            border-radius: 4px;
            margin-top: 8px;
        }
        QPushButton {
            background-color: #3f3f3f;
            border: none;
            padding: 5px 15px;
            border-radius: 3px;
        }
    """)
```

### Layout Guidelines
```python
def create_form_layout():
    """Standard form layout with consistent spacing"""
    layout = QFormLayout()
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)
    return layout
```

## Event Handling

### Signal Connections
```python
class MainWindow:
    def _connect_signals(self):
        """Connect all component signals"""
        self.media_page.opacityChanged.connect(self._handle_opacity)
        self.text_page.textChanged.connect(self._handle_text)
        self.device_page.deviceConnected.connect(self._handle_device)
```

### State Management
```python
class StateManager:
    """Manage application state"""
    def __init__(self):
        self.states = {
            "running": False,
            "device_connected": False,
            "overlay_visible": False
        }
        
    def update_state(self, key: str, value: Any):
        """Update state and notify observers"""
        self.states[key] = value
        self.state_changed.emit(key, value)
```

## Overlay Windows

### OverlayWindow
```python
class OverlayWindow(QWidget):
    """Click-through overlay window"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
```

### Multi-Monitor Support
```python
def create_overlays(self):
    """Create overlay for each selected display"""
    for screen in QGuiApplication.screens():
        if screen.name() in self.selected_displays:
            overlay = OverlayWindow()
            overlay.setGeometry(screen.geometry())
            self.overlays.append(overlay)
```

## Testing

### Widget Tests
```python
def test_opacity_slider():
    slider = OpacitySlider()
    slider.setValue(50)
    assert slider.value() == 50
    assert slider.label.text() == "50%"

def test_file_selector():
    selector = FileSelector()
    assert selector.file_types == "Media Files (*.mp4 *.mov *.mp3 *.wav)"
```

### Integration Tests
```python
def test_launcher_window():
    launcher = Launcher()
    launcher.show()
    assert launcher.isVisible()
    assert len(launcher.findChildren(QTabWidget)) == 1
```

## Best Practices

### UI Design
1. Consistent margins and spacing
2. Clear visual hierarchy
3. Responsive layouts
4. Efficient updates

### Performance
1. Minimize redraws
2. Buffer video frames
3. Async loading
4. Resource cleanup

### Error Handling
1. User feedback
2. Graceful degradation
3. Recovery options
4. Clear messaging

### Accessibility
1. Keyboard navigation
2. Screen reader support
3. High contrast support
4. Font scaling
