"""Kait Intel -- Modern dark-mode PyQt GUI for the Kait AI Sidekick.

Ground-up rewrite with a professional 3-panel + tabs layout:

    +---------------------------------------------------------+
    | [Kait Intel]         [Tokens: 1.2k/128k] [GPU ...]     | <- Status Bar
    +----------------------+----------------------------------+
    |                      | [Chat] [Observatory] [Monitor]   | <- Tab Bar
    |   Chat Messages      |                                  |
    |   (scrollable,       |  Observatory/Monitor content     |
    |    dark bubbles,     |                                  |
    |    timestamps,       |                                  |
    |    sentiment color   |                                  |
    |    accents)          |                                  |
    +----------------------+----------------------------------+
    | [Attach] [ Type... ] [Send] [Mic] [Speaker]             | <- Input Bar
    +----------------------+----------------------------------+
    | * Ollama: connected  * Claude: ready  * TTS: ElevenLabs | <- Footer
    +---------------------------------------------------------+

Dark mode only.  No pygame.  No external assets.

Dependencies:
    pip install PyQt6   (or PyQt5 as fallback)
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Qt imports (PyQt6 preferred, PyQt5 fallback)
# ---------------------------------------------------------------------------
_QT_AVAILABLE = False
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel,
        QProgressBar, QGroupBox, QScrollArea, QFrame, QDialog,
        QComboBox, QCheckBox, QStackedWidget, QSizePolicy,
        QToolBar, QStatusBar, QMessageBox, QTabWidget, QFileDialog,
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QSize, pyqtSignal, pyqtSlot, QThread,
        QPropertyAnimation, QEasingCurve, QObject,
    )
    from PyQt6.QtGui import (
        QImage, QPixmap, QFont, QColor, QPalette, QIcon,
        QTextCursor, QKeySequence, QPainter, QBrush, QPen,
        QLinearGradient, QAction,
    )
    _QT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtWidgets import (  # type: ignore[no-redef]
            QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel,
            QProgressBar, QGroupBox, QScrollArea, QFrame, QDialog,
            QComboBox, QCheckBox, QStackedWidget, QSizePolicy,
            QAction, QToolBar, QStatusBar, QMessageBox, QTabWidget, QFileDialog,
        )
        from PyQt5.QtCore import (  # type: ignore[no-redef]
            Qt, QTimer, QSize, pyqtSignal, pyqtSlot, QThread,
            QPropertyAnimation, QEasingCurve, QObject,
        )
        from PyQt5.QtGui import (  # type: ignore[no-redef]
            QImage, QPixmap, QFont, QColor, QPalette, QIcon,
            QTextCursor, QKeySequence, QPainter, QBrush, QPen,
            QLinearGradient,
        )
        _QT_AVAILABLE = True
    except ImportError:
        pass


# ===================================================================
# AudioCueManager -- stub (pygame removed)
# ===================================================================

class AudioCueManager:
    """Stub retained for backward-compatibility.  Pygame has been removed.

    All methods are safe no-ops.  The ``_CUE_DEFS`` dict is kept so that
    existing tests checking cue names continue to pass.
    """

    _CUE_DEFS: Dict[str, List[tuple]] = {
        "message_sent":     [(660, 60, 0.25)],
        "message_received": [(520, 80, 0.2)],
        "kait_moment":     [(880, 80, 0.3), (1100, 100, 0.35)],
        "error":            [(220, 150, 0.3)],
        "startup":          [(440, 100, 0.2), (550, 100, 0.25), (660, 140, 0.3)],
    }

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = False  # always disabled -- no pygame backend

    @property
    def enabled(self) -> bool:
        return False

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def play_cue(self, name: str) -> None:
        """No-op."""


# ===================================================================
# Theme -- dark-mode colour palette (single theme, the canonical one)
# ===================================================================

class Theme:
    """Dark-mode colour palette -- the only palette for the new design."""

    # Core backgrounds
    BG_PRIMARY = "#0D0D0D"
    BG_SECONDARY = "#1A1A2E"
    BG_TERTIARY = "#16213E"
    BG_INPUT = "#1A1A2E"

    # Text
    TEXT_PRIMARY = "#E8E8E8"
    TEXT_SECONDARY = "#888899"
    TEXT_DIM = "#555566"

    # Accents
    ACCENT_BLUE = "#00D4FF"      # electric cyan (primary)
    ACCENT_PURPLE = "#7B2FBE"    # deep purple (secondary)
    ACCENT_GOLD = "#FFB800"      # warning / warm accent
    ACCENT_KAIT = "#7B2FBE"     # alias for legacy code paths
    ACCENT_GREEN = "#00FF88"     # success
    ACCENT_RED = "#FF3366"       # error

    # Chat bubbles
    BUBBLE_USER = "#16213E"
    BUBBLE_AI = "#1A1A2E"

    # Borders
    BORDER = "#2A2A3E"

    # Scrollbar
    SCROLLBAR_BG = "#0D0D0D"
    SCROLLBAR_HANDLE = "#2A2A3E"

    # Sentiment
    SENTIMENT_POSITIVE = "#00FF88"
    SENTIMENT_NEGATIVE = "#FF3366"
    SENTIMENT_NEUTRAL = "#888899"

    # Attachment chips (legacy compat)
    ATTACHMENT_BG = "#16213E"
    ATTACHMENT_BORDER = "#2A2A3E"
    ATTACHMENT_ICON_COLOR = "#00D4FF"
    DROP_OVERLAY = "rgba(0, 212, 255, 0.12)"


# ---------------------------------------------------------------------------
# Legacy theme aliases -- kept for backward-compatible imports / tests
# ---------------------------------------------------------------------------

class HighContrastTheme:
    """High-contrast dark variant (legacy compat)."""

    BG_PRIMARY = "#000000"
    BG_SECONDARY = "#0a0a0a"
    BG_TERTIARY = "#1a1a1a"
    BG_INPUT = "#1a1a1a"
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#cccccc"
    TEXT_DIM = "#999999"
    ACCENT_BLUE = "#00D4FF"
    ACCENT_GOLD = "#FFB800"
    ACCENT_KAIT = "#7B2FBE"
    ACCENT_GREEN = "#00FF88"
    ACCENT_RED = "#FF3366"
    ACCENT_PURPLE = "#7B2FBE"
    BORDER = "#444444"
    BUBBLE_USER = "#001a33"
    BUBBLE_AI = "#1a0033"
    SCROLLBAR_BG = "#0a0a0a"
    SCROLLBAR_HANDLE = "#444444"
    SENTIMENT_POSITIVE = "#00FF88"
    SENTIMENT_NEGATIVE = "#FF3366"
    SENTIMENT_NEUTRAL = "#cccccc"
    ATTACHMENT_BG = "#0d1b2a"
    ATTACHMENT_BORDER = "#1b3a5c"
    ATTACHMENT_ICON_COLOR = "#00D4FF"
    DROP_OVERLAY = "rgba(0, 212, 255, 0.15)"


class LightTheme:
    """Light theme stub (legacy compat -- UI is dark-mode only)."""

    BG_PRIMARY = "#f0f2f8"
    BG_SECONDARY = "#ffffff"
    BG_TERTIARY = "#e8eaf0"
    BG_INPUT = "#ffffff"
    TEXT_PRIMARY = "#1a1e35"
    TEXT_SECONDARY = "#505878"
    TEXT_DIM = "#8890a8"
    ACCENT_BLUE = "#00A0CC"
    ACCENT_GOLD = "#cc8800"
    ACCENT_KAIT = "#6B1FAE"
    ACCENT_GREEN = "#00CC66"
    ACCENT_RED = "#DD2255"
    ACCENT_PURPLE = "#6B1FAE"
    BORDER = "#c8cce0"
    BUBBLE_USER = "#dde4f8"
    BUBBLE_AI = "#eeddf8"
    SCROLLBAR_BG = "#e8eaf0"
    SCROLLBAR_HANDLE = "#c8cce0"
    SENTIMENT_POSITIVE = "#00CC66"
    SENTIMENT_NEGATIVE = "#DD2255"
    SENTIMENT_NEUTRAL = "#505878"
    ATTACHMENT_BG = "#e0e4f0"
    ATTACHMENT_BORDER = "#c8cce0"
    ATTACHMENT_ICON_COLOR = "#00A0CC"
    DROP_OVERLAY = "rgba(0, 160, 204, 0.12)"


THEMES = {
    "dark": Theme,
    "high_contrast": HighContrastTheme,
    "light": LightTheme,
}

_THEME_CYCLE = ["dark", "high_contrast", "light"]


# ===================================================================
# Stylesheet builder
# ===================================================================

def build_stylesheet(theme: type = Theme) -> str:
    """Build a comprehensive Qt stylesheet from a theme class."""
    return f"""
