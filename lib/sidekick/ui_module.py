"""Kait -- Modern Control UI for the Kait Open Source Sidekick.

Ground-up rewrite with a professional 3-panel + tabs layout:

    +---------------------------------------------------------+
    | [Kait]         [Tokens: 1.2k/128k] [GPU ...]     | <- Status Bar
    +----------------------+----------------------------------+
    |                      | [Dashboard] [History]            | <- Tab Bar
    |   Chat Messages      |                                  |
    |   (scrollable,       |  Pipeline / Metrics / Activity   |
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

import math
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
        QGridLayout, QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel,
        QProgressBar, QGroupBox, QScrollArea, QFrame, QDialog,
        QComboBox, QCheckBox, QStackedWidget, QSizePolicy,
        QToolBar, QStatusBar, QMessageBox, QTabWidget, QFileDialog,
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QSize, pyqtSignal, pyqtSlot, QThread,
        QPropertyAnimation, QEasingCurve, QObject, QPointF, QRectF,
    )
    from PyQt6.QtGui import (
        QImage, QPixmap, QFont, QColor, QPalette, QIcon,
        QTextCursor, QKeySequence, QPainter, QBrush, QPen,
        QLinearGradient, QRadialGradient, QAction, QTextOption, QPainterPath,
    )
    _QT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtWidgets import (  # type: ignore[no-redef]
            QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QGridLayout, QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel,
            QProgressBar, QGroupBox, QScrollArea, QFrame, QDialog,
            QComboBox, QCheckBox, QStackedWidget, QSizePolicy,
            QAction, QToolBar, QStatusBar, QMessageBox, QTabWidget, QFileDialog,
        )
        from PyQt5.QtCore import (  # type: ignore[no-redef]
            Qt, QTimer, QSize, pyqtSignal, pyqtSlot, QThread,
            QPropertyAnimation, QEasingCurve, QObject, QPointF, QRectF,
        )
        from PyQt5.QtGui import (  # type: ignore[no-redef]
            QImage, QPixmap, QFont, QColor, QPalette, QIcon,
            QTextCursor, QKeySequence, QPainter, QBrush, QPen,
            QLinearGradient, QRadialGradient, QPainterPath,
        )
        _QT_AVAILABLE = True
    except ImportError:
        pass


# ===================================================================
# AudioCueManager -- stub (pygame removed)
# ===================================================================

# ---------------------------------------------------------------------------
# Vault viewer import (Kait Brain + BLERBZ OS Map tabbed views)
# ---------------------------------------------------------------------------
try:
    from .vault_viewer import (
        create_kait_brain_panel,
        create_github_mindmap_panel,
        VaultViewerPanel,
        VaultGraphSection,
    )
    _VAULT_VIEWER_AVAILABLE = True
except ImportError:
    _VAULT_VIEWER_AVAILABLE = False


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
    """Apple-style monochrome dark palette following Apple HIG conventions."""

    # Core backgrounds
    BG_PRIMARY = "#000000"       # Pure black
    BG_SECONDARY = "#0A0A0A"    # Panels
    BG_TERTIARY = "#141414"     # Elevated surfaces
    BG_INPUT = "#0F0F0F"        # Input fields

    # Text
    TEXT_PRIMARY = "#FFFFFF"     # Bright white
    TEXT_SECONDARY = "#8E8E93"  # Apple system gray
    TEXT_DIM = "#48484A"        # Apple system gray 3

    # Accents
    ACCENT_BLUE = "#FFFFFF"      # Primary accent -> white
    ACCENT_PURPLE = "#C7C7CC"    # Secondary -> light gray
    ACCENT_GOLD = "#FFD60A"      # Apple system yellow
    ACCENT_KAIT = "#C7C7CC"     # alias for legacy code paths
    ACCENT_GREEN = "#30D158"     # Apple system green
    ACCENT_RED = "#FF453A"       # Apple system red

    # Chat bubbles
    BUBBLE_USER = "#1C1C1E"     # Apple gray 6
    BUBBLE_AI = "#1A1A1E"       # Faint dark grey

    # Borders
    BORDER = "#2C2C2E"          # Apple gray 5

    # Scrollbar
    SCROLLBAR_BG = "#000000"
    SCROLLBAR_HANDLE = "#3A3A3C"  # Apple gray 4

    # Sentiment
    SENTIMENT_POSITIVE = "#30D158"
    SENTIMENT_NEGATIVE = "#FF453A"
    SENTIMENT_NEUTRAL = "#8E8E93"

    # Attachment chips (legacy compat)
    ATTACHMENT_BG = "#1C1C1E"
    ATTACHMENT_BORDER = "#2C2C2E"
    ATTACHMENT_ICON_COLOR = "#FFFFFF"
    DROP_OVERLAY = "rgba(255, 255, 255, 0.06)"


class Glass:
    """Frosted-glass rgba constants for Apple-style translucency."""

    BTN_BG = "rgba(255, 255, 255, 0.06)"
    BTN_BG_HOVER = "rgba(255, 255, 255, 0.12)"
    BTN_BG_PRESSED = "rgba(255, 255, 255, 0.04)"
    BTN_BORDER = "rgba(255, 255, 255, 0.10)"
    PANEL_BG = "rgba(10, 10, 10, 0.85)"
    INPUT_BG = "rgba(255, 255, 255, 0.04)"
    INPUT_BORDER = "rgba(255, 255, 255, 0.08)"
    INPUT_FOCUS = "rgba(255, 255, 255, 0.18)"


# ---------------------------------------------------------------------------
# Legacy theme aliases -- kept for backward-compatible imports / tests
# ---------------------------------------------------------------------------

class HighContrastTheme:
    """High-contrast monochrome variant (legacy compat)."""

    BG_PRIMARY = "#000000"
    BG_SECONDARY = "#080808"
    BG_TERTIARY = "#111111"
    BG_INPUT = "#0C0C0C"
    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#A1A1A6"
    TEXT_DIM = "#636366"
    ACCENT_BLUE = "#FFFFFF"
    ACCENT_GOLD = "#FFD60A"
    ACCENT_KAIT = "#D1D1D6"
    ACCENT_GREEN = "#30D158"
    ACCENT_RED = "#FF453A"
    ACCENT_PURPLE = "#D1D1D6"
    BORDER = "#38383A"
    BUBBLE_USER = "#1C1C1E"
    BUBBLE_AI = "#1A1A1E"
    SCROLLBAR_BG = "#000000"
    SCROLLBAR_HANDLE = "#48484A"
    SENTIMENT_POSITIVE = "#30D158"
    SENTIMENT_NEGATIVE = "#FF453A"
    SENTIMENT_NEUTRAL = "#A1A1A6"
    ATTACHMENT_BG = "#1C1C1E"
    ATTACHMENT_BORDER = "#38383A"
    ATTACHMENT_ICON_COLOR = "#FFFFFF"
    DROP_OVERLAY = "rgba(255, 255, 255, 0.08)"


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
    """Build an Apple-style monochrome Qt stylesheet from a theme class."""
    g = Glass
    return f"""
/* ---- Global ---- */
QMainWindow, QWidget {{
    background-color: {theme.BG_PRIMARY};
    color: {theme.TEXT_PRIMARY};
    font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', -apple-system, sans-serif;
    font-size: 13px;
}}

/* ---- Splitter ---- */
QSplitter::handle {{
    background: {theme.BORDER};
    width: 1px;
}}
QSplitter::handle:hover {{
    background: rgba(255, 255, 255, 0.30);
    width: 2px;
}}

/* ---- Line Edit ---- */
QLineEdit {{
    background-color: {g.INPUT_BG};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {g.INPUT_BORDER};
    border-radius: 18px;
    padding: 10px 16px;
    font-size: 14px;
    selection-background-color: rgba(255, 255, 255, 0.20);
}}
QLineEdit:focus {{
    border: 1px solid rgba(48, 209, 88, 0.35);
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
    background-color: {g.INPUT_BG};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {g.INPUT_BORDER};
    border-radius: 18px;
    padding: 10px 16px;
    font-size: 14px;
    selection-background-color: rgba(48, 209, 88, 0.25);
}}
QTextEdit#promptInput:focus {{
    border: 1px solid rgba(48, 209, 88, 0.35);
}}

/* ---- Buttons (glass pills) ---- */
QPushButton {{
    background-color: {g.BTN_BG};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {g.BTN_BORDER};
    border-radius: 18px;
    padding: 8px 18px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {g.BTN_BG_HOVER};
    color: {theme.TEXT_PRIMARY};
    border-color: rgba(255, 255, 255, 0.16);
}}
QPushButton:pressed {{
    background-color: {g.BTN_BG_PRESSED};
}}
QPushButton#sendBtn {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FFFFFF, stop:0.5 #F0F0F0, stop:1 #E0E0E0);
    color: #000000;
    font-weight: 700;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 18px;
    padding: 10px 22px;
    font-size: 13px;
    letter-spacing: 0.3px;
}}
QPushButton#sendBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FFFFFF, stop:0.5 #F8F8F8, stop:1 #F0F0F0);
    border: 1px solid rgba(0, 0, 0, 0.05);
}}
QPushButton#sendBtn:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #D8D8D8, stop:1 #C8C8C8);
    border: 1px solid rgba(0, 0, 0, 0.12);
}}
QPushButton#attachBtn {{
    background-color: {g.BTN_BG};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {g.BTN_BORDER};
    border-radius: 18px;
    padding: 8px 10px;
    font-size: 16px;
    font-weight: bold;
}}
QPushButton#attachBtn:hover {{
    background-color: {g.BTN_BG_HOVER};
    border-color: rgba(255, 255, 255, 0.16);
}}
QPushButton#micBtn {{
    background-color: {g.BTN_BG};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {g.BTN_BORDER};
    border-radius: 8px;
    padding: 8px 12px;
}}
QPushButton#micBtn:hover {{
    background-color: {g.BTN_BG_HOVER};
    border-color: rgba(255, 255, 255, 0.16);
}}
QPushButton#speakerBtn {{
    background-color: {g.BTN_BG};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {g.BTN_BORDER};
    border-radius: 8px;
    padding: 8px 12px;
}}
QPushButton#speakerBtn:hover {{
    background-color: {g.BTN_BG_HOVER};
    border-color: rgba(255, 255, 255, 0.16);
}}
QPushButton#jumpToBottom {{
    background-color: rgba(255, 255, 255, 0.08);
    color: {theme.TEXT_SECONDARY};
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    padding: 5px 16px;
    font-size: 11px;
    font-weight: 500;
}}
QPushButton#jumpToBottom:hover {{
    background-color: rgba(255, 255, 255, 0.14);
    color: {theme.TEXT_PRIMARY};
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
        stop:0 {theme.ACCENT_GREEN}, stop:1 rgba(48, 209, 88, 0.55));
    border-radius: 4px;
}}

/* ---- Group Box ---- */
QGroupBox {{
    background-color: {theme.BG_SECONDARY};
    border: 1px solid {theme.BORDER};
    border-radius: 12px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
    font-size: 12px;
    color: {theme.TEXT_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: {theme.TEXT_PRIMARY};
    font-weight: 600;
    letter-spacing: 0.3px;
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
    color: {theme.TEXT_PRIMARY};
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.2px;
}}
QLabel#secondaryLabel {{
    color: {theme.TEXT_SECONDARY};
    font-size: 12px;
}}

