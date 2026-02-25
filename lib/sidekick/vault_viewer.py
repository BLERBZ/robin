"""Kait -- Obsidian Vault Viewer for the Kait GUI.

Embeds read-only views of Obsidian vaults into the PyQt6 GUI as tabbed panels.
Supports two vault views:

    1. Kait Brain  -- Aggregated view of Kait-OS-Sidekick vault
       (Knowledge, Memory, Skills, MOCs, Canvases)
    2. BLERBZ OS Map -- BLERBZ-OS-GitMap vault
       (Projects, Areas, Resources, Visuals)

Features:
    - Real-time file watching via QFileSystemWatcher
    - Markdown rendering via QTextBrowser.setMarkdown()
    - YAML frontmatter display as metadata badges
    - Search/filter across all vault notes
    - Mermaid diagram code block highlighting
    - Obsidian Canvas (.canvas) JSON summary view
    - Graceful error handling for missing/offline vaults
    - DOMPurify-equivalent sanitisation (HTML entity escaping)
    - Virtual scrolling via lazy-loaded file lists

Dependencies:
    PyQt6 (already in gui optional group)
    No additional packages required.
"""

from __future__ import annotations

import json
import os
import re
import html
import time
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Qt imports -- mirrors ui_module.py fallback pattern
# ---------------------------------------------------------------------------
_QT_AVAILABLE = False
try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
        QLineEdit, QListWidget, QListWidgetItem, QTextBrowser,
        QFrame, QScrollArea, QSizePolicy, QPushButton, QStackedWidget,
        QTabWidget,
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QFileSystemWatcher, pyqtSignal, QSize,
    )
    from PyQt6.QtGui import (
        QFont, QColor, QIcon, QPixmap, QTextOption, QPainter, QPen, QBrush,
    )
    _QT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtWidgets import (  # type: ignore[no-redef]
            QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
            QLineEdit, QListWidget, QListWidgetItem, QTextBrowser,
            QFrame, QScrollArea, QSizePolicy, QPushButton, QStackedWidget,
            QTabWidget,
        )
        from PyQt5.QtCore import (  # type: ignore[no-redef]
            Qt, QTimer, QFileSystemWatcher, pyqtSignal, QSize,
        )
        from PyQt5.QtGui import (  # type: ignore[no-redef]
            QFont, QColor, QIcon, QPixmap, QTextOption, QPainter, QPen, QBrush,
        )
        _QT_AVAILABLE = True
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default vault paths (macOS) -- overridden by env vars or tuneables
_DEFAULT_KAIT_VAULT = os.path.expanduser("~/Obsidian/Kait-OS-Sidekick")
_DEFAULT_GITMAP_VAULT = os.path.expanduser("~/Obsidian/BLERBZ-OS-GitMap")

# File extensions to index
_MD_EXTENSIONS = {".md"}
_CANVAS_EXTENSIONS = {".canvas"}
_ALL_EXTENSIONS = _MD_EXTENSIONS | _CANVAS_EXTENSIONS

# Directories to skip
_SKIP_DIRS = {".obsidian", ".git", ".trash", "__pycache__", "node_modules"}

# Debounce interval for file watcher (ms)
_WATCHER_DEBOUNCE_MS = 2000

# Max files to display before virtualisation kicks in
_MAX_DISPLAY_FILES = 500

# Graph visualisation constants
_GRAPH_MAX_NODES = 200
_GRAPH_SIM_ITERATIONS = 300
_GRAPH_SIM_PER_TICK = 3
_GRAPH_BUILD_DELAY_MS = 3000  # Delay before building graph to let GUI settle

# YAML frontmatter regex
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_vault_path(env_key: str, default: str) -> str:
    """Resolve vault path from environment or default."""
    raw = os.environ.get(env_key, "").strip()
    if raw:
        return os.path.expanduser(raw)
    return default


def _sanitise_html(text: str) -> str:
    """Escape HTML entities to prevent XSS in rendered content."""
    return html.escape(text, quote=True)


def _parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Extract YAML frontmatter and body from Markdown content.

    Returns (metadata_dict, body_text).  Metadata is a flat dict of
    key: value strings (no full YAML parsing to avoid deps).
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    raw_yaml = match.group(1)
    body = content[match.end():]
    metadata: Dict[str, str] = {}

    for line in raw_yaml.splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                metadata[key] = value

    return metadata, body


