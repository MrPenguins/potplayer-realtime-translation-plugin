"""
Transparent subtitle overlay for PotPlayer real-time translation.

Displays a single translated subtitle at the bottom of the screen.
Fades out when no new subtitle arrives for max_idle_seconds.
"""

import sys
import requests
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QFont, QColor


# ── Configuration (loaded from server or defaults) ───────────────────────

SERVER_URL = "http://127.0.0.1:5000"
POLL_INTERVAL_MS = 500
DEFAULT_MAX_IDLE_SECONDS = 3.0
DEFAULT_FONT_SIZE = 28
DEFAULT_FONT_FAMILY = "Microsoft YaHei, Arial"
DEFAULT_BOTTOM_OFFSET = 150
DEFAULT_FADE_OUT_MS = 500


class FadeLabel(QWidget):
    """
    A label with an opacity property for fade-in/out animation.

    Wraps a QLabel inside a layout. Uses the window's windowOpacity
    on the parent overlay for the actual fade.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._opacity = 1.0

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, value):
        self._opacity = value
        # Update the parent overlay's opacity
        parent = self.parent()
        if parent:
            parent.setWindowOpacity(value)


class SubtitleOverlay(QWidget):
    """
    Frameless, always-on-top, mouse-transparent overlay window.

    Polls the translation server for current subtitle text and renders it
    centered at the bottom of the screen. Fades out when idle.
    """

    def __init__(self):
        super().__init__()

        # Load settings from server
        self._load_server_settings()

        self.initUI()

        # Poll timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_subtitle)
        self.timer.start(POLL_INTERVAL_MS)

        # State tracking
        self.last_text = ""
        self.idle_count = 0  # number of consecutive empty polls

        # Fade animation
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(self.fade_out_ms)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fading_out = False

    def _load_server_settings(self):
        """Fetch settings from the translation server, falling back to defaults."""
        self.font_size = DEFAULT_FONT_SIZE
        self.font_family = DEFAULT_FONT_FAMILY
        self.bottom_offset = DEFAULT_BOTTOM_OFFSET
        self.max_idle_seconds = DEFAULT_MAX_IDLE_SECONDS
        self.fade_out_ms = DEFAULT_FADE_OUT_MS

        try:
            resp = requests.get(f"{SERVER_URL}/config", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                sub = data.get("subtitle", {})
                self.font_size = sub.get("font_size", DEFAULT_FONT_SIZE)
                self.font_family = sub.get("font_family", DEFAULT_FONT_FAMILY)
                self.bottom_offset = sub.get("bottom_offset", DEFAULT_BOTTOM_OFFSET)
                self.max_idle_seconds = sub.get("max_idle_seconds", DEFAULT_MAX_IDLE_SECONDS)
                self.fade_out_ms = sub.get("fade_out_ms", DEFAULT_FADE_OUT_MS)
        except Exception:
            # Server not running yet — use defaults, will retry
            pass

    def initUI(self):
        """Set up the transparent overlay window."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.0)  # start hidden

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel("", self)
        self.label.setStyleSheet(
            f"""
            QLabel {{
                color: #FFFFFF;
                background-color: rgba(0, 0, 0, 160);
                padding: 10px 20px;
                border-radius: 10px;
                font-family: "{self.font_family}";
                font-size: {self.font_size}px;
                font-weight: bold;
            }}
            """
        )
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(self._screen_width() - 200)

        layout.addWidget(self.label)
        self.setLayout(layout)

        # Position at bottom center
        self._center_at_bottom()

    def _screen_width(self):
        return QApplication.primaryScreen().geometry().width()

    def _screen_height(self):
        return QApplication.primaryScreen().geometry().height()

    def _center_at_bottom(self):
        """Position the window centered at the bottom of the screen."""
        screen = QApplication.primaryScreen().geometry()
        width = min(1200, screen.width() - 200)  # max width with margins
        height = 120
        x = (screen.width() - width) // 2
        y = screen.height() - height - self.bottom_offset
        self.setGeometry(x, y, width, height)

    def update_subtitle(self):
        """Poll the server for the current subtitle."""
        try:
            resp = requests.get(f"{SERVER_URL}/subtitle", timeout=1.0)
            if resp.status_code == 200:
                text = resp.json().get("text", "")
            else:
                text = ""
        except Exception:
            text = ""

        # Normalize
        text = text.strip() if text else ""

        # ── Handle subtitle lifecycle ──
        if text:
            self.idle_count = 0
            if text != self.last_text:
                self.label.setText(text)
                self.label.adjustSize()
                self.adjustSize()
                self._recenter()
                self.last_text = text

            # Ensure visible (no animation conflict)
            if self._fading_out:
                self.fade_anim.stop()
                self._fading_out = False
            self.setWindowOpacity(1.0)

        else:
            # No subtitle — start counting idle polls
            self.idle_count += 1
            idle_seconds = self.idle_count * (POLL_INTERVAL_MS / 1000.0)

            if idle_seconds >= self.max_idle_seconds and not self._fading_out:
                if self.windowOpacity() > 0.01:
                    self._start_fade_out()

    def _start_fade_out(self):
        """Animate window opacity to 0."""
        self._fading_out = True
        self.fade_anim.setStartValue(self.windowOpacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(self._on_fade_finished)
        self.fade_anim.start()

    def _on_fade_finished(self):
        """After fade out, clear the label text."""
        self._fading_out = False
        self.label.setText("")
        self.last_text = ""

    def _recenter(self):
        """Re-center the overlay horizontally after size changes."""
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        self.move(x, self.y())


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)

    # Prevent the application from showing in taskbar / Alt+Tab
    # (Tool flag already handles this)

    overlay = SubtitleOverlay()
    overlay.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