/* ---- Scroll Bars (ultra-thin) ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 0.12);
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(255, 255, 255, 0.28);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    height: 0;
}}

/* ---- Tab Widget (underline style) ---- */
QTabWidget::pane {{
    background: {theme.BG_SECONDARY};
    border: none;
    border-top: 1px solid {theme.BORDER};
}}
QTabBar::tab {{
    background: transparent;
    color: {theme.TEXT_SECONDARY};
    padding: 6px 10px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 0px;
    font-size: 12px;
    min-width: 50px;
}}
QTabBar::tab:selected {{
    background: transparent;
    color: {theme.TEXT_PRIMARY};
    font-weight: 600;
    border-bottom: 2px solid {theme.ACCENT_GREEN};
}}
QTabBar::tab:hover:!selected {{
    color: {theme.TEXT_PRIMARY};
    border-bottom: 2px solid rgba(255, 255, 255, 0.15);
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
    background-color: {g.INPUT_BG};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {g.INPUT_BORDER};
    border-radius: 10px;
    padding: 6px 12px;
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
    background: {g.INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background: {theme.TEXT_PRIMARY};
    border-color: {theme.TEXT_PRIMARY};
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
            bg = "rgba(255, 255, 255, 0.03)"
            role_label = "You"
            role_color = "#FFFFFF"
            border_left = "none"
        elif message.role == "assistant":
            bg = t.BUBBLE_AI
            role_label = "Kait"
            role_color = t.ACCENT_GREEN
            sentiment_colors = {
                "positive": t.SENTIMENT_POSITIVE,
                "negative": t.SENTIMENT_NEGATIVE,
                "neutral": t.SENTIMENT_NEUTRAL,
            }
            border_left = f"2px solid {sentiment_colors.get(message.sentiment, t.SENTIMENT_NEUTRAL)}"
        else:
            bg = t.BG_SECONDARY
            role_label = "System"
            role_color = t.TEXT_SECONDARY
            border_left = "none"

        ts = datetime.fromtimestamp(message.timestamp).strftime("%H:%M")

        self.setStyleSheet(
            f"ChatMessageWidget {{ "
            f"background-color: {bg}; "
            f"border-left: {border_left}; "
            f"border-radius: 12px; "
            f"padding: 0px; "
            f"margin: 0px; "
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(5)

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

        # Attachment chips (shown before body text)
        if message.attachments:
            att_row = QHBoxLayout()
            att_row.setSpacing(6)
            for att in message.attachments:
                name = att.get("name", "file")
                size = att.get("size", "")
                label_text = f"  {name}  ({size})" if size else f"  {name}"
                chip = QLabel(label_text)
                chip.setStyleSheet(
                    f"background: rgba(255,255,255,0.08); "
                    f"color: {t.TEXT_SECONDARY}; font-size: 12px; "
                    f"border: 1px solid rgba(255,255,255,0.12); "
                    f"border-radius: 6px; padding: 3px 8px;"
                )
                att_row.addWidget(chip)
            att_row.addStretch()
            layout.addLayout(att_row)

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
        self._synced_active = False
        self._synced_timer: Optional[QTimer] = None
        self._synced_words: List[str] = []
        self._synced_word_idx = 0
        self._synced_sentiment = "neutral"
        self._synced_on_complete: Optional[Callable] = None
        self._flush_scheduled: bool = False

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
        self._msg_layout.setContentsMargins(10, 10, 10, 10)
        self._msg_layout.setSpacing(10)
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
        """Append a token to the current streaming message (batched ~60fps)."""
        if not _QT_AVAILABLE or not self._streaming:
            return
        self._stream_tokens.append(token)
        if not self._flush_scheduled:
            self._flush_scheduled = True
            QTimer.singleShot(16, self._flush_stream_display)

    def _flush_stream_display(self) -> None:
        """Batch-update the streaming label instead of per-token repaints."""
        self._flush_scheduled = False
        if not self._streaming:
            return
        if self._streaming_body is not None:
            self._streaming_body.setText("".join(self._stream_tokens) + "\u2588")
        if self._auto_scroll:
            self._scroll_to_bottom()

    def finish_streaming(self, sentiment: str = "neutral", display_text: str = "") -> str:
        """Finalise the streaming message, returning the full text.

        If *display_text* is provided the chat bubble shows that instead of
        the full accumulated text (used for long-message summaries).
        """
        if not _QT_AVAILABLE:
            return ""
        self._streaming = False
        self._flush_scheduled = False
        full_text = "".join(self._stream_tokens)
        shown = display_text or full_text

        # Replace the cursor block with final text (or summary)
        if self._streaming_body is not None:
            self._streaming_body.setText(shown)

        # Record as a proper message
        if full_text:
            msg = ChatMessage("assistant", shown, sentiment)
            self._messages.append(msg)

        self._streaming_widget = None
        self._streaming_body = None
        self._stream_tokens = []
        return full_text

    def begin_synced_reveal(
        self,
        text: str,
        duration_ms: int,
        sentiment: str = "neutral",
        on_complete: Optional[Callable] = None,
    ) -> None:
        """Reveal *text* word-by-word over *duration_ms*, synchronized with TTS."""
        if not _QT_AVAILABLE:
            return
        words = text.split()
        if not words:
            if on_complete:
                on_complete()
            return

        self._synced_words = words
        self._synced_word_idx = 0
        self._synced_sentiment = sentiment
        self._synced_on_complete = on_complete
        self._synced_active = True

        self.begin_streaming()

        interval = max(30, duration_ms // len(words))
        self._synced_timer = QTimer()
        self._synced_timer.setInterval(interval)
        self._synced_timer.timeout.connect(self._synced_tick)
        self._synced_timer.start()

    def _synced_tick(self) -> None:
        """Reveal the next word in a synced-reveal sequence."""
        if self._synced_word_idx < len(self._synced_words):
            word = self._synced_words[self._synced_word_idx]
            separator = "" if self._synced_word_idx == 0 else " "
            self.append_token(separator + word)
            self._synced_word_idx += 1
        else:
            # All words revealed -- finalize
            if self._synced_timer:
                self._synced_timer.stop()
                self._synced_timer = None
            self._synced_active = False
            self.finish_streaming(self._synced_sentiment)
            if self._synced_on_complete:
                cb = self._synced_on_complete
                self._synced_on_complete = None
                cb()

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
# SkillsPanel -- pipeline skills graph + live observatory metrics
# ===================================================================

class _SkillsGraphWidget(QWidget if _QT_AVAILABLE else object):
    """Custom-painted pipeline skills graph with animated edges and hover effects."""

    # Node definitions: (key, label, x_col, y_row, color_hex)
    _NODES = [
        # Main pipeline spine (row 1, left to right)
        ("capture",     "Event\nCapture",       0, 1, "#3a7ca5"),   # Ingestion
        ("queue",       "Queue",                1, 1, "#3a7ca5"),   # Ingestion
        ("pipeline",    "Pipeline",             2, 1, "#5b8c5a"),   # Processing
        ("memory",      "Memory\nCapture",      3, 1, "#5b8c5a"),   # Processing
        ("metaralph",   "Meta-Ralph\nQuality",  4, 1, "#c09040"),   # Quality Gate
        ("advisory",    "Advisory",             5, 1, "#4a8c4a"),   # Output
        ("promotion",   "Promotion\nCLAUDE.md", 6, 1, "#a05080"),   # Output
        # Upper branch (row 0)
        ("predictions", "Predictions",          3, 0, "#7b68ae"),   # Intelligence
        ("eidos",       "EIDOS\nEpisodes",      4, 0, "#7b68ae"),   # Intelligence
        # Lower branch (row 2)
        ("cognitive",   "Cognitive\nLearner",    4, 2, "#7b68ae"),   # Intelligence
        ("chips",       "Chips\nModules",       3, 2, "#7b68ae"),   # Intelligence
        ("tuneables",   "Tuneables\nConfig",    5, 2, "#607a60"),   # Support
    ]

    # Edges: (from_key, to_key, label_or_None, dashed)
    _EDGES = [
        # Main spine
        ("capture",     "queue",       None,         False),
        ("queue",       "pipeline",    None,         False),
        ("pipeline",    "memory",      None,         False),
        ("memory",      "metaralph",   None,         False),
        ("metaralph",   "advisory",    "pass",       False),
        ("advisory",    "promotion",   None,         False),
        # Upper branch: Pipeline → Predictions → EIDOS → Advisory
        ("pipeline",    "predictions", None,         False),
        ("predictions", "eidos",       None,         False),
        ("eidos",       "advisory",    None,         False),
        # Lower branch: Meta-Ralph → Cognitive → Advisory
        ("metaralph",   "cognitive",   "pass",       False),
        ("cognitive",   "advisory",    None,         False),
        # Chips: Pipeline → Chips → Advisory
        ("pipeline",    "chips",       None,         False),
        ("chips",       "advisory",    None,         False),
        # Support: Tuneables configures Meta-Ralph and Advisory
        ("tuneables",   "metaralph",   "configures", True),
        ("tuneables",   "advisory",    "configures", True),
    ]

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self._node_states: dict = {}  # key -> "idle"/"running"/"done"
        self._health_data: dict = {}  # key -> {metric: value, ...}
        self._hovered_node: Optional[str] = None
        self._anim_phase: float = 0.0
        self.setMinimumSize(200, 220)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding if hasattr(QSizePolicy, "Policy") else QSizePolicy.Expanding,
            QSizePolicy.Policy.Expanding if hasattr(QSizePolicy, "Policy") else QSizePolicy.Expanding,
        )
        self.setMouseTracking(True)

        # Animation timer (~20fps)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_animation)
        self._anim_timer.start(50)

    def _tick_animation(self) -> None:
        self._anim_phase = (self._anim_phase + 0.03) % 1.0
        self.update()

    def _layout_metrics(self) -> dict:
        """Compute all size-dependent layout values from current widget dimensions."""
        w, h = self.width(), self.height()
        cols = 7
        row_count = 3  # rows: 0, 1, 2

        margin_x = max(30, int(w * 0.06))
        margin_y = max(20, int(h * 0.05))

        cell_w = max(1, (w - 2 * margin_x) // cols)
        cell_h = max(1, (h - 2 * margin_y) // row_count)

        node_w = max(32, min(200, int(cell_w * 0.82)))
        node_h = max(20, min(90, int(cell_h * 0.56)))

        scale = node_w / 100.0  # reference width is 100

        return {
            "margin_x": margin_x,
            "margin_y": margin_y,
            "cell_w": cell_w,
            "cell_h": cell_h,
            "node_w": node_w,
            "node_h": node_h,
            "scale": scale,
        }

    def set_node_state(self, key: str, state: str) -> None:
        self._node_states[key] = state
        self.update()

    def set_health(self, data: dict) -> None:
        self._health_data = data
        self.update()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _build_positions(self) -> dict:
        """Compute node center positions based on current widget size."""
        m = self._layout_metrics()
        margin_x, margin_y = m["margin_x"], m["margin_y"]
        cell_w, cell_h = m["cell_w"], m["cell_h"]

        def _row_y(r: int) -> int:
            return margin_y + r * cell_h + cell_h // 2

        def _col_x(c: int) -> int:
            return margin_x + c * cell_w + cell_w // 2

        positions: dict = {}
        for key, label, col, row, color in self._NODES:
            positions[key] = (_col_x(col), _row_y(row), label, color)
        return positions

    @staticmethod
    def _node_boundary(cx: float, cy: float, hw: float, hh: float,
                       vx: float, vy: float) -> tuple:
        """Find where a ray from (cx, cy) in direction (vx, vy) exits a rect."""
        if vx == 0 and vy == 0:
            return (cx, cy)
        tx = hw / abs(vx) if vx != 0 else float("inf")
        ty = hh / abs(vy) if vy != 0 else float("inf")
        t = min(tx, ty)
        return (cx + vx * t, cy + vy * t)

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if not _QT_AVAILABLE:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        mx, my = pos.x(), pos.y()
        m = self._layout_metrics()
        hw, hh = m["node_w"] / 2, m["node_h"] / 2
        positions = self._build_positions()
        hit = None
        for key in positions:
            cx, cy, _, _ = positions[key]
            if abs(mx - cx) <= hw and abs(my - cy) <= hh:
                hit = key
                break
        if hit != self._hovered_node:
            self._hovered_node = hit
            self.update()

    def leaveEvent(self, event: Any) -> None:  # noqa: N802
        if self._hovered_node is not None:
            self._hovered_node = None
            self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        if not _QT_AVAILABLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        m = self._layout_metrics()
        node_w, node_h = m["node_w"], m["node_h"]
        scale = m["scale"]
        hw, hh = node_w / 2.0, node_h / 2.0
        corner_r = 10.0 * scale
        positions = self._build_positions()
        hovered = self._hovered_node

        _NoPen = Qt.PenStyle.NoPen if hasattr(Qt, "PenStyle") else Qt.NoPen
        _NoBrush = Qt.BrushStyle.NoBrush if hasattr(Qt, "BrushStyle") else Qt.NoBrush
        _AlignC = (Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                   if hasattr(Qt, "AlignmentFlag")
                   else Qt.AlignHCenter | Qt.AlignVCenter)
        _DashLine = Qt.PenStyle.DashLine if hasattr(Qt, "PenStyle") else Qt.DashLine

        # --- Background: radial gradient + dot grid ---
        bg_grad = QRadialGradient(w / 2.0, h / 2.0, max(w, h) * 0.7)
        bg_grad.setColorAt(0.0, QColor(18, 20, 24))
        bg_grad.setColorAt(1.0, QColor(8, 8, 10))
        painter.fillRect(0, 0, w, h, QBrush(bg_grad))

        dot_pen = QPen(QColor(255, 255, 255, 12), 1.0)
        painter.setPen(dot_pen)
        spacing = 24
        for gx in range(0, w, spacing):
            for gy in range(0, h, spacing):
                painter.drawPoint(gx, gy)

        # Build hover-connected edge set
        connected_edges: set = set()
        if hovered:
            for i, (fk, tk, _, _) in enumerate(self._EDGES):
                if fk == hovered or tk == hovered:
                    connected_edges.add(i)

        # === EDGES ===
        for idx, (from_key, to_key, elabel, dashed) in enumerate(self._EDGES):
            if from_key not in positions or to_key not in positions:
                continue
            fx, fy, _, f_color = positions[from_key]
            tx, ty, _, t_color = positions[to_key]

            dx_raw, dy_raw = tx - fx, ty - fy
            dist = math.hypot(dx_raw, dy_raw) or 1.0

            # Edge endpoints at node boundaries
            sx, sy = self._node_boundary(fx, fy, hw, hh, dx_raw, dy_raw)
            ex, ey = self._node_boundary(tx, ty, hw, hh, -dx_raw, -dy_raw)

            # Bezier control point (slight perpendicular offset)
            mx_e, my_e = (sx + ex) / 2.0, (sy + ey) / 2.0
            perp_x, perp_y = -(ey - sy), (ex - sx)
            perp_len = math.hypot(perp_x, perp_y) or 1.0
            offset = min(20.0 * scale, dist * 0.1)
            cpx = mx_e + (perp_x / perp_len) * offset
            cpy = my_e + (perp_y / perp_len) * offset

            is_hl = idx in connected_edges
            alpha = 180 if is_hl else 80
            thickness = (2.0 if is_hl else 1.4) * max(0.7, scale)
            edge_color = QColor(f_color)
            edge_color.setAlpha(alpha)

            pen = QPen(edge_color, thickness)
            if dashed:
                pen.setStyle(_DashLine)
            painter.setPen(pen)
            painter.setBrush(_NoBrush)

            path = QPainterPath()
            path.moveTo(sx, sy)
            path.quadTo(cpx, cpy, ex, ey)
            painter.drawPath(path)

            # Arrowhead (tangent at t=1 is direction control->end)
            arr_dx, arr_dy = ex - cpx, ey - cpy
            arr_len = math.hypot(arr_dx, arr_dy) or 1.0
            arr_dx /= arr_len
            arr_dy /= arr_len
            arrow_sz = 7.0 * scale
            px, py = -arr_dy, arr_dx
            b1x = ex - arr_dx * arrow_sz + px * arrow_sz * 0.4
            b1y = ey - arr_dy * arrow_sz + py * arrow_sz * 0.4
            b2x = ex - arr_dx * arrow_sz - px * arrow_sz * 0.4
            b2y = ey - arr_dy * arrow_sz - py * arrow_sz * 0.4
            arrow_path = QPainterPath()
            arrow_path.moveTo(ex, ey)
            arrow_path.lineTo(b1x, b1y)
            arrow_path.lineTo(b2x, b2y)
            arrow_path.closeSubpath()
            painter.setPen(_NoPen)
            painter.setBrush(QBrush(edge_color))
            painter.drawPath(arrow_path)

            # Edge label on pill background
            if elabel:
                lx, ly = mx_e, my_e - 2
                font = painter.font()
                font.setPointSize(max(5, int(7 * scale)))
                painter.setFont(font)
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(elabel) if hasattr(fm, "horizontalAdvance") else fm.width(elabel)
                th = fm.height()
                pill_w, pill_h = tw + int(10 * scale), th + int(4 * scale)
                pill_rect = QRectF(lx - pill_w / 2, ly - pill_h / 2, pill_w, pill_h)
                painter.setPen(_NoPen)
                painter.setBrush(QBrush(QColor(20, 22, 26, 200)))
                pill_path = QPainterPath()
                pill_path.addRoundedRect(pill_rect, pill_h / 2, pill_h / 2)
                painter.drawPath(pill_path)
                painter.setPen(QColor(160, 160, 160))
                painter.drawText(pill_rect, _AlignC, elabel)

            # Animated flow particles on active edges
            src_st = self._node_states.get(from_key, "idle")
            dst_st = self._node_states.get(to_key, "idle")
            if src_st in ("running", "done") or dst_st in ("running", "done"):
                for pi in range(3):
                    t_p = (self._anim_phase + pi / 3.0) % 1.0
                    inv = 1.0 - t_p
                    bx = inv * inv * sx + 2 * inv * t_p * cpx + t_p * t_p * ex
                    by = inv * inv * sy + 2 * inv * t_p * cpy + t_p * t_p * ey
                    brightness = 1.0 - abs(t_p - 0.5) * 2.0
                    p_alpha = int(180 * brightness)
                    pc = QColor(f_color)
                    pc.setAlpha(p_alpha)
                    p_r = max(3.0, 5.0 * scale)
                    p_grad = QRadialGradient(bx, by, p_r)
                    p_grad.setColorAt(0.0, pc)
                    pc_out = QColor(f_color)
                    pc_out.setAlpha(0)
                    p_grad.setColorAt(1.0, pc_out)
                    painter.setPen(_NoPen)
                    painter.setBrush(QBrush(p_grad))
                    painter.drawEllipse(QPointF(bx, by), p_r, p_r)

        # === NODES ===
        for key, label, col, row, base_color in self._NODES:
            cx, cy, _, _ = positions[key]
            rx, ry = cx - hw, cy - hh
            state = self._node_states.get(key, "idle")
            is_hov = (key == hovered)

            # Drop shadow
            painter.setPen(_NoPen)
            shadow_off = max(2.0, 3.0 * scale)
            painter.setBrush(QBrush(QColor(0, 0, 0, 60)))
            sp = QPainterPath()
            sp.addRoundedRect(QRectF(rx + shadow_off, ry + shadow_off, node_w, node_h), corner_r, corner_r)
            painter.drawPath(sp)

            # Glow halo for active / hovered nodes
            if state in ("running", "done") or is_hov:
                glow_a = 90 if is_hov else 60
                glow_r = max(node_w, node_h) * 0.8
                gc = QColor(base_color)
                gc.setAlpha(glow_a)
                gg = QRadialGradient(cx, cy, glow_r)
                gg.setColorAt(0.0, gc)
                gc_out = QColor(base_color)
                gc_out.setAlpha(0)
                gg.setColorAt(1.0, gc_out)
                painter.setBrush(QBrush(gg))
                painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

            # Node fill: linear gradient (lighter top -> darker bottom)
            fill_grad = QLinearGradient(rx, ry, rx, ry + node_h)
            if state == "running":
                top_c = QColor(base_color).lighter(160 if is_hov else 140)
                top_c.setAlpha(230)
                bot_c = QColor(base_color)
                bot_c.setAlpha(230)
                border_c = QColor("#ffffff")
            elif state == "done":
                top_c = QColor(base_color).lighter(140 if is_hov else 120)
                top_c.setAlpha(200)
                bot_c = QColor(base_color)
                bot_c.setAlpha(180)
                border_c = QColor("#88ee88")
            else:
                top_c = QColor(base_color).lighter(140 if is_hov else 110)
                top_c.setAlpha(160 if is_hov else 110)
                bot_c = QColor(base_color)
                bot_c.setAlpha(120 if is_hov else 80)
                border_c = QColor(base_color)
                border_c.setAlpha(180 if is_hov else 120)

            fill_grad.setColorAt(0.0, top_c)
            fill_grad.setColorAt(1.0, bot_c)
            painter.setPen(QPen(border_c, (2.0 if is_hov else 1.5) * max(0.7, scale)))
            painter.setBrush(QBrush(fill_grad))
            np = QPainterPath()
            np.addRoundedRect(QRectF(rx, ry, node_w, node_h), corner_r, corner_r)
            painter.drawPath(np)

            # Inner highlight gleam (top portion)
            gleam = QLinearGradient(rx, ry, rx, ry + node_h * 0.4)
            gleam.setColorAt(0.0, QColor(255, 255, 255, 50 if is_hov else 30))
            gleam.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(_NoPen)
            painter.setBrush(QBrush(gleam))
            gp = QPainterPath()
            gp.addRoundedRect(
                QRectF(rx + 1, ry + 1, node_w - 2, node_h * 0.4),
                corner_r - 1, corner_r - 1,
            )
            painter.drawPath(gp)

            # Status indicator dot (top-right corner)
            dot_x, dot_y, dot_r = rx + node_w - 8 * scale, ry + 8 * scale, max(2.5, 4.0 * scale)
            painter.setPen(_NoPen)
            if state == "running":
                pulse = 0.5 + 0.5 * math.sin(self._anim_phase * 2 * math.pi)
                painter.setBrush(QBrush(QColor(255, 255, 255, int(120 + 135 * pulse))))
            elif state == "done":
                painter.setBrush(QBrush(QColor(100, 220, 100, 220)))
            else:
                painter.setBrush(QBrush(QColor(100, 100, 100, 80)))
            painter.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)

            # Label text
            tc = QColor("#ffffff") if is_hov else (
                QColor("#e0e0e0") if state != "idle" else QColor("#a0a0a0"))
            painter.setPen(tc)
            font = painter.font()
            font.setPointSize(max(5, int(9 * scale)))
            font.setBold(state == "running")
            painter.setFont(font)
            painter.drawText(
                QRectF(rx + 2, ry + 2, node_w - 4, node_h - 4),
                _AlignC, label,
            )

        # === COLOR LEGEND ===
        _legend = [
            ("#3a7ca5", "Ingestion"),
            ("#5b8c5a", "Processing"),
            ("#c09040", "Quality Gate"),
            ("#7b68ae", "Intelligence"),
            ("#4a8c4a", "Output"),
            ("#a05080", "Promotion"),
            ("#607a60", "Support"),
        ]
        legend_font = painter.font()
        legend_font.setPointSize(max(5, int(7 * scale)))
        legend_font.setBold(False)
        painter.setFont(legend_font)
        lfm = painter.fontMetrics()
        dot_radius = max(3.0, 4.0 * scale)
        legend_y = h - max(12, int(14 * scale))
        legend_x = m["margin_x"]
        for lcolor, ltxt in _legend:
            painter.setPen(_NoPen)
            painter.setBrush(QBrush(QColor(lcolor)))
            painter.drawEllipse(QPointF(legend_x + dot_radius, legend_y), dot_radius, dot_radius)
            painter.setPen(QColor(160, 160, 160))
            txt_x = legend_x + dot_radius * 2 + max(3, int(4 * scale))
            txt_w = lfm.horizontalAdvance(ltxt) if hasattr(lfm, "horizontalAdvance") else lfm.width(ltxt)
            painter.drawText(QRectF(txt_x, legend_y - lfm.height() / 2, txt_w + 4, lfm.height()), _AlignC, ltxt)
            legend_x = txt_x + txt_w + max(8, int(12 * scale))

        painter.end()


class _MetricCard(QFrame if _QT_AVAILABLE else object):
    """Compact card displaying a metric value and label for the dashboard."""

    def __init__(self, label_text: str, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        t = Theme
        self.setObjectName("metricCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(1)

        self._value_label = QLabel("--")
        self._value_label.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            f"font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._value_label)

        self._name_label = QLabel(label_text)
        self._name_label.setStyleSheet(
            f"color: {t.TEXT_SECONDARY}; font-size: 10px; font-weight: 400; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._name_label)

        self.setStyleSheet(
            f"QFrame#metricCard {{ background: rgba(255, 255, 255, 0.03); "
            f"border: 1px solid {t.BORDER}; border-radius: 8px; }}"
        )

    def set_value(self, text: str) -> None:
        if _QT_AVAILABLE:
            self._value_label.setText(text)

    def set_highlight(self, active: bool) -> None:
        """Highlight the card value green when the metric is active."""
        if not _QT_AVAILABLE:
            return
        t = Theme
        color = t.ACCENT_GREEN if active else t.TEXT_PRIMARY
        self._value_label.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 700; "
            f"font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace; "
            f"background: transparent; border: none;"
        )


class DashboardPanel(QWidget if _QT_AVAILABLE else object):
    """Unified OS Sidekick dashboard -- pipeline, intelligence metrics,
    context gauge, activity feed, and model info in a single view.

    Replaces the former separate Skills and Monitor tabs.  All public
    methods from both panels are preserved for backward compatibility.
    """

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        t = Theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # --- Status row: active step + model badge ---
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self._active_step_label = QLabel("Idle")
        self._active_step_label.setStyleSheet(
            f"color: {t.ACCENT_GOLD}; font-size: 12px; font-weight: 600; "
            f"font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace; "
            f"background: transparent; border: none; padding: 2px 0;"
        )
        status_row.addWidget(self._active_step_label)
        status_row.addStretch()

        self._model_badge = QLabel("--")
        self._model_badge.setStyleSheet(
            f"color: {t.TEXT_SECONDARY}; font-size: 10px; "
            f"background: rgba(255, 255, 255, 0.05); "
            f"border: 1px solid {t.BORDER}; border-radius: 4px; "
            f"padding: 2px 8px;"
        )
        status_row.addWidget(self._model_badge)
        layout.addLayout(status_row)

        # --- Pipeline Flow (kept as-is) ---
        graph_group = QGroupBox("Pipeline Flow")
        graph_lay = QVBoxLayout(graph_group)
        self._graph = _SkillsGraphWidget()
        graph_lay.addWidget(self._graph)
        layout.addWidget(graph_group, stretch=1)

        # --- Intelligence metrics grid ---
        intel_group = QGroupBox("Intelligence")
        metrics_grid = QGridLayout(intel_group)
        metrics_grid.setSpacing(6)
        metrics_grid.setContentsMargins(8, 8, 8, 8)

        self._card_queue = _MetricCard("Queue (events)")
        self._card_pipeline = _MetricCard("Processed (events)")
        self._card_cycle = _MetricCard("Last Cycle (ago)")
        self._card_metaralph = _MetricCard("Meta-Ralph (roasts)")
        self._card_cognitive = _MetricCard("Cognitive (insights)")
        self._card_eidos = _MetricCard("EIDOS (episodes)")
        self._card_advisory = _MetricCard("Advisory (advice)")
        self._card_promotion = _MetricCard("Promotion (entries)")

        metrics_grid.addWidget(self._card_queue, 0, 0)
        metrics_grid.addWidget(self._card_pipeline, 0, 1)
        metrics_grid.addWidget(self._card_cycle, 1, 0)
        metrics_grid.addWidget(self._card_metaralph, 1, 1)
        metrics_grid.addWidget(self._card_cognitive, 2, 0)
        metrics_grid.addWidget(self._card_eidos, 2, 1)
        metrics_grid.addWidget(self._card_advisory, 3, 0)
        metrics_grid.addWidget(self._card_promotion, 3, 1)
        layout.addWidget(intel_group)

        # --- Activity feed ---
        activity_group = QGroupBox("Activity")
        activity_lay = QVBoxLayout(activity_group)
        activity_lay.setSpacing(4)

        self._activity_feed = QTextEdit()
        self._activity_feed.setReadOnly(True)
        self._activity_feed.setMaximumHeight(120)
        self._activity_feed.setStyleSheet(
            f"background: rgba(255, 255, 255, 0.03); color: {t.TEXT_PRIMARY}; "
            f"font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace; font-size: 11px; "
            f"border: 1px solid {t.BORDER}; border-radius: 8px; padding: 6px;"
        )
        activity_lay.addWidget(self._activity_feed)

        self._agent_list = QTextEdit()
        self._agent_list.setReadOnly(True)
        self._agent_list.setMaximumHeight(60)
        self._agent_list.setStyleSheet(
            f"background: rgba(255, 255, 255, 0.03); color: {t.TEXT_SECONDARY}; "
            f"font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace; font-size: 10px; "
            f"border: 1px solid {t.BORDER}; border-radius: 8px; padding: 4px;"
        )
        self._agent_list.setPlainText("No agent activity yet.")
        activity_lay.addWidget(self._agent_list)
        layout.addWidget(activity_group)

        # --- Status text ---
        self._status_text = QLabel("Waiting for first interaction...")
        self._status_text.setObjectName("dimLabel")
        self._status_text.setWordWrap(True)
        layout.addWidget(self._status_text)

        # Internal state for backward compat
        self._token_count = 0
        self._model_name = "--"
        self._provider_name = "--"
        self._latency_text = "--"

        # Periodic health refresh from observatory
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._refresh_health)
        self._health_timer.start(15_000)
        QTimer.singleShot(2000, self._refresh_health)

    # --- SkillsPanel backward-compatible API ---------------------------------

    def update_stages(self, text: str) -> None:
        """Parse pipeline stage text and update graph node states."""
        if not _QT_AVAILABLE:
            return
        stage_to_node = {
            1: "capture", 2: "queue", 3: "pipeline", 4: "memory", 5: "cognitive",
        }
        for line in text.split("\n"):
            for snum, nkey in stage_to_node.items():
                if line.strip().startswith(f"{snum}."):
                    if "running" in line.lower():
                        self._graph.set_node_state(nkey, "running")
                    elif "done" in line.lower():
                        self._graph.set_node_state(nkey, "done")
                    else:
                        self._graph.set_node_state(nkey, "idle")

    def update_status(self, text: str) -> None:
        """Update the status label at the bottom."""
        if _QT_AVAILABLE:
            self._status_text.setText(text)

    # --- ProcessingMonitorPanel backward-compatible API ----------------------

    def append_feed_entry(self, text: str) -> None:
        """Append a timestamped line to the activity feed, auto-scroll."""
        if not _QT_AVAILABLE:
            return
        ts = datetime.fromtimestamp(time.time()).strftime("%H:%M:%S")
        self._activity_feed.append(f"{ts}  {text}")
        sb = self._activity_feed.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_feed(self) -> None:
        """Clear the activity feed."""
        if _QT_AVAILABLE:
            self._activity_feed.setPlainText("")

    def set_active_step(self, name: str) -> None:
        """Set the active step indicator to '>>> {name}'."""
        if _QT_AVAILABLE:
            self._active_step_label.setText(f">>> {name}")

    def set_idle(self) -> None:
        """Reset active step indicator to Idle."""
        if _QT_AVAILABLE:
            self._active_step_label.setText("Idle")

    def update_token_count(self, count: int) -> None:
        """Track streaming token count."""
        if _QT_AVAILABLE:
            self._token_count = count

    def update_elapsed(self, elapsed_ms: int) -> None:
        """Append elapsed time to the active step label."""
        if not _QT_AVAILABLE:
            return
        current = self._active_step_label.text()
        if "(" in current:
            current = current[:current.rfind("(")].rstrip()
        secs = elapsed_ms / 1000
        self._active_step_label.setText(f"{current}  ({secs:.1f}s)")

    def update_context_gauge(self, used: int, maximum: int) -> None:
        """No-op -- tokens gauge removed."""
        pass

    def update_agent_activity(self, entries: List[str]) -> None:
        """Replace the agent activity list."""
        if not _QT_AVAILABLE:
            return
        if entries:
            self._agent_list.setPlainText("\n".join(entries))
        else:
            self._agent_list.setPlainText("No agent activity yet.")

    def update_model_info(self, model: str = "--", provider: str = "--", latency: str = "--") -> None:
        """Update the model badge with model, provider, and latency."""
        if not _QT_AVAILABLE:
            return
        self._model_name = model
        self._provider_name = provider
        self._latency_text = latency
        parts = [p for p in (model, provider, latency) if p and p != "--"]
        self._model_badge.setText("  |  ".join(parts) if parts else "--")

    def update_source_stats(self, stats: Dict[str, int]) -> None:
        """Store source stats (shown via status text on next metrics update)."""
        if not _QT_AVAILABLE:
            return
        if stats:
            total = sum(stats.values())
            parts = [f"{src}: {cnt}" for src, cnt in sorted(stats.items())]
            self._status_text.setText(f"Sources: {', '.join(parts)} (total {total})")

    def update_metrics(self, metrics: Dict[str, Any]) -> None:
        """Display key metrics in the status text."""
        if not _QT_AVAILABLE:
            return
        parts = [f"{k}: {v}" for k, v in metrics.items()]
        if parts:
            self._status_text.setText("  |  ".join(parts))

    # --- Health refresh (observatory) ----------------------------------------

    def _refresh_health(self) -> None:
        """Load live metrics from observatory readers and update cards + graph."""
        if not _QT_AVAILABLE:
            return
        try:
            from lib.observatory.readers import read_all_stages
            from lib.observatory.linker import fmt_num, fmt_ago, health_badge
            data = read_all_stages(max_recent=5)

            # Update graph node states
            p = data.get(3, {})
            if p.get("last_cycle_ts"):
                import time as _t
                diff = _t.time() - p["last_cycle_ts"]
                self._graph.set_node_state("pipeline", "done" if diff < 300 else "idle")

            mr = data.get(5, {})
            if mr.get("total_roasted", 0) > 0:
                self._graph.set_node_state("metaralph", "done")

            cg = data.get(6, {})
            if cg.get("total_insights", 0) > 0:
                self._graph.set_node_state("cognitive", "done")

            ei = data.get(7, {})
            if ei.get("episodes", 0) > 0:
                self._graph.set_node_state("eidos", "done")

            ad = data.get(8, {})
            if ad.get("total_advice_given", 0) > 0:
                self._graph.set_node_state("advisory", "done")

            pr = data.get(9, {})
            if pr.get("total_entries", 0) > 0:
                self._graph.set_node_state("promotion", "done")

            # Update metric cards
            q = data.get(2, {})
            pending = q.get("estimated_pending", 0)
            self._card_queue.set_value(f"~{fmt_num(pending)} pending")
            self._card_queue.set_highlight(pending > 0)

            rate = p.get("last_processing_rate", 0)
            total_proc = p.get("total_events_processed", 0)
            self._card_pipeline.set_value(
                f"{fmt_num(total_proc)} events ({rate:.1f} evt/s)"
            )

            self._card_cycle.set_value(fmt_ago(p.get("last_cycle_ts")))

            roasted = mr.get("total_roasted", 0)
            pass_rate = mr.get("pass_rate", 0)
            self._card_metaralph.set_value(
                f"{fmt_num(roasted)} roasts  {pass_rate}% pass"
            )
            self._card_metaralph.set_highlight(roasted > 0)

            insights = cg.get("total_insights", 0)
            self._card_cognitive.set_value(f"{fmt_num(insights)} insights")
            self._card_cognitive.set_highlight(insights > 0)

            eps = ei.get("episodes", 0)
            dist = ei.get("distillations", 0)
            self._card_eidos.set_value(
                f"{fmt_num(eps)} episodes  {fmt_num(dist)} distills"
            )
            self._card_eidos.set_highlight(eps > 0)

            advice = ad.get("total_advice_given", 0)
            followed = ad.get("followed_rate", 0)
            self._card_advisory.set_value(
                f"{fmt_num(advice)} given  {followed}% followed"
            )
            self._card_advisory.set_highlight(advice > 0)

            entries = pr.get("total_entries", 0)
            self._card_promotion.set_value(f"{fmt_num(entries)} entries")
            self._card_promotion.set_highlight(entries > 0)

        except Exception:
            pass  # Non-critical -- never crash the GUI


# Backward-compatible aliases
SkillsPanel = DashboardPanel
ObservatoryPanel = DashboardPanel
ProcessingMonitorPanel = DashboardPanel


# ===================================================================
# ChatHistoryPanel -- browsable session history
# ===================================================================

class ChatHistoryPanel(QWidget if _QT_AVAILABLE else object):
    """Browsable chat history panel with Recent/Archives sub-tabs."""

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self._bank = None
        t = Theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel("Chat History")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # --- Filter row ---
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self._source_filter = QComboBox()
        self._source_filter.addItems(["All", "GUI", "Matrix", "CLI"])
        self._source_filter.setFixedWidth(100)
        self._source_filter.currentIndexChanged.connect(lambda _: self.refresh())
        filter_row.addWidget(self._source_filter)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search messages...")
        self._search_input.returnPressed.connect(self.refresh)
        filter_row.addWidget(self._search_input)

        layout.addLayout(filter_row)

        # --- Sub-tab bar: [Recent] [Archives] ---
        _active_tab_style = (
            f"QPushButton {{ background: transparent; color: {t.TEXT_PRIMARY}; "
            f"border: none; border-bottom: 2px solid {t.ACCENT_GREEN}; "
            f"font-size: 12px; font-weight: 600; padding: 4px 12px; }}"
        )
        _inactive_tab_style = (
            f"QPushButton {{ background: transparent; color: {t.TEXT_DIM}; "
            f"border: none; border-bottom: 2px solid transparent; "
            f"font-size: 12px; padding: 4px 12px; }}"
            f"QPushButton:hover {{ color: {t.TEXT_SECONDARY}; }}"
        )
        self._active_tab_style = _active_tab_style
        self._inactive_tab_style = _inactive_tab_style

        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)

        self._recent_tab_btn = QPushButton("Recent")
        self._recent_tab_btn.setFixedHeight(28)
        self._recent_tab_btn.setStyleSheet(_active_tab_style)
        self._recent_tab_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if hasattr(Qt, "CursorShape") else Qt.PointingHandCursor
        )
        self._recent_tab_btn.clicked.connect(lambda: self._switch_sub_tab(0))
        tab_row.addWidget(self._recent_tab_btn)

        self._archives_tab_btn = QPushButton("Archives")
        self._archives_tab_btn.setFixedHeight(28)
        self._archives_tab_btn.setStyleSheet(_inactive_tab_style)
        self._archives_tab_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if hasattr(Qt, "CursorShape") else Qt.PointingHandCursor
        )
        self._archives_tab_btn.clicked.connect(lambda: self._switch_sub_tab(1))
        tab_row.addWidget(self._archives_tab_btn)

        tab_row.addStretch()
        layout.addLayout(tab_row)

        # --- Main stacked widget ---
        self._main_stack = QStackedWidget()

        # ======= Page 0: Recent (existing session list + detail) =======
        self._recent_stack = QStackedWidget()

        # Sub-page 0: Session list
        self._list_page = QWidget()
        list_layout = QVBoxLayout(self._list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self._session_scroll = QScrollArea()
        self._session_scroll.setWidgetResizable(True)
        self._session_scroll.setFrameStyle(
            QFrame.Shape.NoFrame if hasattr(QFrame, "Shape") else QFrame.NoFrame
        )
        self._session_container = QWidget()
        self._session_layout = QVBoxLayout(self._session_container)
        self._session_layout.setContentsMargins(0, 0, 0, 0)
        self._session_layout.setSpacing(4)
        self._session_layout.addStretch()
        self._session_scroll.setWidget(self._session_container)
        list_layout.addWidget(self._session_scroll)
        self._recent_stack.addWidget(self._list_page)

        # Sub-page 1: Session detail
        self._detail_page = QWidget()
        detail_layout = QVBoxLayout(self._detail_page)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        back_btn = QPushButton("< Back to Sessions")
        back_btn.setFixedHeight(28)
        back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t.TEXT_SECONDARY}; "
            f"border: none; text-align: left; font-size: 12px; padding: 2px 6px; }}"
            f"QPushButton:hover {{ color: {t.TEXT_PRIMARY}; }}"
        )
        back_btn.clicked.connect(lambda: self._recent_stack.setCurrentIndex(0))
        detail_layout.addWidget(back_btn)

        self._detail_header = QLabel("")
        self._detail_header.setObjectName("dimLabel")
        self._detail_header.setWordWrap(True)
        detail_layout.addWidget(self._detail_header)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet(
            f"background: {t.BG_PRIMARY}; color: {t.TEXT_PRIMARY}; "
            f"border: 1px solid {t.BORDER}; border-radius: 8px; "
            f"font-size: 13px; padding: 8px;"
        )
        detail_layout.addWidget(self._detail_text)
        self._recent_stack.addWidget(self._detail_page)

        self._main_stack.addWidget(self._recent_stack)

        # ======= Page 1: Archives (archive list + archive detail) =======
        self._archive_stack = QStackedWidget()

        # Sub-page 0: Archive list
        self._archive_list_page = QWidget()
        archive_list_layout = QVBoxLayout(self._archive_list_page)
        archive_list_layout.setContentsMargins(0, 0, 0, 0)

        self._archive_scroll = QScrollArea()
        self._archive_scroll.setWidgetResizable(True)
        self._archive_scroll.setFrameStyle(
            QFrame.Shape.NoFrame if hasattr(QFrame, "Shape") else QFrame.NoFrame
        )
        self._archive_container = QWidget()
        self._archive_layout = QVBoxLayout(self._archive_container)
        self._archive_layout.setContentsMargins(0, 0, 0, 0)
        self._archive_layout.setSpacing(4)
        self._archive_layout.addStretch()
        self._archive_scroll.setWidget(self._archive_container)
        archive_list_layout.addWidget(self._archive_scroll)
        self._archive_stack.addWidget(self._archive_list_page)

        # Sub-page 1: Archive detail
        self._archive_detail_page = QWidget()
        archive_detail_layout = QVBoxLayout(self._archive_detail_page)
        archive_detail_layout.setContentsMargins(0, 0, 0, 0)

        archive_back_btn = QPushButton("< Back to Archives")
        archive_back_btn.setFixedHeight(28)
        archive_back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t.TEXT_SECONDARY}; "
            f"border: none; text-align: left; font-size: 12px; padding: 2px 6px; }}"
            f"QPushButton:hover {{ color: {t.TEXT_PRIMARY}; }}"
        )
        archive_back_btn.clicked.connect(lambda: self._archive_stack.setCurrentIndex(0))
        archive_detail_layout.addWidget(archive_back_btn)

        self._archive_detail_header = QLabel("")
        self._archive_detail_header.setObjectName("dimLabel")
        self._archive_detail_header.setWordWrap(True)
        archive_detail_layout.addWidget(self._archive_detail_header)

        self._archive_summary_text = QTextEdit()
        self._archive_summary_text.setReadOnly(True)
        self._archive_summary_text.setMaximumHeight(200)
        self._archive_summary_text.setStyleSheet(
            f"background: {t.BG_TERTIARY}; color: {t.TEXT_PRIMARY}; "
            f"border: 1px solid {t.BORDER}; border-radius: 8px; "
            f"font-size: 13px; padding: 8px;"
        )
        archive_detail_layout.addWidget(self._archive_summary_text)

        self._archive_detail_text = QTextEdit()
        self._archive_detail_text.setReadOnly(True)
        self._archive_detail_text.setStyleSheet(
            f"background: {t.BG_PRIMARY}; color: {t.TEXT_PRIMARY}; "
            f"border: 1px solid {t.BORDER}; border-radius: 8px; "
            f"font-size: 13px; padding: 8px;"
        )
        archive_detail_layout.addWidget(self._archive_detail_text)
        self._archive_stack.addWidget(self._archive_detail_page)

        self._main_stack.addWidget(self._archive_stack)

        # Keep _stack as alias for back-compat with _show_session
        self._stack = self._recent_stack

        layout.addWidget(self._main_stack, stretch=1)

        # --- Source stats ---
        self._stats_label = QLabel("")
        self._stats_label.setObjectName("dimLabel")
        self._stats_label.setWordWrap(True)
        layout.addWidget(self._stats_label)

    def _switch_sub_tab(self, index: int) -> None:
        """Switch between Recent (0) and Archives (1) sub-tabs."""
        self._main_stack.setCurrentIndex(index)
        if index == 0:
            self._recent_tab_btn.setStyleSheet(self._active_tab_style)
            self._archives_tab_btn.setStyleSheet(self._inactive_tab_style)
            self.refresh()
        else:
            self._recent_tab_btn.setStyleSheet(self._inactive_tab_style)
            self._archives_tab_btn.setStyleSheet(self._active_tab_style)
            self._refresh_archives()

    def set_bank(self, bank) -> None:
        """Set the ReasoningBank reference and do an initial refresh."""
        self._bank = bank
        self.refresh()

    def refresh(self) -> None:
        """Reload sessions from the database."""
        if not _QT_AVAILABLE or not self._bank:
            return
        t = Theme

        # Determine source filter
        source_text = self._source_filter.currentText().lower()
        source_filter = None if source_text == "all" else source_text

        sessions = self._bank.get_recent_sessions(source=source_filter, limit=100)

        # Apply search filter
        search = self._search_input.text().strip().lower()
        if search:
            sessions = [s for s in sessions if search in (s.get("first_message") or "").lower()]

        # Clear existing cards
        while self._session_layout.count() > 1:
            item = self._session_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Source badge colors
        badge_colors = {
            "gui": "#3A3A3C",
            "matrix": "#1A3A2A",
            "cli": "#2A2A3A",
        }

        # Group by date
        from datetime import datetime as _dt
        date_groups: Dict[str, list] = {}
        for sess in sessions:
            ts = sess.get("last_ts") or sess.get("first_ts") or 0
            day = _dt.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "Unknown"
            date_groups.setdefault(day, []).append(sess)

        for day, group in date_groups.items():
            # Date header
            day_label = QLabel(day)
            day_label.setStyleSheet(
                f"color: {t.TEXT_DIM}; font-size: 11px; padding: 4px 0 2px 0;"
            )
            self._session_layout.insertWidget(self._session_layout.count() - 1, day_label)

            for sess in group:
                card = self._make_session_card(sess, badge_colors, t)
                self._session_layout.insertWidget(self._session_layout.count() - 1, card)

        # Update stats
        stats = self._bank.get_source_stats()
        parts = [f"{src}: {cnt}" for src, cnt in sorted(stats.items())]
        self._stats_label.setText("Sources: " + " | ".join(parts) if parts else "")

    def _make_session_card(self, sess: Dict, badge_colors: Dict, t) -> QFrame:
        """Build a clickable session card widget."""
        from datetime import datetime as _dt

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {t.BG_TERTIARY}; border: 1px solid {t.BORDER}; "
            f"border-radius: 6px; padding: 6px; }}"
            f"QFrame:hover {{ border-color: {t.TEXT_DIM}; }}"
        )
        card.setCursor(Qt.CursorShape.PointingHandCursor if hasattr(Qt, "CursorShape") else Qt.PointingHandCursor)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(3)

        # Top row: source badge + time + count
        top = QHBoxLayout()
        top.setSpacing(6)

        source = sess.get("source") or "gui"
        badge = QLabel(source.upper())
        bg = badge_colors.get(source, "#3A3A3C")
        badge.setStyleSheet(
            f"background: {bg}; color: {t.TEXT_SECONDARY}; "
            f"font-size: 10px; padding: 1px 5px; border-radius: 3px;"
        )
        badge.setFixedHeight(16)
        top.addWidget(badge)

        ts = sess.get("last_ts") or sess.get("first_ts") or 0
        time_label = QLabel(_dt.fromtimestamp(ts).strftime("%H:%M") if ts else "")
        time_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: 11px;")
        top.addWidget(time_label)

        top.addStretch()

        count = sess.get("msg_count", 0)
        count_label = QLabel(f"{count} msg{'s' if count != 1 else ''}")
        count_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: 11px;")
        top.addWidget(count_label)

        card_layout.addLayout(top)

        # Preview text
        preview = (sess.get("first_message") or "")[:80]
        if len(sess.get("first_message") or "") > 80:
            preview += "..."
        preview_label = QLabel(preview)
        preview_label.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 12px;")
        preview_label.setWordWrap(True)
        card_layout.addWidget(preview_label)

        # Click handler
        session_id = sess.get("session_id")
        card.mousePressEvent = lambda _ev, sid=session_id, src=source: self._show_session(sid, src)

        return card

    def _show_session(self, session_id: str, source: str) -> None:
        """Load a full session conversation into the detail view."""
        if not self._bank:
            return
        t = Theme

        history = self._bank.get_interaction_history(
            limit=200, session_id=session_id,
        )
        # Oldest first for reading order
        history.reverse()

        self._detail_header.setText(
            f"Session: {session_id[:12]}...  |  Source: {source.upper()}  |  {len(history)} messages"
        )

        from datetime import datetime as _dt
        html_parts: list = []
        for row in history:
            ts = row.get("timestamp", 0)
            ts_str = _dt.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
            user_text = (row.get("user_input") or "").replace("<", "&lt;").replace(">", "&gt;")
            ai_text = (row.get("ai_response") or "").replace("<", "&lt;").replace(">", "&gt;")

            html_parts.append(
                f'<p><span style="color:{t.TEXT_DIM};font-size:11px;">[{ts_str}]</span> '
                f'<span style="color:{t.TEXT_PRIMARY};font-weight:bold;">You:</span> '
                f'<span style="color:{t.TEXT_SECONDARY};">{user_text}</span></p>'
            )
            html_parts.append(
                f'<p><span style="color:{t.TEXT_DIM};font-size:11px;">[{ts_str}]</span> '
                f'<span style="color:{t.ACCENT_PURPLE};font-weight:bold;">Kait:</span> '
                f'<span style="color:{t.TEXT_PRIMARY};">{ai_text}</span></p>'
            )

        self._detail_text.setHtml("".join(html_parts) if html_parts else "<i>No messages</i>")
        self._recent_stack.setCurrentIndex(1)


    def _refresh_archives(self) -> None:
        """Reload archive records from the database."""
        if not _QT_AVAILABLE or not self._bank:
            return
        t = Theme

        archives = self._bank.get_archives(limit=100)

        # Clear existing cards
        while self._archive_layout.count() > 1:
            item = self._archive_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not archives:
            empty_label = QLabel("No archives yet. Sessions older than 24 hours are auto-archived.")
            empty_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: 12px; padding: 12px;")
            empty_label.setWordWrap(True)
            self._archive_layout.insertWidget(0, empty_label)
            return

        for archive in archives:
            card = self._make_archive_card(archive, t)
            self._archive_layout.insertWidget(self._archive_layout.count() - 1, card)

    def _make_archive_card(self, archive: Dict, t) -> QFrame:
        """Build a clickable archive summary card."""
        import json as _json

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {t.BG_TERTIARY}; border: 1px solid {t.BORDER}; "
            f"border-radius: 6px; padding: 6px; }}"
            f"QFrame:hover {{ border-color: {t.TEXT_DIM}; }}"
        )
        card.setCursor(
            Qt.CursorShape.PointingHandCursor if hasattr(Qt, "CursorShape") else Qt.PointingHandCursor
        )

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(3)

        # Top row: date + mood badge + message count
        top = QHBoxLayout()
        top.setSpacing(6)

        batch_label = archive.get("batch_label", "Unknown")
        date_label = QLabel(batch_label)
        date_label.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;")
        top.addWidget(date_label)

        top.addStretch()

        mood = archive.get("mood_summary", "")
        if mood:
            mood_badge = QLabel(mood)
            mood_badge.setStyleSheet(
                f"background: #1A3A2A; color: {t.ACCENT_GREEN}; "
                f"font-size: 10px; padding: 1px 5px; border-radius: 3px;"
            )
            mood_badge.setFixedHeight(16)
            top.addWidget(mood_badge)

        count = archive.get("interaction_count", 0)
        count_label = QLabel(f"{count} msgs")
        count_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: 11px;")
        top.addWidget(count_label)

        card_layout.addLayout(top)

        # Narrative snippet (2 lines)
        narrative = archive.get("narrative_summary", "")
        snippet = narrative[:120] + ("..." if len(narrative) > 120 else "")
        if snippet:
            snippet_label = QLabel(snippet)
            snippet_label.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 12px;")
            snippet_label.setWordWrap(True)
            snippet_label.setMaximumHeight(36)
            card_layout.addWidget(snippet_label)

        # Topic chips
        topics = archive.get("topics_json", [])
        if isinstance(topics, str):
            try:
                topics = _json.loads(topics)
            except (ValueError, TypeError):
                topics = []
        if topics:
            chip_row = QHBoxLayout()
            chip_row.setSpacing(4)
            for topic in topics[:5]:
                chip = QLabel(str(topic))
                chip.setStyleSheet(
                    f"background: #1C1C1E; color: {t.TEXT_SECONDARY}; "
                    f"font-size: 10px; padding: 1px 6px; border-radius: 3px;"
                )
                chip.setFixedHeight(16)
                chip_row.addWidget(chip)
            chip_row.addStretch()
            card_layout.addLayout(chip_row)

        # Stats row
        session_ids = archive.get("session_ids", [])
        if isinstance(session_ids, str):
            try:
                session_ids = _json.loads(session_ids)
            except (ValueError, TypeError):
                session_ids = []
        memory_entries = archive.get("memory_entries_json", [])
        if isinstance(memory_entries, str):
            try:
                memory_entries = _json.loads(memory_entries)
            except (ValueError, TypeError):
                memory_entries = []
        learning_records = archive.get("learning_records_json", [])
        if isinstance(learning_records, str):
            try:
                learning_records = _json.loads(learning_records)
            except (ValueError, TypeError):
                learning_records = []

        stats_parts = [f"{len(session_ids)} sessions"]
        if memory_entries:
            stats_parts.append(f"{len(memory_entries)} memories")
        if learning_records:
            stats_parts.append(f"{len(learning_records)} learnings")
        stats_label = QLabel(" | ".join(stats_parts))
        stats_label.setStyleSheet(f"color: {t.TEXT_DIM}; font-size: 11px;")
        card_layout.addWidget(stats_label)

        # Click handler
        archive_id = archive.get("archive_id")
        card.mousePressEvent = lambda _ev, aid=archive_id: self._show_archive(aid)

        return card

    def _show_archive(self, archive_id: str) -> None:
        """Load an archive detail view."""
        if not self._bank:
            return
        t = Theme

        archive = self._bank.get_archive(archive_id)
        if not archive:
            return

        import json as _json

        batch_label = archive.get("batch_label", "Unknown")
        narrative = archive.get("narrative_summary", "")
        count = archive.get("interaction_count", 0)
        avg_sent = archive.get("avg_sentiment", 0.0)
        mood = archive.get("mood_summary", "")

        topics = archive.get("topics_json", [])
        if isinstance(topics, str):
            try:
                topics = _json.loads(topics)
            except (ValueError, TypeError):
                topics = []

        session_ids = archive.get("session_ids", [])
        if isinstance(session_ids, str):
            try:
                session_ids = _json.loads(session_ids)
            except (ValueError, TypeError):
                session_ids = []

        memory_entries = archive.get("memory_entries_json", [])
        if isinstance(memory_entries, str):
            try:
                memory_entries = _json.loads(memory_entries)
            except (ValueError, TypeError):
                memory_entries = []

        learning_records = archive.get("learning_records_json", [])
        if isinstance(learning_records, str):
            try:
                learning_records = _json.loads(learning_records)
            except (ValueError, TypeError):
                learning_records = []

        self._archive_detail_header.setText(f"Summary for {batch_label}")

        # Summary section
        topics_html = " ".join(
            f'<span style="background:#1C1C1E; color:{t.TEXT_SECONDARY}; '
            f'padding:1px 6px; border-radius:3px; font-size:10px;">{tp}</span>'
            for tp in (topics or [])[:7]
        )
        summary_html = (
            f'<p style="color:{t.TEXT_PRIMARY}; font-size:13px;">{narrative}</p>'
            f'<p style="color:{t.TEXT_DIM}; font-size:11px;">Topics: {topics_html}</p>'
            f'<p style="color:{t.TEXT_DIM}; font-size:11px;">'
            f'{count} msgs | {len(session_ids)} sessions | '
            f'sentiment: {avg_sent:+.2f} | mood: {mood}</p>'
            f'<p style="color:{t.TEXT_DIM}; font-size:11px;">'
            f'Created: {len(memory_entries)} memories, {len(learning_records)} insights'
            f'{", 1 episode" if archive.get("eidos_episode_id") else ""}</p>'
        )
        self._archive_summary_text.setHtml(summary_html)

        # Full conversations
        interactions = self._bank.get_archive_interactions(archive_id)
        from datetime import datetime as _dt
        html_parts: list = []
        for row in interactions:
            ts = row.get("timestamp", 0)
            ts_str = _dt.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
            user_text = (row.get("user_input") or "").replace("<", "&lt;").replace(">", "&gt;")
            ai_text = (row.get("ai_response") or "").replace("<", "&lt;").replace(">", "&gt;")
            html_parts.append(
                f'<p><span style="color:{t.TEXT_DIM};font-size:11px;">[{ts_str}]</span> '
                f'<span style="color:{t.TEXT_PRIMARY};font-weight:bold;">You:</span> '
                f'<span style="color:{t.TEXT_SECONDARY};">{user_text}</span></p>'
            )
            html_parts.append(
                f'<p><span style="color:{t.TEXT_DIM};font-size:11px;">[{ts_str}]</span> '
                f'<span style="color:{t.ACCENT_PURPLE};font-weight:bold;">Kait:</span> '
                f'<span style="color:{t.TEXT_PRIMARY};">{ai_text}</span></p>'
            )

        self._archive_detail_text.setHtml(
            "".join(html_parts) if html_parts else "<i>No messages in this archive</i>"
        )
        self._archive_stack.setCurrentIndex(1)


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
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
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
# Icon helpers -- custom-painted icons for buttons
# ===================================================================