def _scan_vault(vault_path: str) -> List[Dict[str, Any]]:
    """Scan a vault directory and return a list of file info dicts.

    Each dict has: path, name, rel_path, extension, size, mtime.
    Returns empty list if vault path doesn't exist.
    """
    vault = Path(vault_path)
    if not vault.is_dir():
        return []

    files: List[Dict[str, Any]] = []
    count = 0

    for root, dirs, filenames in os.walk(vault):
        # Skip hidden/system directories
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _ALL_EXTENSIONS:
                continue

            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, vault_path)

            try:
                stat = os.stat(fpath)
                files.append({
                    "path": fpath,
                    "name": fname,
                    "rel_path": rel,
                    "extension": ext,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
            except OSError:
                continue

            count += 1
            if count >= 10000:  # Safety cap for very large vaults
                break

        if count >= 10000:
            break

    # Sort by relative path for consistent display
    files.sort(key=lambda f: f["rel_path"])
    return files


def _extract_wiki_links(content: str) -> List[str]:
    """Extract [[wiki-link]] targets from Markdown content."""
    return [
        m.group(1).strip()
        for m in re.finditer(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]", content)
    ]


def _build_vault_graph(
    vault_path: str,
) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int]]]:
    """Build a node/edge graph from vault wiki-link connections.

    Returns (nodes_list, edges_list) where each node is a dict with
    'name', 'connections', 'path', and 'rel_path' keys, and edges are
    (idx_a, idx_b) tuples.
    """
    files = _scan_vault(vault_path)
    if not files:
        return [], []

    stem_to_idx: Dict[str, int] = {}
    node_names: List[str] = []
    node_paths: List[str] = []
    node_rel_paths: List[str] = []

    for f in files:
        stem = os.path.splitext(f["name"])[0]
        if stem not in stem_to_idx:
            stem_to_idx[stem] = len(node_names)
            node_names.append(stem)
            node_paths.append(f["path"])
            node_rel_paths.append(f["rel_path"])

    if len(node_names) > _GRAPH_MAX_NODES:
        node_names = node_names[:_GRAPH_MAX_NODES]
        node_paths = node_paths[:_GRAPH_MAX_NODES]
        node_rel_paths = node_rel_paths[:_GRAPH_MAX_NODES]
        stem_to_idx = {n: i for i, n in enumerate(node_names)}

    connections = [0] * len(node_names)
    edges: List[Tuple[int, int]] = []
    seen_edges: set = set()

    for f in files:
        stem = os.path.splitext(f["name"])[0]
        if stem not in stem_to_idx:
            continue

        try:
            with open(f["path"], "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read(50_000)
        except OSError:
            continue

        links = _extract_wiki_links(content)
        src_idx = stem_to_idx[stem]

        for target in links:
            if target in stem_to_idx and target != stem:
                tgt_idx = stem_to_idx[target]
                edge_key = (min(src_idx, tgt_idx), max(src_idx, tgt_idx))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append(edge_key)
                    connections[src_idx] += 1
                    connections[tgt_idx] += 1

    nodes = [
        {
            "name": name,
            "connections": connections[i],
            "path": node_paths[i],
            "rel_path": node_rel_paths[i],
        }
        for i, name in enumerate(node_names)
    ]
    return nodes, edges


def _render_canvas_summary(content: str) -> str:
    """Render an Obsidian .canvas file as a Markdown summary."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return "*Unable to parse canvas file.*"

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    lines = [f"# Canvas Overview\n"]
    lines.append(f"**Nodes:** {len(nodes)} | **Connections:** {len(edges)}\n")

    if nodes:
        lines.append("## Nodes\n")
        for i, node in enumerate(nodes[:50]):  # Cap at 50 nodes
            ntype = node.get("type", "unknown")
            label = node.get("text", node.get("file", "Untitled"))
            if isinstance(label, str):
                label = label[:80]
            lines.append(f"- **[{ntype}]** {label}")
        if len(nodes) > 50:
            lines.append(f"\n*... and {len(nodes) - 50} more nodes*")

    if edges:
        lines.append("\n## Connections\n")
        for i, edge in enumerate(edges[:30]):
            from_id = edge.get("fromNode", "?")[:12]
            to_id = edge.get("toNode", "?")[:12]
            lines.append(f"- {from_id} → {to_id}")
        if len(edges) > 30:
            lines.append(f"\n*... and {len(edges) - 30} more connections*")

    return "\n".join(lines)


def _build_metadata_badges(metadata: Dict[str, str]) -> str:
    """Build HTML badges for frontmatter metadata."""
    if not metadata:
        return ""

    badge_style = (
        "display:inline-block; padding:2px 8px; margin:2px 4px 2px 0; "
        "border-radius:10px; font-size:11px; "
    )

    badges = []
    for key, value in metadata.items():
        if key in ("tags", "aliases"):
            # Parse comma-separated or bracket-enclosed lists
            items = value.strip("[]").split(",")
            for item in items:
                item = item.strip().strip('"').strip("'")
                if item:
                    colour = "#30D158" if key == "tags" else "#8E8E93"
                    badges.append(
                        f'<span style="{badge_style}'
                        f'background:rgba({_hex_to_rgb(colour)},0.15);'
                        f'color:{colour};">'
                        f'{_sanitise_html(item)}</span>'
                    )
        elif key == "status":
            colour = "#30D158" if value == "active" else "#FFD60A"
            badges.append(
                f'<span style="{badge_style}'
                f'background:rgba({_hex_to_rgb(colour)},0.15);'
                f'color:{colour};">'
                f'{_sanitise_html(key)}: {_sanitise_html(value)}</span>'
            )
        elif key in ("created", "synced", "source"):
            badges.append(
                f'<span style="{badge_style}'
                f'background:rgba(142,142,147,0.12);'
                f'color:#8E8E93;">'
                f'{_sanitise_html(key)}: {_sanitise_html(value)}</span>'
            )

    if not badges:
        return ""
    return '<div style="margin-bottom:12px;">' + "".join(badges) + "</div>"


def _hex_to_rgb(hex_color: str) -> str:
    """Convert #RRGGBB to 'R,G,B' string."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "255,255,255"
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"{r},{g},{b}"


def _get_subdirs_to_watch(vault_path: str) -> List[str]:
    """Get all sub-directories of a vault for the file watcher."""
    vault = Path(vault_path)
    if not vault.is_dir():
        return []

    dirs = [str(vault)]
    for root, subdirs, _ in os.walk(vault):
        subdirs[:] = [d for d in subdirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for d in subdirs:
            dirs.append(os.path.join(root, d))
    return dirs


# ===================================================================
# VaultNoteViewer -- renders a single note
# ===================================================================

if _QT_AVAILABLE:

    class VaultNoteViewer(QTextBrowser):
        """Read-only Markdown/Canvas viewer with metadata badges.

        Uses QTextBrowser.setMarkdown() for rendering.  Sanitises all
        injected HTML.  Shows frontmatter as coloured badges above content.
        """

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.setOpenExternalLinks(True)
            self.setFrameStyle(
                QFrame.Shape.NoFrame if hasattr(QFrame, "Shape") else QFrame.NoFrame
            )
            self.setStyleSheet("""
                QTextBrowser {
                    background-color: #0A0A0A;
                    color: #FFFFFF;
                    border: none;
                    padding: 16px;
                    font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', -apple-system, sans-serif;
                    font-size: 14px;
                    selection-background-color: rgba(255, 255, 255, 0.20);
                }
                QTextBrowser a {
                    color: #30D158;
                }
            """)
            self._current_path: str = ""

        def show_note(self, file_info: Dict[str, Any]) -> None:
            """Load and render a vault note."""
            fpath = file_info.get("path", "")
            ext = file_info.get("extension", "")
            self._current_path = fpath

            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError as exc:
                self.setHtml(
                    f'<p style="color:#FF453A;">Error reading file: '
                    f'{_sanitise_html(str(exc))}</p>'
                )
                return

            if ext == ".canvas":
                md_content = _render_canvas_summary(content)
                self.setMarkdown(md_content)
                return

            # Parse frontmatter
            metadata, body = _parse_frontmatter(content)

            # Build badges HTML
            badges_html = _build_metadata_badges(metadata)

            # Convert Obsidian wiki-links [[target]] → readable text
            body = re.sub(
                r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]",
                lambda m: m.group(2) if m.group(2) else m.group(1),
                body,
            )

            # Use setMarkdown for the body, but prepend badges as HTML
            if badges_html:
                # Render markdown to get the body HTML, then combine
                self.setMarkdown(body)
                body_html = self.toHtml()
                # Insert badges after <body> tag
                body_html = body_html.replace(
                    "<body",
                    f"<body><div>{badges_html}</div><hr style='border:1px solid #2C2C2E;margin:8px 0;'/><div",
                    1,
                )
                # Close the extra div
                if "</body>" in body_html:
                    body_html = body_html.replace("</body>", "</div></body>", 1)
                self.setHtml(body_html)
            else:
                self.setMarkdown(body)

        def show_placeholder(self, message: str = "Select a note to view") -> None:
            """Show a placeholder message."""
            self.setHtml(
                f'<div style="text-align:center;padding:60px 20px;'
                f'color:#8E8E93;font-size:15px;">'
                f'<p style="font-size:28px;margin-bottom:12px;">📖</p>'
                f'<p>{_sanitise_html(message)}</p>'
                f'</div>'
            )

        def show_error(self, message: str) -> None:
            """Show an error state."""
            self.setHtml(
                f'<div style="text-align:center;padding:60px 20px;'
                f'color:#FF453A;font-size:14px;">'
                f'<p style="font-size:28px;margin-bottom:12px;">&#9888;</p>'
                f'<p>{_sanitise_html(message)}</p>'
                f'<p style="color:#8E8E93;margin-top:8px;font-size:12px;">'
                f'Check vault path in .env or tuneables.json</p>'
                f'</div>'
            )

        def show_syncing(self) -> None:
            """Show a syncing/loading indicator."""
            self.setHtml(
                '<div style="text-align:center;padding:60px 20px;'
                'color:#8E8E93;font-size:14px;">'
                '<p style="font-size:24px;margin-bottom:12px;">&#8635;</p>'
                '<p>Syncing vault...</p>'
                '</div>'
            )

    # ===================================================================
    # VaultFileList -- searchable file list with categories
    # ===================================================================

    class VaultFileList(QWidget):
        """Searchable list of vault files with category grouping."""

        file_selected = pyqtSignal(dict)  # Emits file_info dict

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self._files: List[Dict[str, Any]] = []
            self._filtered: List[Dict[str, Any]] = []

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Search bar
            self._search = QLineEdit()
            self._search.setPlaceholderText("Search notes...")
            self._search.setClearButtonEnabled(True)
            self._search.setStyleSheet("""
                QLineEdit {
                    background: rgba(255,255,255,0.04);
                    color: #FFFFFF;
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 12px;
                    margin: 6px;
                }
                QLineEdit:focus {
                    border: 1px solid rgba(255,255,255,0.18);
                }
            """)
            self._search.textChanged.connect(self._on_search)
            layout.addWidget(self._search)

            # File count label
            self._count_label = QLabel("0 notes")
            self._count_label.setStyleSheet(
                "color: #48484A; font-size: 11px; padding: 0 8px 4px 8px;"
            )
            layout.addWidget(self._count_label)

            # File list
            self._list = QListWidget()
            self._list.setStyleSheet("""
                QListWidget {
                    background: transparent;
                    border: none;
                    outline: none;
                    font-size: 12px;
                }
                QListWidget::item {
                    color: #C7C7CC;
                    padding: 6px 12px;
                    border: none;
                    border-bottom: 1px solid rgba(255,255,255,0.03);
                }
                QListWidget::item:selected {
                    background: rgba(255,255,255,0.06);
                    color: #FFFFFF;
                }
                QListWidget::item:hover:!selected {
                    background: rgba(255,255,255,0.03);
                }
            """)
            self._list.currentRowChanged.connect(self._on_item_selected)
            layout.addWidget(self._list, stretch=1)

        def set_files(self, files: List[Dict[str, Any]]) -> None:
            """Set the full file list and refresh display."""
            self._files = files
            self._apply_filter()

        def refresh_file(self, file_path: str) -> None:
            """Update a single file entry if it exists in the list."""
            for i, f in enumerate(self._files):
                if f["path"] == file_path:
                    try:
                        stat = os.stat(file_path)
                        f["size"] = stat.st_size
                        f["mtime"] = stat.st_mtime
                    except OSError:
                        pass
                    break

        def _apply_filter(self) -> None:
            """Apply current search filter and refresh the list widget."""
            query = self._search.text().strip().lower()
            if query:
                self._filtered = [
                    f for f in self._files
                    if query in f["name"].lower() or query in f["rel_path"].lower()
                ]
            else:
                self._filtered = list(self._files)

            # Cap display for performance
            display = self._filtered[:_MAX_DISPLAY_FILES]

            self._list.blockSignals(True)
            self._list.clear()

            for f in display:
                icon = "📝" if f["extension"] == ".md" else "🎨"
                # Show folder path as subtle prefix
                folder = os.path.dirname(f["rel_path"])
                if folder:
                    text = f"{icon}  {folder}/{f['name']}"
                else:
                    text = f"{icon}  {f['name']}"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, f)
                self._list.addItem(item)

            self._list.blockSignals(False)

            total = len(self._filtered)
            shown = len(display)
            if total > shown:
                self._count_label.setText(
                    f"{shown} of {total} notes (filter to see more)"
                )
            else:
                self._count_label.setText(f"{total} notes")

        def _on_search(self, _text: str) -> None:
            self._apply_filter()

        def _on_item_selected(self, row: int) -> None:
            if row < 0:
                return
            item = self._list.item(row)
            if item is None:
                return
            file_info = item.data(Qt.ItemDataRole.UserRole)
            if file_info:
                self.file_selected.emit(file_info)

    # ===================================================================
    # VaultViewerPanel -- main vault tab widget
    # ===================================================================

    class VaultViewerPanel(QWidget):
        """Main vault viewer panel combining file list + note viewer.

        Provides real-time file watching, search/filter, and
        Markdown rendering for Obsidian vault contents.

        Args:
            vault_path: Path to the Obsidian vault directory.
            title: Display title for the vault view.
            parent: Parent Qt widget.
        """

        # Emitted when vault content changes (for Kait autonomous hooks)
        vault_updated = pyqtSignal(str)  # vault_path

        def __init__(
            self,
            vault_path: str,
            title: str = "Vault",
            parent: Optional[QWidget] = None,
        ):
            super().__init__(parent)
            self._vault_path = vault_path
            self._title = title
            self._files: List[Dict[str, Any]] = []
            self._watcher: Optional[QFileSystemWatcher] = None
            self._debounce_timer: Optional[QTimer] = None
            self._last_scan_time: float = 0.0
            self._is_online: bool = False

            self._setup_ui()
            self._setup_watcher()

            # Initial scan (deferred to avoid blocking __init__)
            QTimer.singleShot(100, self._initial_scan)

        def _setup_ui(self) -> None:
            """Build the panel UI."""
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Header with title + status
            header = QWidget()
            header.setStyleSheet("background: #0A0A0A; border-bottom: 1px solid #2C2C2E;")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(12, 8, 12, 8)

            title_label = QLabel(self._title)
            title_label.setStyleSheet(
                "color: #FFFFFF; font-size: 13px; font-weight: 600;"
            )
            header_layout.addWidget(title_label)

            header_layout.addStretch()

            self._status_label = QLabel("Offline")
            self._status_label.setStyleSheet(
                "color: #FF453A; font-size: 11px;"
            )
            header_layout.addWidget(self._status_label)

            # Refresh button
            self._refresh_btn = QPushButton("↻")
            self._refresh_btn.setFixedSize(24, 24)
            self._refresh_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #8E8E93;
                    border: none;
                    font-size: 14px;
                    border-radius: 12px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.06);
                    color: #FFFFFF;
                }
            """)
            self._refresh_btn.clicked.connect(self.refresh)
            header_layout.addWidget(self._refresh_btn)

            layout.addWidget(header)

            # Content area: splitter (file list | note viewer)
            self._content_splitter = QSplitter(
                Qt.Orientation.Vertical if hasattr(Qt, "Orientation")
                else Qt.Vertical
            )
            self._content_splitter.setHandleWidth(2)

            # File list (top)
            self._file_list = VaultFileList()
            self._file_list.file_selected.connect(self._on_file_selected)
            self._content_splitter.addWidget(self._file_list)

            # Note viewer (bottom)
            self._note_viewer = VaultNoteViewer()
            self._note_viewer.show_placeholder()
            self._content_splitter.addWidget(self._note_viewer)

            # Splitter proportions: list=35%, viewer=65%
            self._content_splitter.setSizes([200, 400])
            self._content_splitter.setStretchFactor(0, 1)
            self._content_splitter.setStretchFactor(1, 2)

            layout.addWidget(self._content_splitter, stretch=1)

        def _setup_watcher(self) -> None:
            """Set up QFileSystemWatcher for real-time vault updates."""
            self._watcher = QFileSystemWatcher(self)
            self._watcher.directoryChanged.connect(self._on_directory_changed)
            self._watcher.fileChanged.connect(self._on_file_changed)

            # Debounce timer to avoid rapid re-scans
            self._debounce_timer = QTimer(self)
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.setInterval(_WATCHER_DEBOUNCE_MS)
            self._debounce_timer.timeout.connect(self._debounced_refresh)

        def _initial_scan(self) -> None:
            """Perform initial vault scan."""
            self._note_viewer.show_syncing()
            self.refresh()

        def refresh(self) -> None:
            """Re-scan the vault and update the file list."""
            vault = Path(self._vault_path)

            if not vault.is_dir():
                self._is_online = False
                self._status_label.setText("Vault not found")
                self._status_label.setStyleSheet("color: #FF453A; font-size: 11px;")
                self._file_list.set_files([])
                self._note_viewer.show_error(
                    f"Vault not found at:\n{self._vault_path}"
                )
                return

            self._files = _scan_vault(self._vault_path)
            self._is_online = True
            self._last_scan_time = time.time()

            # Update status
            self._status_label.setText(f"Live ({len(self._files)} notes)")
            self._status_label.setStyleSheet("color: #30D158; font-size: 11px;")

            # Update file list
            self._file_list.set_files(self._files)

            # Update watcher paths
            if self._watcher is not None:
                # Remove old paths
                old_dirs = self._watcher.directories()
                if old_dirs:
                    self._watcher.removePaths(old_dirs)
                old_files = self._watcher.files()
                if old_files:
                    self._watcher.removePaths(old_files)

                # Add new paths
                dirs = _get_subdirs_to_watch(self._vault_path)
                if dirs:
                    self._watcher.addPaths(dirs)

            # If no note selected, show placeholder
            if not self._note_viewer._current_path:
                self._note_viewer.show_placeholder(
                    f"{len(self._files)} notes in {self._title}"
                )

            # Emit update signal for Kait hooks
            self.vault_updated.emit(self._vault_path)

        def _on_directory_changed(self, _path: str) -> None:
            """Handle directory change (file added/removed)."""
            if self._debounce_timer is not None:
                self._debounce_timer.start()

        def _on_file_changed(self, path: str) -> None:
            """Handle individual file change."""
            # Refresh the file in the list
            self._file_list.refresh_file(path)

            # If this file is currently displayed, re-render it
            if path == self._note_viewer._current_path:
                for f in self._files:
                    if f["path"] == path:
                        self._note_viewer.show_note(f)
                        break

            if self._debounce_timer is not None:
                self._debounce_timer.start()

        def _debounced_refresh(self) -> None:
            """Debounced refresh after file system changes."""
            self.refresh()

        def _on_file_selected(self, file_info: Dict[str, Any]) -> None:
            """Handle file selection from the list."""
            self._note_viewer.show_note(file_info)

        @property
        def vault_path(self) -> str:
            return self._vault_path

        @property
        def is_online(self) -> bool:
            return self._is_online

        @property
        def file_count(self) -> int:
            return len(self._files)

    # ===================================================================
    # Factory functions for the two vault tabs
    # ===================================================================

    def create_kait_brain_panel(
        vault_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> VaultViewerPanel:
        """Create the Kait Brain vault viewer panel.

        Shows aggregated content from Kait-OS-Sidekick vault:
        Knowledge, Memory, Skills, MOCs, Canvases.
        """
        path = vault_path or _resolve_vault_path(
            "KAIT_VAULT_BRAIN_PATH", _DEFAULT_KAIT_VAULT
        )
        return VaultViewerPanel(
            vault_path=path,
            title="Kait Brain",
            parent=parent,
        )

    def create_github_mindmap_panel(
        vault_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> VaultViewerPanel:
        """Create the BLERBZ OS Map vault viewer panel.

        Shows content from BLERBZ-OS-GitMap vault:
        Projects, Areas, Resources, Visuals.
        """
        path = vault_path or _resolve_vault_path(
            "KAIT_VAULT_GITMAP_PATH", _DEFAULT_GITMAP_VAULT
        )
        return VaultViewerPanel(
            vault_path=path,
            title="BLERBZ OS Map",
            parent=parent,
        )

    # ===================================================================
    # VaultGraphWidget -- force-directed graph with labels & interaction
    # ===================================================================

    class VaultGraphWidget(QWidget):
        """Interactive force-directed graph of Obsidian vault connections.

        Features:
        - Node labels that appear on hover and for high-connection nodes
        - Click a node to open its .md file in the note viewer panel
        - Hover tooltip showing name + connection count + relative path
        - Glow effect on hovered/selected nodes
        - Edge opacity proportional to connected node importance
        - Stats overlay (node count, edge count, vault status)
        - Pan (drag) and zoom (scroll wheel) interaction
        - Double-click to open file in system default editor
        """

        # Signal emitted when a node is clicked: (file_path, file_name)
        node_clicked = pyqtSignal(str, str)

        def __init__(
            self,
            vault_path: str,
            title: str = "Graph",
            parent: Optional[QWidget] = None,
        ):
            super().__init__(parent)
            self._vault_path = vault_path
            self._title = title
            self._nodes: List[Dict[str, Any]] = []
            self._edges: List[Tuple[int, int]] = []
            self._is_online: bool = False

            # View transform
            self._offset_x: float = 0.0
            self._offset_y: float = 0.0
            self._zoom: float = 1.0
            self._dragging: bool = False
            self._drag_moved: bool = False
            self._last_mouse_pos: Any = None

            # Hover / selection state
            self._hovered_idx: int = -1
            self._selected_idx: int = -1

            # Simulation state
            self._sim_step: int = 0

            # Pixmap cache to avoid expensive repaints during resize
            self._cached_pixmap: Optional["QPixmap"] = None
            self._cache_dirty: bool = True
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.setInterval(150)
            self._resize_timer.timeout.connect(self._on_resize_settled)
            self._resizing: bool = False

            self._needs_initial_fit: bool = False

            self.setMinimumHeight(180)
            self.setMouseTracking(True)
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if hasattr(Qt, "CursorShape")
                else Qt.OpenHandCursor
            )

            # Simulation timer (~60 fps)
            self._sim_timer = QTimer(self)
            self._sim_timer.setInterval(16)
            self._sim_timer.timeout.connect(self._step_simulation)

            # Eager build -- scan vault synchronously so graph is ready
            # before the GUI window is shown (avoids "Vault not found" flash).
            # Only the force-simulation animation is deferred.
            self._build_graph(defer_sim=True)

        # -- Resize debounce / cache management --------------------------

        def _invalidate_cache(self) -> None:
            """Mark the pixmap cache as dirty so next paint re-renders."""
            self._cache_dirty = True

        def resizeEvent(self, event: Any) -> None:
            """Debounce resize: stretch cached pixmap until resize settles."""
            super().resizeEvent(event)
            self._resizing = True
            self._resize_timer.start()
            self.update()  # fast blit of stretched cache

        def _on_resize_settled(self) -> None:
            """Resize finished — do a full re-render."""
            self._resizing = False
            if self._needs_initial_fit:
                # First real layout — re-fit graph to actual viewport size.
                self._needs_initial_fit = False
                self._fit_to_view()
            self._invalidate_cache()
            self.update()

        # -- Graph construction ------------------------------------------

        def _build_graph(self, defer_sim: bool = False) -> None:
            """Scan vault and build the graph.

            Args:
                defer_sim: When True, delay starting the force-simulation
                    timer so it runs after the GUI event loop is active.
                    Used during __init__ to load vault data eagerly while
                    keeping the animation smooth.
            """
            vault = Path(self._vault_path)
            if not vault.is_dir():
                self._is_online = False
                self._invalidate_cache()
                self.update()
                return

            raw_nodes, self._edges = _build_vault_graph(self._vault_path)
            self._is_online = True

            if not raw_nodes:
                self._invalidate_cache()
                self.update()
                return

            # Find max connections for normalisation
            max_conns = max((n["connections"] for n in raw_nodes), default=1) or 1

            # Initialise node positions randomly (deterministic seed)
            rng = random.Random(42)
            for n in raw_nodes:
                conns = n["connections"]
                t_norm = min(conns / max(max_conns, 1), 1.0)

                # Color gradient: gray(0) -> teal(mid) -> bright green(high)
                if t_norm >= 0.5:
                    t2 = (t_norm - 0.5) * 2.0
                    r = int(40 + (48 - 40) * t2)
                    g = int(180 + (209 - 180) * t2)
                    b = int(120 + (88 - 120) * t2)
                else:
                    t2 = t_norm * 2.0
                    r = int(120 + (40 - 120) * t2)
                    g = int(120 + (180 - 120) * t2)
                    b = int(130 + (120 - 130) * t2)
                color = QColor(r, g, b)

                # Radius scales with connections: 4..18
                radius = 4.0 + min(conns, 12) * 1.2

                self._nodes.append({
                    "name": n["name"],
                    "connections": conns,
                    "path": n.get("path", ""),
                    "rel_path": n.get("rel_path", ""),
                    "x": rng.uniform(-300, 300),
                    "y": rng.uniform(-300, 300),
                    "vx": 0.0,
                    "vy": 0.0,
                    "radius": radius,
                    "color": color,
                })

            # Run force simulation
            self._sim_step = 0
            if defer_sim:
                # Run the full simulation synchronously so the graph is
                # completely laid out before the window is shown.
                self._run_simulation_sync()
                self._fit_to_view()
                self._invalidate_cache()
                # Re-fit once the widget gets its real size from layout.
                self._needs_initial_fit = True
            else:
                self._sim_timer.start()

        # -- Physics simulation ------------------------------------------

        def _fit_to_view(self) -> None:
            """Zoom and pan so the entire graph fits the viewport."""
            if not self._nodes:
                return
            min_x = min(n["x"] for n in self._nodes)
            max_x = max(n["x"] for n in self._nodes)
            min_y = min(n["y"] for n in self._nodes)
            max_y = max(n["y"] for n in self._nodes)

            graph_w = (max_x - min_x) + 80  # padding for node radius + labels
            graph_h = (max_y - min_y) + 80

            if graph_w < 1 or graph_h < 1:
                return

            view_w = max(self.width(), 200)
            view_h = max(self.height(), 150)

            zoom_x = view_w / graph_w
            zoom_y = view_h / graph_h
            self._zoom = min(zoom_x, zoom_y) * 0.88
            self._zoom = max(0.15, min(6.0, self._zoom))

            # Center on the graph midpoint
            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0
            self._offset_x = -cx * self._zoom
            self._offset_y = -cy * self._zoom

        def _run_simulation_sync(self) -> None:
            """Run the full force-directed simulation synchronously.

            This is pure math with no Qt event-loop dependency, so it is
            safe to call during __init__ before the window is shown.
            Completes all ``_GRAPH_SIM_ITERATIONS`` in one shot so the
            graph layout is fully settled before the first paint.
            """
            n = len(self._nodes)
            if not n:
                return

            k_rep = 6000.0
            k_att = 0.006
            k_grav = 0.004
            damping = 0.88
            max_force = 12.0

            while self._sim_step < _GRAPH_SIM_ITERATIONS:
                # Repulsive forces between all node pairs
                for i in range(n):
                    ni = self._nodes[i]
                    for j in range(i + 1, n):
                        nj = self._nodes[j]
                        dx = nj["x"] - ni["x"]
                        dy = nj["y"] - ni["y"]
                        dist_sq = dx * dx + dy * dy + 1.0
                        dist = math.sqrt(dist_sq)

                        force = min(k_rep / dist_sq, max_force)
                        fx = force * dx / dist
                        fy = force * dy / dist

                        ni["vx"] -= fx
                        ni["vy"] -= fy
                        nj["vx"] += fx
                        nj["vy"] += fy

                # Attractive forces along edges
                for src, tgt in self._edges:
                    if src >= n or tgt >= n:
                        continue
                    ns = self._nodes[src]
                    nt = self._nodes[tgt]
                    dx = nt["x"] - ns["x"]
                    dy = nt["y"] - ns["y"]
                    dist = math.sqrt(dx * dx + dy * dy) + 0.01

                    force = k_att * dist
                    fx = force * dx / dist
                    fy = force * dy / dist

                    ns["vx"] += fx
                    ns["vy"] += fy
                    nt["vx"] -= fx
                    nt["vy"] -= fy

                # Gravity + damping + position update
                for node in self._nodes:
                    node["vx"] -= k_grav * node["x"]
                    node["vy"] -= k_grav * node["y"]
                    node["vx"] *= damping
                    node["vy"] *= damping

                    speed = math.sqrt(node["vx"] ** 2 + node["vy"] ** 2)
                    if speed > 15.0:
                        node["vx"] = node["vx"] / speed * 15.0
                        node["vy"] = node["vy"] / speed * 15.0

                    node["x"] += node["vx"]
                    node["y"] += node["vy"]

                self._sim_step += 1

        def _step_simulation(self) -> None:
            """Run a few iterations of the force-directed layout."""
            if not self._nodes or self._sim_step >= _GRAPH_SIM_ITERATIONS:
                self._sim_timer.stop()
                self._fit_to_view()
                self._invalidate_cache()
                self.update()
                return

            n = len(self._nodes)
            k_rep = 6000.0
            k_att = 0.006
            k_grav = 0.004
            damping = 0.88
            max_force = 12.0

            for _ in range(_GRAPH_SIM_PER_TICK):
                if self._sim_step >= _GRAPH_SIM_ITERATIONS:
                    break

                # Repulsive forces between all node pairs
                for i in range(n):
                    ni = self._nodes[i]
                    for j in range(i + 1, n):
                        nj = self._nodes[j]
                        dx = nj["x"] - ni["x"]
                        dy = nj["y"] - ni["y"]
                        dist_sq = dx * dx + dy * dy + 1.0
                        dist = math.sqrt(dist_sq)

                        force = min(k_rep / dist_sq, max_force)
                        fx = force * dx / dist
                        fy = force * dy / dist

                        ni["vx"] -= fx
                        ni["vy"] -= fy
                        nj["vx"] += fx
                        nj["vy"] += fy

                # Attractive forces along edges
                for src, tgt in self._edges:
                    if src >= n or tgt >= n:
                        continue
                    ns = self._nodes[src]
                    nt = self._nodes[tgt]
                    dx = nt["x"] - ns["x"]
                    dy = nt["y"] - ns["y"]
                    dist = math.sqrt(dx * dx + dy * dy) + 0.01

                    force = k_att * dist
                    fx = force * dx / dist
                    fy = force * dy / dist

                    ns["vx"] += fx
                    ns["vy"] += fy
                    nt["vx"] -= fx
                    nt["vy"] -= fy

                # Gravity + damping + position update
                for node in self._nodes:
                    node["vx"] -= k_grav * node["x"]
                    node["vy"] -= k_grav * node["y"]
                    node["vx"] *= damping
                    node["vy"] *= damping

                    speed = math.sqrt(node["vx"] ** 2 + node["vy"] ** 2)
                    if speed > 15.0:
                        node["vx"] = node["vx"] / speed * 15.0
                        node["vy"] = node["vy"] / speed * 15.0

                    node["x"] += node["vx"]
                    node["y"] += node["vy"]

                self._sim_step += 1

            self._invalidate_cache()
            self.update()

        # -- Coordinate helpers ------------------------------------------

        def _world_to_screen(self, wx: float, wy: float) -> Tuple[float, float]:
            """Convert world coordinates to screen pixel coordinates."""
            cx = self.width() / 2.0 + self._offset_x
            cy = self.height() / 2.0 + self._offset_y
            return cx + wx * self._zoom, cy + wy * self._zoom

        def _screen_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
            """Convert screen pixel coordinates to world coordinates."""
            cx = self.width() / 2.0 + self._offset_x
            cy = self.height() / 2.0 + self._offset_y
            return (sx - cx) / self._zoom, (sy - cy) / self._zoom

        def _hit_test(self, sx: float, sy: float) -> int:
            """Return index of node under screen point, or -1."""
            best = -1
            best_dist_sq = float("inf")
            for i, node in enumerate(self._nodes):
                nx, ny = self._world_to_screen(node["x"], node["y"])
                r = (node["radius"] + 4) * self._zoom  # extra hit margin
                dx = sx - nx
                dy = sy - ny
                d2 = dx * dx + dy * dy
                if d2 <= r * r and d2 < best_dist_sq:
                    best_dist_sq = d2
                    best = i
            return best

        # -- QPainter rendering ------------------------------------------

        def paintEvent(self, event: Any) -> None:
            """Render the graph, using a cached pixmap when possible."""
            w = self.width()
            h = self.height()

            # During active resize, stretch the stale cached pixmap instead
            # of doing an expensive full re-render every frame.
            if self._resizing and self._cached_pixmap is not None:
                painter = QPainter(self)
                painter.drawPixmap(0, 0, w, h, self._cached_pixmap)
                painter.end()
                return

            # Re-render into cache when dirty or cache doesn't exist.
            if self._cache_dirty or self._cached_pixmap is None:
                self._cached_pixmap = QPixmap(w, h)
                self._cached_pixmap.fill(QColor(24, 24, 26))
                self._render_graph(self._cached_pixmap)
                self._cache_dirty = False

            painter = QPainter(self)
            painter.drawPixmap(0, 0, self._cached_pixmap)
            painter.end()

        def _render_graph(self, target: "QPixmap") -> None:
            """Render the full interactive graph onto a QPixmap."""
            painter = QPainter(target)
            if hasattr(QPainter.RenderHint, "Antialiasing"):
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            else:
                painter.setRenderHint(QPainter.Antialiasing)

            w = target.width()
            h = target.height()
            z = self._zoom
            num = len(self._nodes)

            # Background gradient (subtle radial feel via vertical gradient)
            painter.fillRect(0, 0, w, h, QColor(24, 24, 26))

            # Empty state
            if not self._nodes:
                painter.setPen(QColor(100, 100, 100))
                font = painter.font()
                font.setPointSize(13)
                painter.setFont(font)
                if not self._is_online:
                    msg = "Vault not found"
                elif self._sim_step < _GRAPH_SIM_ITERATIONS:
                    msg = "Building graph..."
                else:
                    msg = "No linked notes"
                align = (
                    Qt.AlignmentFlag.AlignCenter
                    if hasattr(Qt, "AlignmentFlag")
                    else Qt.AlignCenter
                )
                painter.drawText(0, 0, w, h, align, msg)
                painter.end()
                return

            no_pen = (
                Qt.PenStyle.NoPen if hasattr(Qt, "PenStyle") else Qt.NoPen
            )

            # --- Edges ---------------------------------------------------
            for src, tgt in self._edges:
                if src >= num or tgt >= num:
                    continue
                ns = self._nodes[src]
                nt = self._nodes[tgt]
                x1, y1 = self._world_to_screen(ns["x"], ns["y"])
                x2, y2 = self._world_to_screen(nt["x"], nt["y"])

                # Edge brightness based on connected-node importance
                importance = min(ns["connections"] + nt["connections"], 20)
                alpha = 25 + int(importance * 3.5)

                # Highlight edges connected to hovered/selected node
                if self._hovered_idx in (src, tgt):
                    alpha = min(alpha + 80, 200)
                elif self._selected_idx in (src, tgt):
                    alpha = min(alpha + 50, 180)

                pen = QPen(QColor(140, 140, 145, alpha))
                pen.setWidthF(0.6 + min(importance * 0.05, 0.8))
                painter.setPen(pen)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

            # --- Precompute focus neighbors for label visibility ----------
            focus_neighbors: set = set()
            focus_idx = (
                self._hovered_idx
                if self._hovered_idx >= 0
                else self._selected_idx
            )
            if focus_idx >= 0:
                for src, tgt in self._edges:
                    if src == focus_idx and tgt < num:
                        focus_neighbors.add(tgt)
                    elif tgt == focus_idx and src < num:
                        focus_neighbors.add(src)

            # --- Nodes (bottom layer: glow, then circle, then label) -----
            focus_font = painter.font()
            focus_font.setPointSizeF(max(9.0, 10.5 * min(z, 1.8)))
            focus_font.setWeight(
                QFont.Weight.DemiBold if hasattr(QFont, "Weight") else 63
            )

            label_font = painter.font()
            label_font.setPointSizeF(max(8.0, 9.0 * min(z, 1.6)))
            label_font.setWeight(
                QFont.Weight.Medium if hasattr(QFont, "Weight") else 57
            )

            small_label_font = painter.font()
            small_label_font.setPointSizeF(max(7.0, 8.0 * min(z, 1.4)))

            for i, node in enumerate(self._nodes):
                sx, sy = self._world_to_screen(node["x"], node["y"])
                r = node["radius"] * z

                # Cull off-screen nodes (generous margin for labels)
                if sx + r + 150 < 0 or sx - r - 150 > w:
                    continue
                if sy + r + 40 < 0 or sy - r - 40 > h:
                    continue

                is_hovered = i == self._hovered_idx
                is_selected = i == self._selected_idx
                is_neighbor = i in focus_neighbors
                conns = node["connections"]

                # Glow for hovered / selected / neighbor / high-connection
                if is_hovered or is_selected:
                    glow_r = r + 8 * z
                    gc = QColor(node["color"])
                    gc.setAlpha(55 if is_hovered else 40)
                    painter.setPen(no_pen)
                    painter.setBrush(QBrush(gc))
                    painter.drawEllipse(
                        int(sx - glow_r), int(sy - glow_r),
                        int(glow_r * 2), int(glow_r * 2),
                    )
                elif is_neighbor:
                    glow_r = r + 6 * z
                    gc = QColor(node["color"])
                    gc.setAlpha(30)
                    painter.setPen(no_pen)
                    painter.setBrush(QBrush(gc))
                    painter.drawEllipse(
                        int(sx - glow_r), int(sy - glow_r),
                        int(glow_r * 2), int(glow_r * 2),
                    )
                elif conns >= 6:
                    glow_r = r + 5 * z
                    gc = QColor(node["color"])
                    gc.setAlpha(20)
                    painter.setPen(no_pen)
                    painter.setBrush(QBrush(gc))
                    painter.drawEllipse(
                        int(sx - glow_r), int(sy - glow_r),
                        int(glow_r * 2), int(glow_r * 2),
                    )

                # Node circle
                painter.setPen(no_pen)
                fill = QColor(node["color"])
                if is_hovered:
                    fill = fill.lighter(130)
                elif is_selected:
                    fill = fill.lighter(120)
                elif is_neighbor:
                    fill = fill.lighter(110)
                painter.setBrush(QBrush(fill))
                painter.drawEllipse(
                    int(sx - r), int(sy - r), int(r * 2), int(r * 2)
                )

                # Selection ring
                if is_selected:
                    ring_pen = QPen(QColor(255, 255, 255, 160))
                    ring_pen.setWidthF(1.5)
                    painter.setPen(ring_pen)
                    painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
                    rr = r + 2 * z
                    painter.drawEllipse(
                        int(sx - rr), int(sy - rr), int(rr * 2), int(rr * 2)
                    )

                # --- Labels -------------------------------------------------
                # Visibility tiers (zoom-aware + focus-aware):
                #   - Hovered / selected: ALWAYS show, full brightness
                #   - Neighbor of focused: ALWAYS show, slightly dimmer
                #   - High-connection (>=6): show at zoom >= 0.4
                #   - Medium-connection (>=3): show at zoom >= 0.9
                #   - Low-connection (>=1): show at zoom >= 1.8
                #   - Everything: zoom >= 3.0
                show_label = (
                    is_hovered
                    or is_selected
                    or is_neighbor
                    or (conns >= 6 and z >= 0.4)
                    or (conns >= 3 and z >= 0.9)
                    or (conns >= 1 and z >= 1.8)
                    or z >= 3.0
                )
                if show_label:
                    name = node["name"]

                    # Font and alpha based on focus state
                    if is_hovered or is_selected:
                        painter.setFont(focus_font)
                        text_alpha = 255
                        shadow_alpha = 200
                        if len(name) > 30:
                            name = name[:28] + "..."
                    elif is_neighbor:
                        painter.setFont(label_font)
                        text_alpha = 210
                        shadow_alpha = 170
                        if len(name) > 24:
                            name = name[:22] + "..."
                    elif conns >= 5:
                        painter.setFont(label_font)
                        # Fade in based on zoom
                        text_alpha = int(min(80 + 140 * min(z, 1.5), 220))
                        shadow_alpha = int(text_alpha * 0.7)
                        if len(name) > 20:
                            name = name[:18] + "..."
                    else:
                        painter.setFont(small_label_font)
                        # Progressive fade: only fully visible at higher zoom
                        t_fade = max(0.0, min((z - 0.8) / 1.5, 1.0))
                        text_alpha = int(60 + 150 * t_fade)
                        shadow_alpha = int(text_alpha * 0.6)
                        if len(name) > 18:
                            name = name[:16] + "..."

                    # Text shadow for readability
                    shadow_color = QColor(0, 0, 0, shadow_alpha)
                    if is_hovered or is_selected:
                        text_color = QColor(255, 255, 255, text_alpha)
                    elif is_neighbor:
                        text_color = QColor(240, 240, 245, text_alpha)
                    else:
                        text_color = QColor(210, 210, 215, text_alpha)

                    tx = int(sx + r + 4 * z)
                    ty = int(sy + 4)

                    painter.setPen(shadow_color)
                    painter.drawText(tx + 1, ty + 1, name)
                    painter.setPen(text_color)
                    painter.drawText(tx, ty, name)

            # --- Hover tooltip -------------------------------------------
            if self._hovered_idx >= 0 and self._hovered_idx < num:
                hn = self._nodes[self._hovered_idx]
                sx, sy = self._world_to_screen(hn["x"], hn["y"])
                r = hn["radius"] * z

                tip_lines = [
                    hn["name"],
                    f"{hn['connections']} connections",
                ]
                if hn.get("rel_path"):
                    tip_lines.append(hn["rel_path"])

                # Tooltip background
                tip_font = painter.font()
                tip_font.setPointSizeF(9.5)
                painter.setFont(tip_font)

                fm = painter.fontMetrics()
                line_h = fm.height() + 2
                tip_w = max(fm.horizontalAdvance(ln) for ln in tip_lines) + 16
                tip_h = line_h * len(tip_lines) + 10
                tip_x = int(sx + r + 10 * z)
                tip_y = int(sy - tip_h / 2)

                # Keep tooltip on screen
                if tip_x + tip_w > w - 4:
                    tip_x = int(sx - r - 10 * z - tip_w)
                if tip_y < 4:
                    tip_y = 4
                if tip_y + tip_h > h - 4:
                    tip_y = h - 4 - tip_h

                painter.setPen(no_pen)
                painter.setBrush(QBrush(QColor(20, 20, 22, 230)))
                painter.drawRoundedRect(tip_x, tip_y, tip_w, tip_h, 6, 6)

                # Tooltip border
                border_pen = QPen(QColor(60, 60, 65, 180))
                border_pen.setWidthF(0.8)
                painter.setPen(border_pen)
                painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
                painter.drawRoundedRect(tip_x, tip_y, tip_w, tip_h, 6, 6)

                # Tooltip text
                for li, line in enumerate(tip_lines):
                    if li == 0:
                        painter.setPen(QColor(255, 255, 255, 240))
                        bold_f = painter.font()
                        bold_f.setWeight(
                            QFont.Weight.DemiBold
                            if hasattr(QFont, "Weight")
                            else 63
                        )
                        painter.setFont(bold_f)
                    else:
                        painter.setPen(QColor(160, 160, 165, 220))
                        norm_f = painter.font()
                        norm_f.setWeight(
                            QFont.Weight.Normal
                            if hasattr(QFont, "Weight")
                            else 50
                        )
                        painter.setFont(norm_f)
                    painter.drawText(
                        tip_x + 8, tip_y + 6 + (li + 1) * line_h - 2, line
                    )

            # --- Stats overlay (bottom-left) -----------------------------
            painter.setFont(small_label_font)
            painter.setPen(QColor(90, 90, 95, 180))
            edge_count = len(self._edges)
            stats = f"{num} notes  {edge_count} links"
            painter.drawText(8, h - 8, stats)

            # --- "Click to open" hint (bottom-right when selected) -------
            if self._selected_idx >= 0:
                painter.setPen(QColor(48, 209, 88, 160))
                hint_f = painter.font()
                hint_f.setPointSizeF(9.0)
                painter.setFont(hint_f)
                hint = "Double-click to open in editor"
                hw = painter.fontMetrics().horizontalAdvance(hint)
                painter.drawText(w - hw - 10, h - 8, hint)

            painter.end()

        # -- Mouse interaction -------------------------------------------

        def mousePressEvent(self, event: Any) -> None:
            btn_left = (
                Qt.MouseButton.LeftButton
                if hasattr(Qt, "MouseButton")
                else Qt.LeftButton
            )
            if event.button() == btn_left:
                self._dragging = True
                self._drag_moved = False
                self._last_mouse_pos = event.pos()

        def mouseMoveEvent(self, event: Any) -> None:
            pos = event.pos()

            if self._dragging and self._last_mouse_pos is not None:
                delta = pos - self._last_mouse_pos
                if abs(delta.x()) > 2 or abs(delta.y()) > 2:
                    self._drag_moved = True
                self._offset_x += delta.x()
                self._offset_y += delta.y()
                self._last_mouse_pos = pos
                self.setCursor(
                    Qt.CursorShape.ClosedHandCursor
                    if hasattr(Qt, "CursorShape")
                    else Qt.ClosedHandCursor
                )
                self._invalidate_cache()
                self.update()
                return

            # Hover detection
            hit = self._hit_test(pos.x(), pos.y())
            if hit != self._hovered_idx:
                self._hovered_idx = hit
                if hit >= 0:
                    self.setCursor(
                        Qt.CursorShape.PointingHandCursor
                        if hasattr(Qt, "CursorShape")
                        else Qt.PointingHandCursor
                    )
                else:
                    self.setCursor(
                        Qt.CursorShape.OpenHandCursor
                        if hasattr(Qt, "CursorShape")
                        else Qt.OpenHandCursor
                    )
                self._invalidate_cache()
                self.update()

        def mouseReleaseEvent(self, event: Any) -> None:
            btn_left = (
                Qt.MouseButton.LeftButton
                if hasattr(Qt, "MouseButton")
                else Qt.LeftButton
            )
            if event.button() == btn_left:
                was_drag = self._drag_moved
                self._dragging = False
                self._drag_moved = False
                self._last_mouse_pos = None

                if not was_drag:
                    # Click: select node
                    hit = self._hit_test(event.pos().x(), event.pos().y())
                    old_sel = self._selected_idx
                    self._selected_idx = hit

                    if hit >= 0 and hit != old_sel:
                        node = self._nodes[hit]
                        self.node_clicked.emit(node.get("path", ""), node["name"])

                    self._invalidate_cache()
                    self.update()

                # Restore cursor
                if self._hovered_idx >= 0:
                    self.setCursor(
                        Qt.CursorShape.PointingHandCursor
                        if hasattr(Qt, "CursorShape")
                        else Qt.PointingHandCursor
                    )
                else:
                    self.setCursor(
                        Qt.CursorShape.OpenHandCursor
                        if hasattr(Qt, "CursorShape")
                        else Qt.OpenHandCursor
                    )

        def mouseDoubleClickEvent(self, event: Any) -> None:
            """Double-click a node to open it in the system editor."""
            hit = self._hit_test(event.pos().x(), event.pos().y())
            if hit >= 0:
                fpath = self._nodes[hit].get("path", "")
                if fpath and os.path.isfile(fpath):
                    import subprocess
                    try:
                        subprocess.Popen(["open", fpath])
                    except OSError:
                        pass

        def wheelEvent(self, event: Any) -> None:
            delta = event.angleDelta().y()
            # Zoom toward mouse position
            pos = event.position() if hasattr(event, "position") else event.posF()
            mx, my = pos.x(), pos.y()
            old_wx, old_wy = self._screen_to_world(mx, my)

            factor = 1.12 if delta > 0 else 0.89
            self._zoom = max(0.15, min(6.0, self._zoom * factor))

            # Adjust offset so the point under the mouse stays fixed
            new_sx, new_sy = self._world_to_screen(old_wx, old_wy)
            self._offset_x += mx - new_sx
            self._offset_y += my - new_sy

            self._invalidate_cache()
            self.update()

        def leaveEvent(self, event: Any) -> None:
            if self._hovered_idx >= 0:
                self._hovered_idx = -1
                self._invalidate_cache()
                self.update()

    # ===================================================================
    # VaultGraphSection -- tabbed graph + note preview
    # ===================================================================

    class VaultGraphSection(QWidget):
        """Section with tabbed graph views and an integrated note preview."""

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Section header
            header = QWidget()
            header.setFixedHeight(28)
            header.setStyleSheet(
                "background: #0A0A0A; border-top: 1px solid #2C2C2E;"
            )
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(12, 4, 12, 4)

            title = QLabel("Obsidian Graph")
            title.setStyleSheet(
                "color: #8E8E93; font-size: 11px; font-weight: 600;"
            )
            header_layout.addWidget(title)
            header_layout.addStretch()

            self._status_label = QLabel("")
            self._status_label.setStyleSheet(
                "color: #48484A; font-size: 10px; background: transparent;"
            )
            header_layout.addWidget(self._status_label)

            layout.addWidget(header)

            # Main content: graph + optional note preview splitter
            self._content_splitter = QSplitter(
                Qt.Orientation.Horizontal
                if hasattr(Qt, "Orientation")
                else Qt.Horizontal
            )
            self._content_splitter.setHandleWidth(2)

            # Tabbed graphs (left/main)
            self._tabs = QTabWidget()
            _elide_none = (
                Qt.TextElideMode.ElideNone
                if hasattr(Qt, "TextElideMode")
                else Qt.ElideNone
            )
            self._tabs.tabBar().setElideMode(_elide_none)
            self._tabs.tabBar().setExpanding(True)
            self._tabs.tabBar().setUsesScrollButtons(False)
            self._tabs.setStyleSheet("""
                QTabWidget::pane {
                    background: #18181A;
                    border: none;
                }
                QTabBar::tab {
                    background: transparent;
                    color: #8E8E93;
                    padding: 4px 14px;
                    font-size: 11px;
                    border: none;
                    border-bottom: 2px solid transparent;
                    min-width: 60px;
                }
                QTabBar::tab:selected {
                    color: #FFFFFF;
                    border-bottom: 2px solid #30D158;
                }
                QTabBar::tab:hover:!selected {
                    color: #C7C7CC;
                }
            """)

            # Kait Brain graph
            brain_path = _resolve_vault_path(
                "KAIT_VAULT_BRAIN_PATH", _DEFAULT_KAIT_VAULT
            )
            self._brain_graph = VaultGraphWidget(brain_path, "Kait Brain")
            self._brain_graph.node_clicked.connect(self._on_node_clicked)
            self._tabs.addTab(self._brain_graph, "Kait Brain")

            # BLERBZ OS Map graph
            gitmap_path = _resolve_vault_path(
                "KAIT_VAULT_GITMAP_PATH", _DEFAULT_GITMAP_VAULT
            )
            self._github_graph = VaultGraphWidget(gitmap_path, "BLERBZ OS Map")
            self._github_graph.node_clicked.connect(self._on_node_clicked)
            self._tabs.addTab(self._github_graph, "BLERBZ OS Map")

            self._content_splitter.addWidget(self._tabs)

            # Note preview panel (right side, hidden by default)
            self._note_viewer = VaultNoteViewer()
            self._note_viewer.setMinimumWidth(180)
            self._note_viewer.show_placeholder("Click a node to preview")
            self._content_splitter.addWidget(self._note_viewer)

            # Start with preview hidden (graph takes full width)
            self._content_splitter.setSizes([600, 0])
            self._note_preview_visible = False

            layout.addWidget(self._content_splitter, stretch=1)

        def _on_node_clicked(self, file_path: str, file_name: str) -> None:
            """Show the clicked note in the preview panel."""
            if not file_path or not os.path.isfile(file_path):
                return

            # Show the preview panel if hidden
            if not self._note_preview_visible:
                total = sum(self._content_splitter.sizes()) or 600
                self._content_splitter.setSizes(
                    [int(total * 0.55), int(total * 0.45)]
                )
                self._note_preview_visible = True

            ext = os.path.splitext(file_path)[1].lower()
            self._note_viewer.show_note({
                "path": file_path,
                "name": file_name,
                "extension": ext,
            })
            self._status_label.setText(file_name)
            self._status_label.setStyleSheet(
                "color: #30D158; font-size: 10px; background: transparent;"
            )

else:
    # Stubs when Qt is not available
    class VaultNoteViewer:  # type: ignore[no-redef]
        pass

    class VaultFileList:  # type: ignore[no-redef]
        pass

    class VaultViewerPanel:  # type: ignore[no-redef]
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

    def create_kait_brain_panel(*a: Any, **kw: Any) -> Any:
        return None

    def create_github_mindmap_panel(*a: Any, **kw: Any) -> Any:
        return None

    class VaultGraphWidget:  # type: ignore[no-redef]
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

    class VaultGraphSection:  # type: ignore[no-redef]
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass
