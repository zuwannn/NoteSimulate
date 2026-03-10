import sys
import time
import threading

from PyQt6.QtWidgets import (
    QApplication, QWidget, QTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QScrollArea, QFrame, QSizePolicy,
    QSpinBox, QComboBox, QGridLayout, QSlider
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPropertyAnimation, QRect
from PyQt6.QtGui import QColor, QPalette, QFont, QPainter, QPen, QBrush, QLinearGradient, QFontDatabase

from pynput.keyboard import Controller

keyboard = Controller()


# ─────────────────────────────────────────────
#  Default Hearttopia keyboard map (from screenshot)
# ─────────────────────────────────────────────
DEFAULT_MAP = [
    # Row 1 – top keyboard row
    ("Do",  "1", "q"),
    ("Re",  "2", "w"),
    ("Mi",  "3", "e"),
    ("Fa",  "4", "r"),
    ("Sol", "5", "t"),
    ("La",  "6", "y"),
    ("Si",  "7", "u"),
    ("Do²","1'","i"),   # high octave

    # Row 2 – home row
    ("Do",  "1", "z"),
    ("Re",  "2", "x"),
    ("Mi",  "3", "c"),
    ("Fa",  "4", "v"),
    ("Sol", "5", "b"),
    ("La",  "6", "h"),
    ("Si",  "7", "j"),
    ("Si",  "7", "m"),

    # Row 3 – bottom row
    ("Do",  "1", "l"),
    ("Re",  "2", ";"),
    ("Mi",  "3", "/"),
    ("Fa",  "4", "o"),
    ("Sol", "5", "p"),
    ("La",  "6", "["),
    ("Si",  "7", "]"),
]

NOTE_COLORS = {
    "1":  "#FF6B6B",
    "2":  "#FF9F43",
    "3":  "#FFEAA7",
    "4":  "#A8E6CF",
    "5":  "#74B9FF",
    "6":  "#A29BFE",
    "7":  "#FD79A8",
    "1'": "#FF6B6B",
}

SOLFEGE_LABELS = {
    "Do": "DO", "Re": "RE", "Mi": "MI",
    "Fa": "FA", "Sol": "SOL", "La": "LA",
    "Si": "SI", "Do²": "DO²",
}

# ─────────────────────────────────────────────
#  Signal bridge (thread → UI)
# ─────────────────────────────────────────────
class Signals(QObject):
    note_played   = pyqtSignal(str, str)   # note_name, key
    playback_done = pyqtSignal()
    update_beat   = pyqtSignal(int)        # current beat index


# ─────────────────────────────────────────────
#  Glowing note button
# ─────────────────────────────────────────────
class NoteButton(QPushButton):
    def __init__(self, note_name, degree, key, parent=None):
        super().__init__(parent)
        self.note_name = note_name
        self.degree    = degree
        self.key       = key
        self._active   = False

        color = NOTE_COLORS.get(degree, "#ffffff")
        self.setFixedSize(70, 70)
        self.setCheckable(False)

        self._base_style = f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {color}ee, stop:1 {color}88);
                border: 2px solid {color};
                border-radius: 35px;
                color: #1a1a2e;
                font-family: 'Nunito';
                font-size: 11px;
                font-weight: 800;
            }}
            QPushButton:hover {{
                background: {color};
                border: 3px solid white;
            }}
            QPushButton:pressed {{
                background: white;
            }}
        """
        self._active_style = f"""
            QPushButton {{
                background: white;
                border: 3px solid {color};
                border-radius: 35px;
                color: #1a1a2e;
                font-family: 'Nunito';
                font-size: 11px;
                font-weight: 800;
            }}
        """
        self.setStyleSheet(self._base_style)
        self.setText(f"{SOLFEGE_LABELS.get(note_name, note_name)}\n[{key.upper()}]")

    def set_active(self, active: bool):
        self._active = active
        self.setStyleSheet(self._active_style if active else self._base_style)


# ─────────────────────────────────────────────
#  Beat cell in the sequencer grid
# ─────────────────────────────────────────────
class BeatCell(QPushButton):
    def __init__(self, row, col, degree, parent=None):
        super().__init__(parent)
        self.row     = row
        self.col     = col
        self.degree  = degree
        self._on     = False
        self._cursor = False

        self.setFixedSize(36, 36)
        self.setCheckable(True)
        self.toggled.connect(self._on_toggle)
        self._refresh()

    def _on_toggle(self, checked):
        self._on = checked
        self._refresh()

    def set_cursor(self, active: bool):
        self._cursor = active
        self._refresh()

    def _refresh(self):
        color   = NOTE_COLORS.get(self.degree, "#888888")
        if self._cursor:
            bg = "white"
            border = f"3px solid {color}"
        elif self._on:
            bg = color
            border = f"2px solid white"
        else:
            bg = "#1e1e3a"
            border = f"1px solid #3a3a6a"

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: {border};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {color}55;
                border: 2px solid {color};
            }}
        """)