def _make_mic_icon(size: int = 20, color: str = "#FFFFFF") -> "QIcon":
    """Create a microphone icon."""
    if not _QT_AVAILABLE:
        return None  # type: ignore[return-value]
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    if hasattr(QPainter, "RenderHint"):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
    else:
        p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.5)
    if hasattr(Qt, "PenCapStyle"):
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    else:
        pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    s = float(size)
    cx = s / 2
    # Mic capsule (filled rounded rect)
    p.setBrush(QBrush(c))
    cw, ch = s * 0.32, s * 0.40
    p.drawRoundedRect(int(cx - cw / 2), int(s * 0.06), int(cw), int(ch), cw / 2, cw / 2)
    # U-shaped arc below capsule (unfilled)
    if hasattr(Qt, "BrushStyle"):
        p.setBrush(Qt.BrushStyle.NoBrush)
    else:
        p.setBrush(Qt.NoBrush)
    aw, ah = s * 0.54, s * 0.56
    ay = s * 0.02
    p.drawArc(int(cx - aw / 2), int(ay), int(aw), int(ah), 0, -180 * 16)
    # Stem
    stem_top = ay + ah / 2
    stem_bot = s * 0.78
    p.drawLine(int(cx), int(stem_top), int(cx), int(stem_bot))
    # Base
    bw = s * 0.30
    p.drawLine(int(cx - bw / 2), int(stem_bot), int(cx + bw / 2), int(stem_bot))
    p.end()
    return QIcon(pixmap)


def _make_volume_icon(size: int = 20, color: str = "#FFFFFF", muted: bool = False) -> "QIcon":
    """Create a speaker/volume icon. Pass *muted=True* for the muted variant."""
    if not _QT_AVAILABLE:
        return None  # type: ignore[return-value]
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    if hasattr(QPainter, "RenderHint"):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
    else:
        p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.5)
    if hasattr(Qt, "PenCapStyle"):
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    else:
        pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(QBrush(c))
    s = float(size)
    cy = s / 2
    # Speaker body + cone as single filled path
    bx, bw, bh = s * 0.10, s * 0.12, s * 0.24
    path = QPainterPath()
    path.moveTo(bx, cy - bh / 2)
    path.lineTo(bx + bw, cy - bh / 2)
    path.lineTo(s * 0.42, cy - s * 0.32)
    path.lineTo(s * 0.42, cy + s * 0.32)
    path.lineTo(bx + bw, cy + bh / 2)
    path.lineTo(bx, cy + bh / 2)
    path.closeSubpath()
    p.drawPath(path)
    # Sound waves or mute X
    if hasattr(Qt, "BrushStyle"):
        p.setBrush(Qt.BrushStyle.NoBrush)
    else:
        p.setBrush(Qt.NoBrush)
    if muted:
        mx = s * 0.56
        p.drawLine(int(mx), int(cy - s * 0.18), int(mx + s * 0.24), int(cy + s * 0.18))
        p.drawLine(int(mx), int(cy + s * 0.18), int(mx + s * 0.24), int(cy - s * 0.18))
    else:
        wx = s * 0.48
        wr1 = s * 0.12
        p.drawArc(int(wx), int(cy - wr1), int(wr1 * 2), int(wr1 * 2), 45 * 16, -90 * 16)
        wr2 = s * 0.22
        p.drawArc(int(wx), int(cy - wr2), int(wr2 * 2), int(wr2 * 2), 45 * 16, -90 * 16)
    p.end()
    return QIcon(pixmap)