/* ---- Global ---- */
QMainWindow, QWidget {{
    background-color: {theme.BG_PRIMARY};
    color: {theme.TEXT_PRIMARY};
    font-family: 'Inter', 'SF Pro Display', 'Segoe UI', 'Helvetica Neue', sans-serif;
    font-size: 13px;
}}

/* ---- Splitter ---- */
QSplitter::handle {{
    background: {theme.BORDER};
    width: 2px;
}}
QSplitter::handle:hover {{
    background: {theme.ACCENT_BLUE};
}}

/* ---- Line Edit ---- */
QLineEdit {{
    background-color: {theme.BG_INPUT};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    selection-background-color: {theme.ACCENT_BLUE};
}}
QLineEdit:focus {{
    border: 1px solid {theme.ACCENT_BLUE};
}}

/* ---- Text Edit ---- */
QTextEdit {{
    background-color: {theme.BG_SECONDARY};
    color: {theme.TEXT_PRIMARY};
    border: none;
    border-radius: 4px;
    padding: 8px;
    font-size: 14px;
}}
QTextEdit#promptInput {{
    background-color: {theme.BG_INPUT};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
}}
QTextEdit#promptInput:focus {{
    border: 1px solid {theme.ACCENT_BLUE};
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {theme.BG_TERTIARY};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {theme.BORDER};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {theme.ACCENT_BLUE};
    color: #000000;
    border-color: {theme.ACCENT_BLUE};
}}
QPushButton:pressed {{
    background-color: #00AACC;
}}
QPushButton#sendBtn {{
    background-color: {theme.ACCENT_BLUE};
    color: #000000;
    font-weight: bold;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
}}
QPushButton#sendBtn:hover {{
    background-color: #33DDFF;
}}
QPushButton#attachBtn {{
    background-color: {theme.BG_TERTIARY};
    color: {theme.ATTACHMENT_ICON_COLOR};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 16px;
    font-weight: bold;
}}
QPushButton#attachBtn:hover {{
    background-color: {theme.ATTACHMENT_BG};
    border-color: {theme.ATTACHMENT_ICON_COLOR};
}}
QPushButton#micBtn {{
    background-color: {theme.BG_TERTIARY};
    color: {theme.ACCENT_BLUE};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
    padding: 8px 12px;
}}
QPushButton#micBtn:hover {{
    background-color: {theme.ACCENT_BLUE};
    color: #000000;
}}
QPushButton#speakerBtn {{
    background-color: {theme.BG_TERTIARY};
    color: {theme.ACCENT_BLUE};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
    padding: 8px 12px;
}}
QPushButton#speakerBtn:hover {{
    background-color: {theme.ACCENT_BLUE};
    color: #000000;
}}
QPushButton#jumpToBottom {{
    background-color: {theme.ACCENT_BLUE};
    color: #000000;
    border: none;
    border-radius: 14px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: bold;
}}

/* ---- Progress Bar ---- */
QProgressBar {{
    background-color: {theme.BG_INPUT};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {theme.ACCENT_BLUE}, stop:1 {theme.ACCENT_PURPLE});
    border-radius: 4px;
}}

/* ---- Group Box ---- */
QGroupBox {{
    background-color: {theme.BG_SECONDARY};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-size: 12px;
    color: {theme.TEXT_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: {theme.ACCENT_BLUE};
    font-weight: bold;
}}

/* ---- Labels ---- */
QLabel {{
    color: {theme.TEXT_PRIMARY};
}}
QLabel#dimLabel {{
    color: {theme.TEXT_DIM};
    font-size: 11px;
}}
QLabel#headerLabel {{
    color: {theme.ACCENT_BLUE};
    font-size: 16px;
    font-weight: bold;
}}
QLabel#secondaryLabel {{
    color: {theme.TEXT_SECONDARY};
    font-size: 12px;
}}

/* ---- Scroll Bars ---- */
QScrollBar:vertical {{
    background: {theme.SCROLLBAR_BG};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {theme.SCROLLBAR_HANDLE};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    height: 0;
}}

/* ---- Tab Widget ---- */
QTabWidget::pane {{
    background: {theme.BG_SECONDARY};
    border: 1px solid {theme.BORDER};
    border-top: none;
    border-radius: 0 0 8px 8px;
}}
QTabBar::tab {{
    background: {theme.BG_PRIMARY};
    color: {theme.TEXT_SECONDARY};
    padding: 8px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    border: 1px solid {theme.BORDER};
    border-bottom: none;
}}
QTabBar::tab:selected {{
    background: {theme.BG_SECONDARY};
    color: {theme.ACCENT_BLUE};
    font-weight: bold;
}}
QTabBar::tab:hover:!selected {{
    background: {theme.BG_TERTIARY};
    color: {theme.TEXT_PRIMARY};
}}

/* ---- Status Bar ---- */
QStatusBar {{
    background: {theme.BG_SECONDARY};
    color: {theme.TEXT_DIM};
    font-size: 11px;
    border-top: 1px solid {theme.BORDER};
}}