# ─────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────
class HeartopiaSequencer(QWidget):

    def __init__(self):
        super().__init__()
        self.signals  = Signals()
        self.running  = False
        self.beat_idx = 0
        self.beats    = 16
        self.bpm      = 120

        # build note map: (note_name, degree) → key
        self.note_map: dict[str, str] = {}
        for name, deg, key in DEFAULT_MAP:
            label = f"{name}({key.upper()})"
            self.note_map[label] = key

        # flat list for sequencer rows
        self.row_defs = DEFAULT_MAP  # (name, degree, key)
        self.num_rows = len(self.row_defs)

        self._init_ui()
        self._connect_signals()

    # ── UI construction ──────────────────────
    def _init_ui(self):
        self.setWindowTitle("♪ Hearttopia Music Sequencer v2")
        self.resize(1300, 800)

        self.setStyleSheet("""
            QWidget {
                background-color: #0f0f23;
                color: #e0e0ff;
                font-family: 'Nunito', 'Segoe UI', sans-serif;
            }
            QScrollArea { border: none; }
            QLabel { color: #c0c0ee; }
        """)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Header ──
        header = QLabel("♪  HEARTTOPIA  MUSIC  SEQUENCER")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("""
            font-size: 22px;
            font-weight: 900;
            letter-spacing: 6px;
            color: #a29bfe;
            padding: 8px;
        """)
        root.addWidget(header)

        # ── Transport bar ──
        transport = QHBoxLayout()
        transport.setSpacing(12)

        self.btn_play  = self._mk_btn("▶  PLAY",  "#00b894")
        self.btn_stop  = self._mk_btn("■  STOP",  "#d63031")
        self.btn_clear = self._mk_btn("✕  CLEAR", "#636e72")

        lbl_bpm = QLabel("BPM")
        lbl_bpm.setStyleSheet("color:#a29bfe; font-weight:700;")
        self.spin_bpm = QSpinBox()
        self.spin_bpm.setRange(40, 300)
        self.spin_bpm.setValue(self.bpm)
        self.spin_bpm.setFixedWidth(70)
        self.spin_bpm.setStyleSheet("""
            QSpinBox {
                background:#1e1e3a; color:#e0e0ff;
                border:1px solid #a29bfe; border-radius:6px;
                padding:4px; font-size:14px; font-weight:700;
            }
        """)

        lbl_beats = QLabel("Beats")
        lbl_beats.setStyleSheet("color:#a29bfe; font-weight:700;")
        self.combo_beats = QComboBox()
        for b in [8, 16, 32]:
            self.combo_beats.addItem(str(b))
        self.combo_beats.setCurrentIndex(1)
        self.combo_beats.setFixedWidth(60)
        self.combo_beats.setStyleSheet("""
            QComboBox {
                background:#1e1e3a; color:#e0e0ff;
                border:1px solid #a29bfe; border-radius:6px;
                padding:4px; font-size:13px;
            }
            QComboBox QAbstractItemView { background:#1e1e3a; color:#e0e0ff; }
        """)

        transport.addWidget(self.btn_play)
        transport.addWidget(self.btn_stop)
        transport.addWidget(self.btn_clear)
        transport.addStretch()
        transport.addWidget(lbl_bpm)
        transport.addWidget(self.spin_bpm)
        transport.addWidget(lbl_beats)
        transport.addWidget(self.combo_beats)

        root.addLayout(transport)

        # ── Main area: sequencer + text input ──
        body = QHBoxLayout()
        body.setSpacing(14)

        # Sequencer grid
        grid_frame = QFrame()
        grid_frame.setStyleSheet("""
            QFrame {
                background: #12122a;
                border: 1px solid #2a2a5a;
                border-radius: 12px;
            }
        """)
        grid_layout = QVBoxLayout(grid_frame)
        grid_layout.setContentsMargins(10, 10, 10, 10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background:transparent;")
        self.grid_inner  = QGridLayout(self.grid_widget)
        self.grid_inner.setSpacing(4)

        self.cells: list[list[BeatCell]] = []
        self._build_grid(self.beats)

        scroll.setWidget(self.grid_widget)
        grid_layout.addWidget(scroll)

        body.addWidget(grid_frame, 3)

        # Right panel
        right = QVBoxLayout()
        right.setSpacing(10)

        # Text note input
        note_frame = QFrame()
        note_frame.setStyleSheet("""
            QFrame { background:#12122a; border:1px solid #2a2a5a; border-radius:12px; }
        """)
        note_layout = QVBoxLayout(note_frame)

        lbl_input = QLabel("♩  Text Note Input  (e.g.  Do Re Mi Fa Sol)")
        lbl_input.setStyleSheet("font-size:12px; color:#a29bfe; font-weight:700;")
        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText(
            "พิมพ์ชื่อ note เช่น:\nDo Re Mi Fa Sol La Si Do²\n\n"
            "หรือใช้ key เช่น:\nq w e r t y u i"
        )
        self.note_input.setMaximumHeight(110)
        self.note_input.setStyleSheet("""
            QTextEdit {
                background:#0f0f23; color:#e0e0ff;
                border:1px solid #3a3a6a; border-radius:8px;
                font-size:13px; padding:6px;
            }
        """)

        self.btn_send = self._mk_btn("▶  Play Text Sequence", "#6c5ce7")
        note_layout.addWidget(lbl_input)
        note_layout.addWidget(self.note_input)
        note_layout.addWidget(self.btn_send)
        right.addWidget(note_frame)

        # Log
        log_frame = QFrame()
        log_frame.setStyleSheet("""
            QFrame { background:#12122a; border:1px solid #2a2a5a; border-radius:12px; }
        """)
        log_layout = QVBoxLayout(log_frame)
        lbl_log = QLabel("📋  Activity Log")
        lbl_log.setStyleSheet("font-size:12px; color:#a29bfe; font-weight:700;")
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("""
            QTextEdit {
                background:#0a0a1a; color:#74b9ff;
                border:1px solid #3a3a6a; border-radius:8px;
                font-family: 'Courier New'; font-size:12px; padding:6px;
            }
        """)
        log_layout.addWidget(lbl_log)
        log_layout.addWidget(self.log_box)
        right.addWidget(log_frame, 1)

        # Note keyboard reference
        kb_frame = QFrame()
        kb_frame.setStyleSheet("""
            QFrame { background:#12122a; border:1px solid #2a2a5a; border-radius:12px; }
        """)
        kb_layout = QVBoxLayout(kb_frame)
        lbl_kb = QLabel("🎹  Hearttopia Key Map")
        lbl_kb.setStyleSheet("font-size:12px; color:#a29bfe; font-weight:700;")
        kb_layout.addWidget(lbl_kb)

        kb_grid = QGridLayout()
        kb_grid.setSpacing(4)
        shown = {}
        col = 0
        for name, deg, key in DEFAULT_MAP:
            if key in shown:
                continue
            shown[key] = True
            btn = NoteButton(name, deg, key)
            btn.setFixedSize(58, 58)
            btn.clicked.connect(lambda _, k=key, n=name, d=deg: self._manual_press(k, n, d))
            kb_grid.addWidget(btn, 0 if col < 8 else (1 if col < 16 else 2), col % 8)
            col += 1

        kb_layout.addLayout(kb_grid)
        right.addWidget(kb_frame)

        body.addLayout(right, 2)
        root.addLayout(body, 1)

    def _build_grid(self, beats: int):
        # clear
        for r in self.cells:
            for c in r:
                c.deleteLater()
        self.cells.clear()

        while self.grid_inner.count():
            item = self.grid_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.beats = beats

        # Beat number headers
        for col in range(beats):
            lbl = QLabel(str(col + 1))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(36)
            lbl.setStyleSheet("color:#555588; font-size:10px;")
            self.grid_inner.addWidget(lbl, 0, col + 1)

        for row_idx, (name, deg, key) in enumerate(self.row_defs):
            # Row label
            color = NOTE_COLORS.get(deg, "#888")
            lbl = QLabel(f"{SOLFEGE_LABELS.get(name, name)}\n[{key.upper()}]")
            lbl.setFixedWidth(54)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(f"color:{color}; font-size:10px; font-weight:700;")
            self.grid_inner.addWidget(lbl, row_idx + 1, 0)

            row_cells = []
            for col in range(beats):
                cell = BeatCell(row_idx, col, deg)
                self.grid_inner.addWidget(cell, row_idx + 1, col + 1)
                row_cells.append(cell)
            self.cells.append(row_cells)

    # ── Helpers ──────────────────────────────
    def _mk_btn(self, text, color):
        btn = QPushButton(text)
        btn.setFixedHeight(36)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color}33;
                color: {color};
                border: 1px solid {color};
                border-radius: 8px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {color}88;
                color: white;
            }}
            QPushButton:pressed {{
                background: {color};
                color: #0f0f23;
            }}
        """)
        return btn

    def _connect_signals(self):
        self.btn_play.clicked.connect(self.start_sequencer)
        self.btn_stop.clicked.connect(self.stop_all)
        self.btn_clear.clicked.connect(self.clear_grid)
        self.btn_send.clicked.connect(self.play_text_sequence)
        self.combo_beats.currentTextChanged.connect(
            lambda t: self._build_grid(int(t))
        )
        self.spin_bpm.valueChanged.connect(lambda v: setattr(self, 'bpm', v))

        self.signals.note_played.connect(self._on_note_played)
        self.signals.playback_done.connect(self._on_done)
        self.signals.update_beat.connect(self._advance_cursor)

    # ── Grid sequencer ───────────────────────
    def start_sequencer(self):
        if self.running:
            return
        self.running  = True
        self.beat_idx = 0
        threading.Thread(target=self._run_sequencer, daemon=True).start()

    def _run_sequencer(self):
        interval = 60.0 / self.bpm / 1  # quarter note

        while self.running:
            col = self.beat_idx % self.beats
            self.signals.update_beat.emit(col)

            for row_idx, (name, deg, key) in enumerate(self.row_defs):
                cell = self.cells[row_idx][col]
                if cell._on:
                    keyboard.press(key)
                    keyboard.release(key)
                    self.signals.note_played.emit(
                        f"{SOLFEGE_LABELS.get(name, name)}({key.upper()})", key
                    )

            self.beat_idx += 1
            time.sleep(interval)

    def _advance_cursor(self, col: int):
        prev_col = (col - 1) % self.beats
        for row in self.cells:
            row[prev_col].set_cursor(False)
            row[col].set_cursor(True)

    def stop_all(self):
        self.running = False
        # clear cursors
        for row in self.cells:
            for cell in row:
                cell.set_cursor(False)
        self.log_box.append("■ Stopped.")

    def clear_grid(self):
        for row in self.cells:
            for cell in row:
                if cell._on:
                    cell.setChecked(False)

    # ── Text sequence player ─────────────────
    def play_text_sequence(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._play_text, daemon=True).start()

    def _play_text(self):
        text   = self.note_input.toPlainText().strip()
        tokens = text.split()

        # Build lookup: name → key  AND  key → key
        lookup: dict[str, tuple[str, str]] = {}
        for name, deg, key in DEFAULT_MAP:
            sol = SOLFEGE_LABELS.get(name, name)
            lookup[sol.lower()]  = (sol, key)
            lookup[name.lower()] = (sol, key)
            lookup[key.lower()]  = (sol, key)

        interval = 60.0 / self.bpm

        for token in tokens:
            if not self.running:
                break
            entry = lookup.get(token.lower())
            if entry:
                label, key = entry
                keyboard.press(key)
                keyboard.release(key)
                self.signals.note_played.emit(label, key)
            else:
                self.signals.note_played.emit(f"?? {token}", "–")
            time.sleep(interval)

        self.running = False
        self.signals.playback_done.emit()

    # ── Manual key press from piano buttons ──
    def _manual_press(self, key, name, deg):
        keyboard.press(key)
        keyboard.release(key)
        self.signals.note_played.emit(
            f"{SOLFEGE_LABELS.get(name, name)}({key.upper()})", key
        )

    # ── Signal handlers ──────────────────────
    def _on_note_played(self, label, key):
        color = "#74b9ff"
        self.log_box.append(
            f'<span style="color:{color}">♩ {label}</span>'
            f'<span style="color:#636e72;"> → [{key.upper()}]</span>'
        )
        # auto-scroll
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_done(self):
        self.log_box.append('<span style="color:#00b894">✓ Sequence complete.</span>')


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor("#0f0f23"))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor("#e0e0ff"))
    palette.setColor(QPalette.ColorRole.Base,            QColor("#12122a"))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor("#1a1a3a"))
    palette.setColor(QPalette.ColorRole.Text,            QColor("#e0e0ff"))
    palette.setColor(QPalette.ColorRole.Button,          QColor("#1e1e3a"))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor("#e0e0ff"))
    app.setPalette(palette)

    window = HeartopiaSequencer()
    window.show()
    sys.exit(app.exec())