def _make_sidebar_icon(size: int = 20, color: str = "#FFFFFF", collapsed: bool = False) -> "QIcon":
    """Create a sidebar toggle icon."""
    if not _QT_AVAILABLE:
        return None  # type: ignore[return-value]
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    if hasattr(QPainter, "RenderHint"):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
    else:
        p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.4)
    if hasattr(Qt, "PenCapStyle"):
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    else:
        pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    if hasattr(Qt, "BrushStyle"):
        p.setBrush(Qt.BrushStyle.NoBrush)
    else:
        p.setBrush(Qt.NoBrush)
    s = float(size)
    m = s * 0.12  # margin
    # Outer rounded rect
    p.drawRoundedRect(int(m), int(m), int(s - 2 * m), int(s - 2 * m), 3, 3)
    # Vertical divider line (sidebar edge)
    if collapsed:
        dx = s * 0.38
    else:
        dx = s * 0.58
    p.drawLine(int(dx), int(m), int(dx), int(s - m))
    p.end()
    return QIcon(pixmap)


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
        files_dropped = pyqtSignal(list)

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self._speaker_on = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Attach button
        self._attach_btn = QPushButton("+")
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
        self._input.files_dropped.connect(self.files_dropped.emit)
        layout.addWidget(self._input, stretch=1)

        # Send button
        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedWidth(82)
        self._send_btn.clicked.connect(self._on_submit)
        layout.addWidget(self._send_btn)

        # Mic button
        self._mic_btn = QPushButton()
        self._mic_btn.setObjectName("micBtn")
        self._mic_btn.setToolTip("Voice input")
        self._mic_btn.setFixedWidth(44)
        self._mic_btn.setIcon(_make_mic_icon(18))
        self._mic_btn.setIconSize(QSize(18, 18))
        self._mic_btn.clicked.connect(lambda: self.voice_requested.emit())
        layout.addWidget(self._mic_btn)

        # Speaker button
        self._speaker_btn = QPushButton()
        self._speaker_btn.setObjectName("speakerBtn")
        self._speaker_btn.setToolTip("Toggle speaker")
        self._speaker_btn.setFixedWidth(44)
        self._speaker_btn.setIcon(_make_volume_icon(18))
        self._speaker_btn.setIconSize(QSize(18, 18))
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
        self._speaker_btn.setIcon(_make_volume_icon(18, muted=not self._speaker_on))
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

    def update_placeholder(self, text: str) -> None:
        """Update placeholder text without toggling enabled state."""
        if _QT_AVAILABLE:
            self._input.setPlaceholderText(text)

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
            f"background: rgba(10, 10, 10, 0.90); "
            f"border-top: 1px solid rgba(255, 255, 255, 0.06);"
        )
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 3, 14, 3)
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
            f"color: #FFFFFF; font-size: 11px; font-weight: 600; "
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
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 rgba(10, 10, 10, 0.95), "
            "stop:0.4 rgba(18, 18, 18, 0.95), "
            "stop:0.6 rgba(14, 14, 14, 0.95), "
            "stop:1 rgba(10, 10, 10, 0.95)); "
            f"border-bottom: 1px solid rgba(255, 255, 255, 0.06);"
        )
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 14, 4)
        layout.setSpacing(12)

        # Title + subtitle
        title = QLabel("Kait")
        title.setStyleSheet(
            "color: #FFFFFF; font-size: 15px; font-weight: 700; "
            "letter-spacing: -0.3px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(title)

        subtitle = QLabel("Intelligence System")
        subtitle.setStyleSheet(
            f"color: {t.TEXT_DIM}; font-size: 10px; font-weight: 400; "
            f"letter-spacing: 0.5px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(subtitle)

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

        # Panel toggle button
        self._panel_btn = QPushButton()
        self._panel_btn.setToolTip("Toggle side panels")
        self._panel_btn.setFixedSize(28, 28)
        self._panel_btn.setIcon(_make_sidebar_icon(18, color="#FFFFFF"))
        self._panel_btn.setIconSize(QSize(18, 18))
        self._panel_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 0.08); border-radius: 6px; }"
        )
        layout.addWidget(self._panel_btn)

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
        self.setWindowTitle("Welcome to Kait")
        self.setMinimumSize(480, 400)
        self.setStyleSheet(DARK_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        header = QLabel("Welcome to Kait")
        header.setObjectName("headerLabel")
        header.setAlignment(
            Qt.AlignmentFlag.AlignCenter if hasattr(Qt, "AlignmentFlag") else Qt.AlignCenter
        )
        layout.addWidget(header)

        subtitle = QLabel("Your AI Open Source Sidekick.")
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


# Legacy no-op methods mixed into DashboardPanel for backward compat
DashboardPanel.update_evolution = lambda self, *a, **kw: None
DashboardPanel.update_resonance = lambda self, *a, **kw: None
DashboardPanel.update_bank_stats = lambda self, *a, **kw: None
DashboardPanel.update_system = lambda self, *a, **kw: None
DashboardPanel.update_services = lambda self, *a, **kw: None


# ===================================================================
# KaitMainWindow -- the main application window
# ===================================================================

class KaitMainWindow(QMainWindow if _QT_AVAILABLE else object):
    """Main window for the Kait GUI.

    Layout::

        +---------------------------------------------------------+
        | Header: [Kait]  [Tokens]  [GPU]                   |
        +----------------------+----------------------------------+
        |                      | [Skills] [Monitor] [History]     |
        |   Chat Messages      |   Tab content                    |
        |   (scrollable)       |                                  |
        +----------------------+----------------------------------+
        | Input Bar: [Attach] [Text...] [Send] [Mic] [Speaker]   |
        +---------------------------------------------------------+
        | Footer: service dots | mood | evolution                  |
        +---------------------------------------------------------+
    """

    # Word count above which a response is considered "long".
    # Long responses are routed to Monitor Activity; chat shows a summary.
    _LONG_MSG_WORDS = 150

    if _QT_AVAILABLE:
        user_message_sent = pyqtSignal(str)
        voice_requested = pyqtSignal()
        speaker_toggled = pyqtSignal(bool)
        theme_changed = pyqtSignal(str)
        attachments_ready = pyqtSignal(list)
        # Emitted with summary text when a long message was summarised.
        # Connect to TTS to speak the summary in sync.
        summary_ready = pyqtSignal(str)

    def __init__(self, parent: Any = None):
        if not _QT_AVAILABLE:
            return
        super().__init__(parent)
        self.setWindowTitle("Kait")
        self.setMinimumSize(360, 400)
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
        self._splitter = QSplitter(
            Qt.Orientation.Horizontal if hasattr(Qt, "Orientation") else Qt.Horizontal
        )
        self._splitter.setHandleWidth(2)
        splitter = self._splitter

        # LEFT: Chat panel
        left_container = QWidget()
        left_container.setMinimumWidth(320)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.chat_panel = ChatPanel()
        left_layout.addWidget(self.chat_panel, stretch=1)

        splitter.addWidget(left_container)

        # RIGHT: Vertical splitter (Tabs on top + Graph section below)
        self._right_splitter = QSplitter(
            Qt.Orientation.Vertical if hasattr(Qt, "Orientation") else Qt.Vertical
        )
        self._right_splitter.setHandleWidth(2)

        # Tab widget (System / History)
        self._tab_widget = QTabWidget()
        # Prevent tab label truncation: no eliding, expand to fill
        _elide_none = (
            Qt.TextElideMode.ElideNone
            if hasattr(Qt, "TextElideMode")
            else Qt.ElideNone
        )
        self._tab_widget.tabBar().setElideMode(_elide_none)
        self._tab_widget.tabBar().setExpanding(True)
        self._tab_widget.tabBar().setUsesScrollButtons(False)

        # System tab (unified pipeline + health + monitoring)
        self._dashboard = DashboardPanel()
        self._observatory = self._dashboard  # backward compat
        self._monitor = self._dashboard      # backward compat
        dash_scroll = QScrollArea()
        dash_scroll.setWidget(self._dashboard)
        dash_scroll.setWidgetResizable(True)
        dash_scroll.setFrameStyle(QFrame.Shape.NoFrame if hasattr(QFrame, "Shape") else QFrame.NoFrame)
        self._tab_widget.addTab(dash_scroll, "System")

        # History tab
        self._history_panel = ChatHistoryPanel()
        self._tab_widget.addTab(self._history_panel, "History")

        # Auto-refresh History tab when selected
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        self._right_splitter.addWidget(self._tab_widget)

        # Graph section (Kait Brain + BLERBZ OS Map visual graphs)
        self._graph_section = None
        self._kait_brain_panel = None
        self._github_mindmap_panel = None
        if _VAULT_VIEWER_AVAILABLE:
            try:
                self._graph_section = VaultGraphSection()
                self._right_splitter.addWidget(self._graph_section)
            except Exception:
                pass  # Graceful degradation if graph section fails

        # Right splitter proportions: tabs=50%, graph=50%
        self._right_splitter.setSizes([400, 400])
        self._right_splitter.setStretchFactor(0, 1)
        self._right_splitter.setStretchFactor(1, 1)

        # Graph reopen tab (visible only when graph section is fully collapsed)
        self._graph_reopen_tab = QWidget()
        self._graph_reopen_tab.setFixedHeight(28)
        self._graph_reopen_tab.setCursor(
            Qt.CursorShape.PointingHandCursor
            if hasattr(Qt, "CursorShape")
            else Qt.PointingHandCursor
        )
        self._graph_reopen_tab.setStyleSheet(
            "background: #0A0A0A; border-top: 1px solid #2C2C2E;"
        )
        _reopen_layout = QHBoxLayout(self._graph_reopen_tab)
        _reopen_layout.setContentsMargins(12, 4, 12, 4)
        _reopen_icon = QLabel("\u25B2")
        _reopen_icon.setStyleSheet(
            "color: #8E8E93; font-size: 9px; background: transparent;"
        )
        _reopen_label = QLabel("Obsidian Graph")
        _reopen_label.setStyleSheet(
            "color: #8E8E93; font-size: 11px; font-weight: 600;"
            " background: transparent;"
        )
        _reopen_layout.addWidget(_reopen_icon)
        _reopen_layout.addWidget(_reopen_label)
        _reopen_layout.addStretch()
        self._graph_reopen_tab.hide()
        self._graph_reopen_tab.mousePressEvent = (
            lambda _evt: self._restore_graph_section()
        )

        # Detect when graph section is collapsed via splitter drag
        self._right_splitter.splitterMoved.connect(
            self._on_right_splitter_moved
        )

        # Wrap right splitter + reopen tab in a container
        self._right_container = QWidget()
        _rc_layout = QVBoxLayout(self._right_container)
        _rc_layout.setContentsMargins(0, 0, 0, 0)
        _rc_layout.setSpacing(0)
        _rc_layout.addWidget(self._right_splitter, stretch=1)
        _rc_layout.addWidget(self._graph_reopen_tab)

        self._right_container.setMinimumWidth(300)
        splitter.addWidget(self._right_container)

        # Splitter proportions: chat=60%, tabs=40%
        splitter.setSizes([600, 400])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root_layout.addWidget(splitter, stretch=1)

        # Wire panel toggle button
        self._header_bar._panel_btn.clicked.connect(self._toggle_side_panels)
        self._saved_splitter_sizes: list = []

        # --- Input bar ---
        self._input_bar = InputBar()
        self._input_bar.message_submitted.connect(self._on_send)
        self._input_bar.voice_requested.connect(self._on_voice)
        self._input_bar.attach_requested.connect(self._on_attach)
        self._input_bar.files_dropped.connect(self._on_files_dropped)
        self._input_bar.speaker_toggled.connect(self.speaker_toggled.emit)
        root_layout.addWidget(self._input_bar)

        # --- Footer status bar ---
        self._footer_bar = FooterStatusBar()
        root_layout.addWidget(self._footer_bar)

        # --- Legacy compatibility attributes ---
        self.avatar_widget = QWidget() if _QT_AVAILABLE else None
        self.avatar_customize = AvatarCustomizePanel()
        self._file_processor: Any = None
        self._pending_attachments: List[Any] = []
        self._generating: bool = False

        # Keyboard shortcuts
        self._setup_shortcuts()

    # ------------------------------------------------------------------
    # Side-panel toggle
    # ------------------------------------------------------------------

    def _toggle_side_panels(self) -> None:
        """Hide or show the right-side panel."""
        target = getattr(self, "_right_container", self._right_splitter)
        if target.isVisible():
            self._saved_splitter_sizes = self._splitter.sizes()
            target.hide()
            self._header_bar._panel_btn.setIcon(_make_sidebar_icon(18, color="#FFFFFF", collapsed=True))
        else:
            target.show()
            if self._saved_splitter_sizes:
                self._splitter.setSizes(self._saved_splitter_sizes)
            self._header_bar._panel_btn.setIcon(_make_sidebar_icon(18, color="#FFFFFF", collapsed=False))

    # ------------------------------------------------------------------
    # Graph section collapse / restore
    # ------------------------------------------------------------------

    def _on_right_splitter_moved(self, pos: int, index: int) -> None:
        """Show or hide the graph reopen tab based on graph section height."""
        sizes = self._right_splitter.sizes()
        # Graph section is the second widget (index 1)
        graph_collapsed = len(sizes) > 1 and sizes[1] <= 2
        self._graph_reopen_tab.setVisible(graph_collapsed)

    def _restore_graph_section(self) -> None:
        """Restore the graph section to 50% of the right panel height."""
        total = sum(self._right_splitter.sizes()) or 800
        half = total // 2
        self._right_splitter.setSizes([half, total - half])
        self._graph_reopen_tab.hide()

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

        panel_action = QAction("Toggle Panels", self)
        panel_action.setShortcut(QKeySequence("Ctrl+B"))
        panel_action.triggered.connect(self._toggle_side_panels)
        self.addAction(panel_action)

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
            self.attachments_ready.emit(paths)

    def _on_files_dropped(self, paths: list) -> None:
        """Handle files dropped onto the input field via drag & drop."""
        if not _QT_AVAILABLE or self._generating:
            return
        if paths:
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
        """Finalise streaming. Long messages go to Monitor Activity; chat gets a summary."""
        # Peek at accumulated tokens before finalising
        full_text = "".join(self.chat_panel._stream_tokens)
        words = full_text.split()

        if len(words) > self._LONG_MSG_WORDS:
            summary = self._extract_summary(full_text)
            # Show full response in Monitor Activity tab
            self._monitor.append_feed_entry("[Full Response]")
            self._monitor.append_feed_entry(full_text)
            # Chat bubble shows only the summary
            self.chat_panel.finish_streaming(display_text=summary)
            # Signal for TTS to speak the summary
            self.summary_ready.emit(summary)
            return summary

        return self.chat_panel.finish_streaming()

    @staticmethod
    def _extract_summary(text: str, max_sentences: int = 3) -> str:
        """Extract first few sentences as a short chat summary."""
        import re
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        summary = " ".join(sentences[:max_sentences])
        if len(sentences) > max_sentences:
            summary += " ..."
        return summary

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

    def _on_tab_changed(self, index: int) -> None:
        """Auto-refresh panels when their tab is selected."""
        widget = self._tab_widget.widget(index)
        if widget is self._history_panel:
            self._history_panel.refresh()

    # --- Archive worker integration ---

    def start_archive_worker(self, bank) -> None:
        """Initialize and start the archive worker with a 5-minute timer."""
        from lib.sidekick.archive_worker import ArchiveWorker

        self._archive_worker = ArchiveWorker(bank)

        self._archive_timer = QTimer(self)
        self._archive_timer.setInterval(300_000)  # 5 minutes
        self._archive_timer.timeout.connect(self._run_archive_check)
        self._archive_timer.start()

        # Initial check after 30s to let UI settle
        QTimer.singleShot(30_000, self._run_archive_check)

    def _run_archive_check(self) -> None:
        """Run an archive cycle and refresh the history panel if needed."""
        if not hasattr(self, "_archive_worker") or self._archive_worker is None:
            return
        try:
            result = self._archive_worker.run_archive_cycle()
            if result.get("batches_created", 0) > 0:
                self._history_panel.refresh()
        except Exception:
            pass  # Archive is best-effort, never crash the UI

    @property
    def observatory(self) -> "DashboardPanel":
        return self._observatory

    @property
    def monitor(self) -> "DashboardPanel":
        return self._monitor

    @property
    def dashboard(self) -> "DashboardPanel":
        return self._dashboard

    @property
    def history_panel(self) -> "ChatHistoryPanel":
        return self._history_panel

    @property
    def header_bar(self) -> "HeaderStatusBar":
        return self._header_bar

    @property
    def input_bar(self) -> "InputBar":
        return self._input_bar

    @property
    def footer_bar(self) -> "FooterStatusBar":
        return self._footer_bar

    @property
    def kait_brain_panel(self) -> Any:
        """Kait Brain vault viewer (None -- legacy, now in graph section)."""
        return self._kait_brain_panel

    @property
    def github_mindmap_panel(self) -> Any:
        """BLERBZ OS Map vault viewer (None -- legacy, now in graph section)."""
        return self._github_mindmap_panel

    @property
    def graph_section(self) -> Any:
        """Obsidian graph section (None if vault_viewer unavailable)."""
        return self._graph_section

    def trigger_vault_refresh(self) -> None:
        """Trigger refresh on all vault viewer panels (for Kait autonomous hooks)."""
        if self._kait_brain_panel is not None:
            self._kait_brain_panel.refresh()
        if self._github_mindmap_panel is not None:
            self._github_mindmap_panel.refresh()