/* ---- Combo / Check ---- */
QComboBox {{
    background-color: {theme.BG_INPUT};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {theme.BORDER};
    border-radius: 6px;
    padding: 6px 10px;
}}
QCheckBox {{
    color: {theme.TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {theme.BORDER};
    border-radius: 4px;
    background: {theme.BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {theme.ACCENT_BLUE};
    border-color: {theme.ACCENT_BLUE};
}}
"""


# Global stylesheet
DARK_STYLESHEET = build_stylesheet(Theme)


# ===================================================================
# ChatMessage -- data class for a single message
# ===================================================================

class ChatMessage:
    """Data for a single chat message."""

    def __init__(
        self,
        role: str,          # "user" | "assistant" | "system"
        text: str,
        sentiment: str = "neutral",  # positive | negative | neutral
        timestamp: Optional[float] = None,
        attachments: Optional[List[Dict]] = None,
    ):
        self.role = role
        self.text = text
        self.sentiment = sentiment
        self.timestamp = timestamp or time.time()
        self.attachments: List[Dict] = attachments or []


# ===================================================================
# ChatMessageWidget -- individual styled message bubble
# ===================================================================

class ChatMessageWidget(QWidget if _QT_AVAILABLE else object):
    """A single chat message rendered as a dark bubble with sentiment border."""

    def __init__(self, message: "ChatMessage", parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        t = Theme

        # Determine styling based on role
        if message.role == "user":
            bg = t.BUBBLE_USER
            role_label = "You"
            role_color = t.ACCENT_BLUE
        elif message.role == "assistant":
            bg = t.BUBBLE_AI
            role_label = "Kait"
            role_color = t.ACCENT_PURPLE
        else:
            bg = t.BG_SECONDARY
            role_label = "System"
            role_color = t.TEXT_SECONDARY

        # Sentiment border color
        sentiment_colors = {
            "positive": t.SENTIMENT_POSITIVE,
            "negative": t.SENTIMENT_NEGATIVE,
            "neutral": t.SENTIMENT_NEUTRAL,
        }
        border_color = sentiment_colors.get(message.sentiment, t.SENTIMENT_NEUTRAL)

        ts = datetime.fromtimestamp(message.timestamp).strftime("%H:%M")

        self.setStyleSheet(
            f"ChatMessageWidget {{ "
            f"background-color: {bg}; "
            f"border-left: 3px solid {border_color}; "
            f"border-radius: 8px; "
            f"padding: 0px; "
            f"margin: 0px; "
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Header row: role + timestamp
        header = QHBoxLayout()
        header.setSpacing(8)

        role_lbl = QLabel(role_label)
        role_lbl.setStyleSheet(
            f"color: {role_color}; font-weight: bold; font-size: 12px; "
            f"background: transparent; border: none;"
        )
        header.addWidget(role_lbl)

        ts_lbl = QLabel(ts)
        ts_lbl.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        header.addWidget(ts_lbl)
        header.addStretch()
        layout.addLayout(header)

        # Message body
        body = QLabel(message.text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            if hasattr(Qt, "TextInteractionFlag")
            else Qt.TextSelectableByMouse
        )
        body.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: 14px; "
            f"background: transparent; border: none; "
            f"line-height: 1.5;"
        )
        layout.addWidget(body)


# ===================================================================
# ChatPanel -- scrollable list of ChatMessageWidget instances
# ===================================================================

class ChatPanel(QWidget if _QT_AVAILABLE else object):
    """Scrollable chat view with message bubbles, streaming, and jump-to-bottom."""

    def __init__(self, parent: Any = None, theme: type = Theme):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self._theme = theme
        self._messages: List[ChatMessage] = []
        self._streaming = False
        self._stream_tokens: List[str] = []
        self._stream_prefix = "Kait"
        self._streaming_widget: Optional[ChatMessageWidget] = None
        self._streaming_body: Optional[QLabel] = None
        self._auto_scroll = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area containing message widgets
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameStyle(QFrame.Shape.NoFrame if hasattr(QFrame, "Shape") else QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if hasattr(Qt, "ScrollBarPolicy")
            else Qt.ScrollBarAlwaysOff
        )
        self._scroll.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_moved)

        self._container = QWidget()
        self._container.setStyleSheet(f"background: {theme.BG_PRIMARY};")
        self._msg_layout = QVBoxLayout(self._container)
        self._msg_layout.setContentsMargins(8, 8, 8, 8)
        self._msg_layout.setSpacing(6)
        self._msg_layout.addStretch()

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

        # Jump-to-bottom button (hidden by default)
        self._jump_btn = QPushButton("Jump to latest")
        self._jump_btn.setObjectName("jumpToBottom")
        self._jump_btn.setFixedHeight(28)
        self._jump_btn.setVisible(False)
        self._jump_btn.clicked.connect(self._scroll_to_bottom)
        layout.addWidget(self._jump_btn, alignment=(
            Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter
        ))

    # --- public API ----------------------------------------------------------

    def add_message(self, msg_or_role: Any, text: str = "", sentiment: str = "neutral") -> None:
        """Add a message. Accepts ChatMessage *or* (role, text, sentiment) args."""
        if not _QT_AVAILABLE:
            return
        if isinstance(msg_or_role, ChatMessage):
            msg = msg_or_role
        else:
            msg = ChatMessage(str(msg_or_role), text, sentiment)
        self._messages.append(msg)
        widget = ChatMessageWidget(msg)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, widget)
        if self._auto_scroll:
            QTimer.singleShot(10, self._scroll_to_bottom)

    def begin_streaming(self, prefix: str = "Kait") -> None:
        """Start a streaming assistant message.  Tokens are appended via append_token()."""
        if not _QT_AVAILABLE:
            return
        t = self._theme
        self._streaming = True
        self._stream_tokens = []
        self._stream_prefix = prefix

        # Create a widget for the streaming bubble
        placeholder = ChatMessage("assistant", "\u2588", "neutral")
        widget = ChatMessageWidget(placeholder)
        self._streaming_widget = widget

        # Find the body QLabel inside the widget so we can update it
        for child in widget.findChildren(QLabel):
            if child.text() == "\u2588":
                self._streaming_body = child
                break

        self._msg_layout.insertWidget(self._msg_layout.count() - 1, widget)
        if self._auto_scroll:
            QTimer.singleShot(10, self._scroll_to_bottom)

    def append_token(self, token: str) -> None:
        """Append a token to the current streaming message."""
        if not _QT_AVAILABLE or not self._streaming:
            return
        self._stream_tokens.append(token)
        if self._streaming_body is not None:
            full_text = "".join(self._stream_tokens) + "\u2588"
            self._streaming_body.setText(full_text)
        if self._auto_scroll:
            QTimer.singleShot(10, self._scroll_to_bottom)

    def finish_streaming(self, sentiment: str = "neutral") -> str:
        """Finalise the streaming message, returning the full text."""
        if not _QT_AVAILABLE:
            return ""
        self._streaming = False
        full_text = "".join(self._stream_tokens)

        # Remove the cursor block character
        if self._streaming_body is not None:
            self._streaming_body.setText(full_text)

        # Record as a proper message
        if full_text:
            msg = ChatMessage("assistant", full_text, sentiment)
            self._messages.append(msg)

        self._streaming_widget = None
        self._streaming_body = None
        self._stream_tokens = []
        return full_text

    def clear_chat(self) -> None:
        if not _QT_AVAILABLE:
            return
        # Remove all message widgets
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._messages.clear()
        self._streaming = False

    def set_theme(self, theme: type) -> None:
        self._theme = theme

    # --- scrolling -----------------------------------------------------------

    def _scroll_to_bottom(self) -> None:
        if not _QT_AVAILABLE:
            return
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_range_changed(self, _min: int, _max: int) -> None:
        if self._auto_scroll:
            self._scroll_to_bottom()

    def _on_scroll_moved(self, value: int) -> None:
        sb = self._scroll.verticalScrollBar()
        at_bottom = value >= sb.maximum() - 20
        self._auto_scroll = at_bottom
        self._jump_btn.setVisible(not at_bottom)


# ===================================================================
# ObservatoryPanel -- pipeline stage viewer (placeholder)
# ===================================================================

class ObservatoryPanel(QWidget if _QT_AVAILABLE else object):
    """Placeholder panel showing pipeline stages and observatory data."""

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        t = Theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("Observatory")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        desc = QLabel(
            "Pipeline stage viewer.  Full Mermaid / D3 rendering "
            "is a future enhancement."
        )
        desc.setObjectName("secondaryLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Pipeline stages text view
        stages_group = QGroupBox("Pipeline Stages")
        stages_lay = QVBoxLayout(stages_group)

        self._stages_view = QTextEdit()
        self._stages_view.setReadOnly(True)
        self._stages_view.setStyleSheet(
            f"background: {t.BG_PRIMARY}; color: {t.TEXT_PRIMARY}; "
            f"font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 12px; "
            f"border: 1px solid {t.BORDER}; border-radius: 6px; padding: 8px;"
        )
        self._stages_view.setPlainText(
            "1. Input Processing    [ idle ]\n"
            "2. Agent Orchestration [ idle ]\n"
            "3. Context Assembly    [ idle ]\n"
            "4. LLM Generation     [ idle ]\n"
            "5. Response Rendering  [ idle ]\n"
        )
        stages_lay.addWidget(self._stages_view)
        layout.addWidget(stages_group)

        # Status text
        status_group = QGroupBox("Status")
        status_lay = QVBoxLayout(status_group)
        self._status_text = QLabel("No active observatory data.")
        self._status_text.setObjectName("dimLabel")
        self._status_text.setWordWrap(True)
        status_lay.addWidget(self._status_text)
        layout.addWidget(status_group)

        layout.addStretch()

    def update_stages(self, text: str) -> None:
        """Replace pipeline stages text."""
        if _QT_AVAILABLE:
            self._stages_view.setPlainText(text)

    def update_status(self, text: str) -> None:
        """Update status message."""
        if _QT_AVAILABLE:
            self._status_text.setText(text)


# ===================================================================
# ProcessingMonitorPanel -- real-time stats
# ===================================================================

class ProcessingMonitorPanel(QWidget if _QT_AVAILABLE else object):
    """Shows context window gauge, agent activity, model info, and metrics."""

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        t = Theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("Processing Monitor")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # --- Context Window Gauge ---
        ctx_group = QGroupBox("Context Window")
        ctx_lay = QVBoxLayout(ctx_group)

        self._ctx_bar = QProgressBar()
        self._ctx_bar.setRange(0, 128000)
        self._ctx_bar.setValue(0)
        self._ctx_bar.setFormat("%v / %m tokens")
        self._ctx_bar.setStyleSheet(
            f"QProgressBar {{ text-align: center; color: {t.TEXT_SECONDARY}; "
            f"height: 14px; font-size: 11px; background: {t.BG_INPUT}; "
            f"border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, "
            f"stop:0 {t.ACCENT_BLUE}, stop:1 {t.ACCENT_PURPLE}); border-radius: 4px; }}"
        )
        ctx_lay.addWidget(self._ctx_bar)

        self._ctx_label = QLabel("0 / 128,000 tokens")
        self._ctx_label.setObjectName("dimLabel")
        ctx_lay.addWidget(self._ctx_label)
        layout.addWidget(ctx_group)

        # --- Agent Activity ---
        agent_group = QGroupBox("Agent Activity")
        agent_lay = QVBoxLayout(agent_group)

        self._agent_list = QTextEdit()
        self._agent_list.setReadOnly(True)
        self._agent_list.setMaximumHeight(140)
        self._agent_list.setStyleSheet(
            f"background: {t.BG_PRIMARY}; color: {t.TEXT_PRIMARY}; "
            f"font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 11px; "
            f"border: 1px solid {t.BORDER}; border-radius: 6px; padding: 6px;"
        )
        self._agent_list.setPlainText("No agent activity yet.")
        agent_lay.addWidget(self._agent_list)
        layout.addWidget(agent_group)

        # --- Model Info ---
        model_group = QGroupBox("Model")
        model_lay = QVBoxLayout(model_group)

        self._model_label = QLabel("Model: --")
        self._model_label.setObjectName("dimLabel")
        model_lay.addWidget(self._model_label)

        self._provider_label = QLabel("Provider: --")
        self._provider_label.setObjectName("dimLabel")
        model_lay.addWidget(self._provider_label)

        self._latency_label = QLabel("Latency: --")
        self._latency_label.setObjectName("dimLabel")
        model_lay.addWidget(self._latency_label)

        layout.addWidget(model_group)

        # --- Metrics ---
        metrics_group = QGroupBox("Metrics")
        metrics_lay = QVBoxLayout(metrics_group)

        self._metrics_text = QLabel("No metrics yet.")
        self._metrics_text.setObjectName("dimLabel")
        self._metrics_text.setWordWrap(True)
        metrics_lay.addWidget(self._metrics_text)
        layout.addWidget(metrics_group)

        layout.addStretch()

    # --- public API ----------------------------------------------------------

    def update_context_gauge(self, used: int, maximum: int) -> None:
        """Update the context window progress bar."""
        if not _QT_AVAILABLE:
            return
        self._ctx_bar.setRange(0, maximum)
        self._ctx_bar.setValue(used)
        self._ctx_label.setText(f"{used:,} / {maximum:,} tokens")

    def update_agent_activity(self, entries: List[str]) -> None:
        """Replace the agent activity list."""
        if not _QT_AVAILABLE:
            return
        if entries:
            self._agent_list.setPlainText("\n".join(entries))
        else:
            self._agent_list.setPlainText("No agent activity yet.")

    def update_model_info(self, model: str = "--", provider: str = "--", latency: str = "--") -> None:
        if not _QT_AVAILABLE:
            return
        self._model_label.setText(f"Model: {model}")
        self._provider_label.setText(f"Provider: {provider}")
        self._latency_label.setText(f"Latency: {latency}")

    def update_metrics(self, metrics: Dict[str, Any]) -> None:
        """Display arbitrary key-value metrics."""
        if not _QT_AVAILABLE:
            return
        lines = [f"{k}: {v}" for k, v in metrics.items()]
        self._metrics_text.setText("\n".join(lines) if lines else "No metrics yet.")


# ===================================================================
# ExpandingTextEdit -- auto-growing prompt input
# ===================================================================

class ExpandingTextEdit(QTextEdit if _QT_AVAILABLE else object):
    """Multi-line text input that grows vertically.

    Enter sends, Shift+Enter inserts a newline.
    """

    submit_pressed = pyqtSignal() if _QT_AVAILABLE else None
    files_dropped = pyqtSignal(list) if _QT_AVAILABLE else None

    _MIN_LINES = 1
    _MAX_LINES = 6
    _MAX_HISTORY = 100

    def __init__(self, parent: Any = None) -> None:
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(True)
        self.setAcceptDrops(True)
        self.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth
            if hasattr(QTextEdit, "LineWrapMode")
            else QTextEdit.WidgetWidth
        )
        self.setWordWrapMode(4)  # WrapAtWordBoundaryOrAnywhere
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if hasattr(Qt, "ScrollBarPolicy")
            else Qt.ScrollBarAsNeeded
        )
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if hasattr(Qt, "ScrollBarPolicy")
            else Qt.ScrollBarAlwaysOff
        )
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding if hasattr(QSizePolicy, "Policy") else QSizePolicy.Expanding,
            QSizePolicy.Policy.Minimum if hasattr(QSizePolicy, "Policy") else QSizePolicy.Minimum,
        )
        self._adjust_height()

        self._history: List[str] = []
        self._history_idx: int = -1
        self._draft: str = ""
        self._last_esc_time: float = 0.0

    # --- height management ---------------------------------------------------

    def _line_height(self) -> int:
        return self.fontMetrics().lineSpacing()

    def _adjust_height(self) -> None:
        self.document().setTextWidth(self.viewport().width())
        doc_height = int(self.document().size().height())
        margins = self.contentsMargins()
        pad = margins.top() + margins.bottom() + 2 * self.frameWidth()
        line_h = self._line_height()
        min_h = line_h * self._MIN_LINES + pad + 10
        max_h = line_h * self._MAX_LINES + pad + 10
        new_h = max(min_h, min(doc_height + pad, max_h))
        self.setMinimumHeight(min_h)
        self.setMaximumHeight(max_h)
        if self.height() != new_h:
            self.resize(self.width(), new_h)

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._adjust_height()

    # --- history -------------------------------------------------------------

    def push_history(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if self._history and self._history[-1] == text:
            return
        self._history.append(text)
        if len(self._history) > self._MAX_HISTORY:
            self._history = self._history[-self._MAX_HISTORY:]
        self._history_idx = -1
        self._draft = ""

    def _cursor_on_first_line(self) -> bool:
        cursor = self.textCursor()
        cursor.movePosition(
            cursor.MoveOperation.StartOfBlock if hasattr(cursor, "MoveOperation") else cursor.StartOfBlock
        )
        return cursor.atStart()

    def _cursor_on_last_line(self) -> bool:
        cursor = self.textCursor()
        cursor.movePosition(
            cursor.MoveOperation.EndOfBlock if hasattr(cursor, "MoveOperation") else cursor.EndOfBlock
        )
        return cursor.atEnd()

    def _move_cursor_to_end(self) -> None:
        cursor = self.textCursor()
        cursor.movePosition(
            cursor.MoveOperation.End if hasattr(cursor, "MoveOperation") else cursor.End
        )
        self.setTextCursor(cursor)

    # --- keyboard handling ---------------------------------------------------

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()

        _shift = Qt.KeyboardModifier.ShiftModifier if hasattr(Qt, "KeyboardModifier") else Qt.ShiftModifier
        _ctrl = Qt.KeyboardModifier.ControlModifier if hasattr(Qt, "KeyboardModifier") else Qt.ControlModifier
        _no = Qt.KeyboardModifier.NoModifier if hasattr(Qt, "KeyboardModifier") else Qt.NoModifier

        _Key_Return = Qt.Key.Key_Return if hasattr(Qt, "Key") else Qt.Key_Return
        _Key_Enter = Qt.Key.Key_Enter if hasattr(Qt, "Key") else Qt.Key_Enter
        _Key_Escape = Qt.Key.Key_Escape if hasattr(Qt, "Key") else Qt.Key_Escape
        _Key_Up = Qt.Key.Key_Up if hasattr(Qt, "Key") else Qt.Key_Up
        _Key_Down = Qt.Key.Key_Down if hasattr(Qt, "Key") else Qt.Key_Down

        # Enter / Shift+Enter
        if key in (_Key_Return, _Key_Enter):
            if mods & _shift:
                super().keyPressEvent(event)
            else:
                if self.submit_pressed is not None:
                    self.submit_pressed.emit()
            return

        # Double-Esc to clear
        if key == _Key_Escape:
            now = time.monotonic()
            if now - self._last_esc_time < 0.4:
                self.clear()
                self._last_esc_time = 0.0
                self._history_idx = -1
            else:
                self._last_esc_time = now
            return

        # History Up
        if key == _Key_Up and not (mods & _shift) and self._cursor_on_first_line():
            if not self._history:
                return
            if self._history_idx == -1:
                self._draft = self.toPlainText()
                self._history_idx = len(self._history) - 1
            elif self._history_idx > 0:
                self._history_idx -= 1
            else:
                return
            self.setPlainText(self._history[self._history_idx])
            self._move_cursor_to_end()
            return

        # History Down
        if key == _Key_Down and not (mods & _shift) and self._cursor_on_last_line():
            if self._history_idx == -1:
                return
            if self._history_idx < len(self._history) - 1:
                self._history_idx += 1
                self.setPlainText(self._history[self._history_idx])
            else:
                self._history_idx = -1
                self.setPlainText(self._draft)
            self._move_cursor_to_end()
            return

        super().keyPressEvent(event)

    # --- clipboard -----------------------------------------------------------

    def insertFromMimeData(self, source: Any) -> None:  # noqa: N802
        if source.hasText():
            self.textCursor().insertText(source.text())
        else:
            super().insertFromMimeData(source)

    def text(self) -> str:
        return self.toPlainText()

    # --- drag-and-drop -------------------------------------------------------

    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
            if paths and self.files_dropped is not None:
                self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


# ===================================================================
# InputBar -- text input with attachment, mic, and speaker buttons
# ===================================================================

class InputBar(QWidget if _QT_AVAILABLE else object):
    """Styled input bar with text field and action buttons."""

    if _QT_AVAILABLE:
        message_submitted = pyqtSignal(str)
        voice_requested = pyqtSignal()
        speaker_toggled = pyqtSignal(bool)
        attach_requested = pyqtSignal()

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self._speaker_on = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # Attach button
        self._attach_btn = QPushButton("\U0001F4CE")
        self._attach_btn.setObjectName("attachBtn")
        self._attach_btn.setToolTip("Attach files")
        self._attach_btn.setFixedWidth(42)
        self._attach_btn.clicked.connect(lambda: self.attach_requested.emit())
        layout.addWidget(self._attach_btn)

        # Text input
        self._input = ExpandingTextEdit()
        self._input.setObjectName("promptInput")
        self._input.setPlaceholderText("Type a message... (Enter to send, Shift+Enter for newline)")
        self._input.submit_pressed.connect(self._on_submit)
        layout.addWidget(self._input, stretch=1)

        # Send button
        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedWidth(70)
        self._send_btn.clicked.connect(self._on_submit)
        layout.addWidget(self._send_btn)

        # Mic button
        self._mic_btn = QPushButton("\U0001F3A4")
        self._mic_btn.setObjectName("micBtn")
        self._mic_btn.setToolTip("Voice input")
        self._mic_btn.setFixedWidth(42)
        self._mic_btn.clicked.connect(lambda: self.voice_requested.emit())
        layout.addWidget(self._mic_btn)

        # Speaker button
        self._speaker_btn = QPushButton("\U0001F50A")
        self._speaker_btn.setObjectName("speakerBtn")
        self._speaker_btn.setToolTip("Toggle speaker")
        self._speaker_btn.setFixedWidth(42)
        self._speaker_btn.clicked.connect(self._toggle_speaker)
        layout.addWidget(self._speaker_btn)

    def _on_submit(self) -> None:
        text = self._input.toPlainText().strip()
        if text:
            self._input.push_history(text)
            self._input.clear()
            self.message_submitted.emit(text)

    def _toggle_speaker(self) -> None:
        self._speaker_on = not self._speaker_on
        self._speaker_btn.setText("\U0001F50A" if self._speaker_on else "\U0001F507")
        self.speaker_toggled.emit(self._speaker_on)

    def set_enabled(self, enabled: bool) -> None:
        if not _QT_AVAILABLE:
            return
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)
        self._attach_btn.setEnabled(enabled)
        if enabled:
            self._input.setPlaceholderText(
                "Type a message... (Enter to send, Shift+Enter for newline)"
            )
        else:
            self._input.setPlaceholderText("Kait is thinking...")

    def set_focus(self) -> None:
        if _QT_AVAILABLE:
            self._input.setFocus()

    @property
    def input_field(self) -> Any:
        return self._input


# ===================================================================
# FooterStatusBar -- service health + mood + evolution badge
# ===================================================================

class FooterStatusBar(QWidget if _QT_AVAILABLE else object):
    """Footer bar showing service connection dots, mood, and evolution stage."""

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        t = Theme
        self.setStyleSheet(
            f"background: {t.BG_SECONDARY}; border-top: 1px solid {t.BORDER};"
        )
        self.setFixedHeight(30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 2, 12, 2)
        layout.setSpacing(16)

        self._service_labels: Dict[str, QLabel] = {}

        # Default services
        for svc in ("Ollama", "Claude", "TTS"):
            dot_lbl = QLabel(f"\u25CF {svc}: --")
            dot_lbl.setStyleSheet(
                f"color: {t.TEXT_DIM}; font-size: 11px; background: transparent; border: none;"
            )
            layout.addWidget(dot_lbl)
            self._service_labels[svc.lower()] = dot_lbl

        layout.addStretch()

        # Mood indicator
        self._mood_label = QLabel("Mood: calm")
        self._mood_label.setStyleSheet(
            f"color: {t.TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;"
        )
        layout.addWidget(self._mood_label)

        # Evolution badge
        self._evo_label = QLabel("Stage 1")
        self._evo_label.setStyleSheet(
            f"color: {t.ACCENT_BLUE}; font-size: 11px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._evo_label)

    def update_service(self, name: str, connected: bool) -> None:
        """Update a service health indicator."""
        if not _QT_AVAILABLE:
            return
        t = Theme
        key = name.lower()
        if key not in self._service_labels:
            # Dynamically add new service
            lbl = QLabel(f"\u25CF {name}: --")
            lbl.setStyleSheet(
                f"color: {t.TEXT_DIM}; font-size: 11px; background: transparent; border: none;"
            )
            self.layout().insertWidget(len(self._service_labels), lbl)
            self._service_labels[key] = lbl

        lbl = self._service_labels[key]
        if connected:
            color = t.ACCENT_GREEN
            status = "connected"
        else:
            color = t.ACCENT_RED
            status = "offline"
        lbl.setText(f"\u25CF {name}: {status}")
        lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; background: transparent; border: none;"
        )

    def update_mood(self, mood_text: str) -> None:
        if _QT_AVAILABLE:
            self._mood_label.setText(f"Mood: {mood_text}")

    def update_evolution(self, stage_text: str) -> None:
        if _QT_AVAILABLE:
            self._evo_label.setText(stage_text)


# ===================================================================
# HeaderStatusBar -- top bar with title, token count, GPU indicator
# ===================================================================

class HeaderStatusBar(QWidget if _QT_AVAILABLE else object):
    """Top status bar: title left, token counter and GPU indicator right."""

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        t = Theme
        self.setStyleSheet(
            f"background: {t.BG_SECONDARY}; border-bottom: 1px solid {t.BORDER};"
        )
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 14, 4)
        layout.setSpacing(12)

        # Title
        title = QLabel("Kait Intel")
        title.setStyleSheet(
            f"color: {t.ACCENT_BLUE}; font-size: 15px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(title)

        layout.addStretch()

        # Token counter
        self._token_label = QLabel("Tokens: 0/128k")
        self._token_label.setStyleSheet(
            f"color: {t.TEXT_SECONDARY}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._token_label)

        # GPU indicator
        self._gpu_label = QLabel("GPU \u25AA")
        self._gpu_label.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._gpu_label)

    def update_tokens(self, used: int, maximum: int) -> None:
        if not _QT_AVAILABLE:
            return
        if maximum >= 1000:
            max_str = f"{maximum / 1000:.0f}k"
        else:
            max_str = str(maximum)
        if used >= 1000:
            used_str = f"{used / 1000:.1f}k"
        else:
            used_str = str(used)
        self._token_label.setText(f"Tokens: {used_str}/{max_str}")

    def update_gpu(self, active: bool) -> None:
        if not _QT_AVAILABLE:
            return
        t = Theme
        if active:
            self._gpu_label.setText("GPU \u25AA")
            self._gpu_label.setStyleSheet(
                f"color: {t.ACCENT_GREEN}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
        else:
            self._gpu_label.setText("GPU \u25AA")
            self._gpu_label.setStyleSheet(
                f"color: {t.TEXT_DIM}; font-size: 11px; "
                f"background: transparent; border: none;"
            )


# ===================================================================
# AvatarCustomizePanel -- stub for backward compatibility
# ===================================================================

class AvatarCustomizePanel(QWidget if _QT_AVAILABLE else object):
    """Stub retained for backward compatibility.  Avatar system has been removed."""

    if _QT_AVAILABLE:
        settings_changed = pyqtSignal(dict)

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self.setVisible(False)

    def _emit_settings(self, _: Any = None) -> None:
        if _QT_AVAILABLE:
            self.settings_changed.emit(self.get_settings())

    def get_settings(self) -> Dict[str, Any]:
        return {
            "max_particles": 120,
            "core_intensity": 0.5,
            "vein_bias": 0,
            "mood_override": None,
        }


# ===================================================================
# OnboardingWizard -- first-run setup dialog
# ===================================================================

class OnboardingWizard(QDialog if _QT_AVAILABLE else object):
    """First-run onboarding wizard for model selection and preferences."""

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self.setWindowTitle("Welcome to Kait Intel")
        self.setMinimumSize(480, 400)
        self.setStyleSheet(DARK_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        header = QLabel("Welcome to Kait Intel")
        header.setObjectName("headerLabel")
        header.setAlignment(
            Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter
        )
        layout.addWidget(header)

        subtitle = QLabel("Your AI intelligence sidekick.")
        subtitle.setObjectName("dimLabel")
        subtitle.setAlignment(
            Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter
        )
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Model selection
        model_group = QGroupBox("LLM Model")
        model_lay = QVBoxLayout(model_group)
        model_lay.addWidget(QLabel("Select your preferred model:"))
        self._model_combo = QComboBox()
        self._model_combo.addItems([
            "Auto-detect (recommended)",
            "llama3.1:70b",
            "llama3.1:8b",
            "llama3:latest",
            "mistral",
        ])
        model_lay.addWidget(self._model_combo)
        layout.addWidget(model_group)

        # Preferences
        pref_group = QGroupBox("Preferences")
        pref_lay = QVBoxLayout(pref_group)

        self._voice_check = QCheckBox("Enable voice input (requires microphone)")
        pref_lay.addWidget(self._voice_check)

        self._sound_check = QCheckBox("Enable sound effects")
        self._sound_check.setChecked(True)
        pref_lay.addWidget(self._sound_check)

        layout.addWidget(pref_group)
        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        start_btn = QPushButton("Start")
        start_btn.setObjectName("sendBtn")
        start_btn.clicked.connect(self.accept)
        btn_row.addWidget(start_btn)
        layout.addLayout(btn_row)

        # Results
        self.selected_model: str = "auto"
        self.voice_enabled: bool = False
        self.sound_enabled: bool = True
        self.avatar_enabled: bool = False

    def accept(self) -> None:
        if not _QT_AVAILABLE:
            return
        idx = self._model_combo.currentIndex()
        if idx == 0:
            self.selected_model = "auto"
        else:
            self.selected_model = self._model_combo.currentText()
        self.voice_enabled = self._voice_check.isChecked()
        self.sound_enabled = self._sound_check.isChecked()
        super().accept()


# ===================================================================
# LLMWorker -- background thread for LLM generation
# ===================================================================

class LLMWorker(QThread if _QT_AVAILABLE else object):
    """Runs LLM generation in a background thread."""

    if _QT_AVAILABLE:
        token_received = pyqtSignal(str)
        generation_done = pyqtSignal(str)
        generation_error = pyqtSignal(str)

    def __init__(self, generate_fn: Callable, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self._generate_fn = generate_fn
        self._user_input: str = ""
        self._context: Dict[str, Any] = {}

    def setup(self, user_input: str, context: Dict[str, Any]) -> None:
        self._user_input = user_input
        self._context = context

    def run(self) -> None:
        if not _QT_AVAILABLE:
            return
        try:
            response = self._generate_fn(self._user_input, self._context)
            self.generation_done.emit(response)
        except Exception as exc:
            self.generation_error.emit(str(exc))


# ===================================================================
# DashboardPanel -- legacy compatibility stub
# ===================================================================

class DashboardPanel(QWidget if _QT_AVAILABLE else object):
    """Legacy dashboard stub.  Functionality moved to ProcessingMonitorPanel."""

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        lbl = QLabel("Dashboard data is now in the Monitor tab.")
        lbl.setObjectName("dimLabel")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        layout.addStretch()

    def update_evolution(self, *args: Any, **kwargs: Any) -> None:
        pass

    def update_resonance(self, *args: Any, **kwargs: Any) -> None:
        pass

    def update_bank_stats(self, *args: Any, **kwargs: Any) -> None:
        pass

    def update_system(self, *args: Any, **kwargs: Any) -> None:
        pass

    def update_services(self, *args: Any, **kwargs: Any) -> None:
        pass


# ===================================================================
# KaitMainWindow -- the main application window
# ===================================================================

class KaitMainWindow(QMainWindow if _QT_AVAILABLE else object):
    """Main window for the Kait Intel GUI.

    Layout::

        +---------------------------------------------------------+
        | Header: [Kait Intel]  [Tokens]  [GPU]                   |
        +----------------------+----------------------------------+
        |                      | [Chat] [Observatory] [Monitor]   |
        |   Chat Messages      |   Tab content                    |
        |   (scrollable)       |                                  |
        +----------------------+----------------------------------+
        | Input Bar: [Attach] [Text...] [Send] [Mic] [Speaker]   |
        +---------------------------------------------------------+
        | Footer: service dots | mood | evolution                  |
        +---------------------------------------------------------+
    """

    if _QT_AVAILABLE:
        user_message_sent = pyqtSignal(str)
        voice_requested = pyqtSignal()
        theme_changed = pyqtSignal(str)
        attachments_ready = pyqtSignal(list)

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self.setWindowTitle("Kait Intel")
        self.setMinimumSize(900, 600)
        self.resize(1400, 850)

        self._current_theme_name = "dark"
        self._current_theme = Theme
        self.setStyleSheet(DARK_STYLESHEET)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Header status bar ---
        self._header_bar = HeaderStatusBar()
        root_layout.addWidget(self._header_bar)

        # --- Main content area (splitter) ---
        splitter = QSplitter(
            Qt.Orientation.Horizontal if hasattr(Qt, "Orientation") else Qt.Horizontal
        )
        splitter.setHandleWidth(2)

        # LEFT: Chat panel
        left_container = QWidget()
        left_container.setMinimumWidth(320)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.chat_panel = ChatPanel()
        left_layout.addWidget(self.chat_panel, stretch=1)

        splitter.addWidget(left_container)

        # RIGHT: Tab widget (Chat duplicate / Observatory / Monitor)
        self._tab_widget = QTabWidget()

        # Chat tab (duplicate -- shows same messages in rich text for reference)
        self._chat_tab = QWidget()
        chat_tab_layout = QVBoxLayout(self._chat_tab)
        chat_tab_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_reference = QTextEdit()
        self._chat_reference.setReadOnly(True)
        self._chat_reference.setStyleSheet(
            f"background: {Theme.BG_PRIMARY}; color: {Theme.TEXT_PRIMARY}; "
            f"border: none; font-size: 13px;"
        )
        self._chat_reference.setPlainText("Chat history will appear here as a reference view.")
        chat_tab_layout.addWidget(self._chat_reference)
        self._tab_widget.addTab(self._chat_tab, "Chat")

        # Observatory tab
        self._observatory = ObservatoryPanel()
        obs_scroll = QScrollArea()
        obs_scroll.setWidget(self._observatory)
        obs_scroll.setWidgetResizable(True)
        obs_scroll.setFrameStyle(QFrame.Shape.NoFrame if hasattr(QFrame, "Shape") else QFrame.NoFrame)
        self._tab_widget.addTab(obs_scroll, "Observatory")

        # Monitor tab
        self._monitor = ProcessingMonitorPanel()
        mon_scroll = QScrollArea()
        mon_scroll.setWidget(self._monitor)
        mon_scroll.setWidgetResizable(True)
        mon_scroll.setFrameStyle(QFrame.Shape.NoFrame if hasattr(QFrame, "Shape") else QFrame.NoFrame)
        self._tab_widget.addTab(mon_scroll, "Monitor")

        self._tab_widget.setMinimumWidth(300)
        splitter.addWidget(self._tab_widget)

        # Splitter proportions: chat=60%, tabs=40%
        splitter.setSizes([600, 400])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root_layout.addWidget(splitter, stretch=1)

        # --- Input bar ---
        self._input_bar = InputBar()
        self._input_bar.message_submitted.connect(self._on_send)
        self._input_bar.voice_requested.connect(self._on_voice)
        self._input_bar.attach_requested.connect(self._on_attach)
        root_layout.addWidget(self._input_bar)

        # --- Footer status bar ---
        self._footer_bar = FooterStatusBar()
        root_layout.addWidget(self._footer_bar)

        # --- Legacy compatibility attributes ---
        self.dashboard = DashboardPanel()
        self.avatar_widget = QWidget() if _QT_AVAILABLE else None
        self.avatar_customize = AvatarCustomizePanel()
        self._file_processor: Any = None
        self._pending_attachments: List[Any] = []
        self._generating: bool = False

        # Keyboard shortcuts
        self._setup_shortcuts()

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        if not _QT_AVAILABLE:
            return

        voice_action = QAction("Voice Input", self)
        voice_action.setShortcut(QKeySequence("Ctrl+Shift+V"))
        voice_action.triggered.connect(self._on_voice)
        self.addAction(voice_action)

        clear_action = QAction("Clear Chat", self)
        clear_action.setShortcut(QKeySequence("Ctrl+L"))
        clear_action.triggered.connect(self.chat_panel.clear_chat)
        self.addAction(clear_action)

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

        focus_action = QAction("Focus Input", self)
        focus_action.setShortcut(QKeySequence("Escape"))
        focus_action.triggered.connect(lambda: self._input_bar.set_focus())
        self.addAction(focus_action)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_send(self, text: str = "") -> None:
        if not _QT_AVAILABLE:
            return
        if not text:
            return
        if self._generating:
            return
        self.user_message_sent.emit(text)

    def _on_voice(self) -> None:
        if _QT_AVAILABLE:
            self.voice_requested.emit()

    def _on_attach(self) -> None:
        if not _QT_AVAILABLE or self._generating:
            return
        filter_str = "All files (*)"
        from pathlib import Path
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach Files", str(Path.home()), filter_str,
        )
        if paths:
            # For now, emit files as attachments ready
            self.attachments_ready.emit(paths)

    # ------------------------------------------------------------------
    # Public API for controller
    # ------------------------------------------------------------------

    def display_message(self, role: str, text: str, sentiment: str = "neutral") -> None:
        """Add a message to the chat panel."""
        self.chat_panel.add_message(role, text, sentiment)

    def display_streaming_token(self, token: str) -> None:
        """Append a streaming token to the current assistant message."""
        self.chat_panel.append_token(token)

    def finish_streaming(self) -> str:
        """Finalise streaming and return the full text."""
        return self.chat_panel.finish_streaming()

    def update_status(self, service_name: str, is_connected: bool) -> None:
        """Update a service health indicator in the footer."""
        self._footer_bar.update_service(service_name, is_connected)

    def update_mood(self, mood_text: str) -> None:
        """Update the mood indicator in the footer."""
        self._footer_bar.update_mood(mood_text)

    def update_metrics(self, metrics_dict: Dict[str, Any]) -> None:
        """Update the processing monitor metrics."""
        if not _QT_AVAILABLE:
            return
        self._monitor.update_metrics(metrics_dict)
        # Also update context gauge if tokens info is present
        if "tokens_used" in metrics_dict and "tokens_max" in metrics_dict:
            used = int(metrics_dict["tokens_used"])
            maximum = int(metrics_dict["tokens_max"])
            self._monitor.update_context_gauge(used, maximum)
            self._header_bar.update_tokens(used, maximum)

    # --- Legacy API compatibility ---

    def set_generating(self, active: bool) -> None:
        """Toggle generating state (disables input while LLM runs)."""
        if not _QT_AVAILABLE:
            return
        self._generating = active
        self._input_bar.set_enabled(not active)

    def update_mood_display(self, mood: str, kait: float) -> None:
        if _QT_AVAILABLE:
            self._footer_bar.update_mood(mood)

    def show_status_message(self, msg: str, timeout_ms: int = 5000) -> None:
        """Show a transient message (uses footer mood label as fallback)."""
        if _QT_AVAILABLE:
            self._footer_bar.update_mood(msg)

    def add_system_message(self, text: str) -> None:
        self.chat_panel.add_message(ChatMessage("system", text))

    def add_user_message(self, text: str, attachments: Optional[List[Dict]] = None) -> None:
        self.chat_panel.add_message(ChatMessage("user", text, attachments=attachments))

    def add_ai_message(self, text: str, sentiment: str = "neutral") -> None:
        self.chat_panel.add_message(ChatMessage("assistant", text, sentiment))

    def update_model_indicator(self, model: str, provider: str = "ollama") -> None:
        """Update model info in the monitor panel."""
        if not _QT_AVAILABLE:
            return
        self._monitor.update_model_info(model=model, provider=provider)
        self.update_status(provider.capitalize(), True)

    def set_file_processor(self, processor: Any) -> None:
        self._file_processor = processor

    def get_pending_attachments(self) -> List[Any]:
        results = list(self._pending_attachments)
        self._pending_attachments.clear()
        return results

    def start_avatar_animation(self) -> None:
        """No-op -- avatar system removed."""

    def stop_avatar_animation(self) -> None:
        """No-op -- avatar system removed."""

    def apply_theme(self, theme_name: str) -> None:
        """Apply a named theme (dark mode only in practice)."""
        if not _QT_AVAILABLE:
            return
        theme_cls = THEMES.get(theme_name)
        if theme_cls is None:
            return
        self._current_theme_name = theme_name
        self._current_theme = theme_cls
        self.setStyleSheet(build_stylesheet(theme_cls))
        self.chat_panel.set_theme(theme_cls)
        self.theme_changed.emit(theme_name)

    @property
    def observatory(self) -> "ObservatoryPanel":
        return self._observatory

    @property
    def monitor(self) -> "ProcessingMonitorPanel":
        return self._monitor

    @property
    def header_bar(self) -> "HeaderStatusBar":
        return self._header_bar

    @property
    def footer_bar(self) -> "FooterStatusBar":
        return self._footer_bar
