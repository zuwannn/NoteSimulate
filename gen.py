"""
Hearttopia Music Sequencer v3
– Real note audio via pygame sine-wave synthesis
– Beat sequencer grid  (8 / 16 / 32 beats)
– Text note input  (Do Re Mi … or keyboard keys)
– Piano keyboard panel (click to hear)
– Volume + Waveform selector (sine / triangle / square)
– BPM control
"""

import sys
import time
import threading
import numpy as np

import pygame
import pygame.sndarray

from PyQt6.QtWidgets import (
    QApplication, QWidget, QTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSpinBox, QComboBox, QGridLayout, QSlider,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPalette

from pynput.keyboard import Controller

keyboard = Controller()

# ─────────────────────────────────────────────────────────────────
#  Audio engine
# ─────────────────────────────────────────────────────────────────
SAMPLE_RATE = 44100

pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 512)   # 2 = stereo
pygame.mixer.init()
pygame.mixer.set_num_channels(32)


# Note frequencies  (C4 = Do, D4 = Re … two octaves)
NOTE_FREQ = {
    "Do":   261.63,   # C4
    "Re":   293.66,   # D4
    "Mi":   329.63,   # E4
    "Fa":   349.23,   # F4
    "Sol":  392.00,   # G4
    "La":   440.00,   # A4
    "Si":   493.88,   # B4
    "Do²":  523.25,   # C5
}


def _make_wave(freq: float, duration: float = 0.45,
               wave: str = "sine", volume: float = 0.5) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    if wave == "sine":
        samples = np.sin(2 * np.pi * freq * t)
    elif wave == "triangle":
        samples = 2 * np.abs(2 * (t * freq - np.floor(t * freq + 0.5))) - 1
    elif wave == "square":
        samples = np.sign(np.sin(2 * np.pi * freq * t))
    else:
        samples = np.sin(2 * np.pi * freq * t)

    # ADSR envelope  (attack 5 ms, decay 40 ms, sustain 0.7, release 80 ms)
    n = len(samples)
    env = np.ones(n)
    a = int(0.005 * SAMPLE_RATE)
    d = int(0.040 * SAMPLE_RATE)
    r = int(0.080 * SAMPLE_RATE)
    env[:a]    = np.linspace(0, 1, a)
    env[a:a+d] = np.linspace(1, 0.7, d)
    env[n-r:]  = np.linspace(0.7, 0, r)
    samples = samples * env * volume

    mono = (samples * 32767).astype(np.int16)
    # pygame stereo mixer requires shape (N, 2)
    return np.column_stack([mono, mono])


def build_sound_cache(wave: str = "sine", volume: float = 0.5) -> dict:
    cache = {}
    for name, freq in NOTE_FREQ.items():
        arr = _make_wave(freq, wave=wave, volume=volume)   # shape (N, 2)
        sound = pygame.sndarray.make_sound(arr)
        cache[name] = sound
    return cache


# ─────────────────────────────────────────────────────────────────
#  Hearttopia keyboard map
# ─────────────────────────────────────────────────────────────────
DEFAULT_MAP = [
    # Row 1
    ("Do",  "1",  "q"),
    ("Re",  "2",  "w"),
    ("Mi",  "3",  "e"),
    ("Fa",  "4",  "r"),
    ("Sol", "5",  "t"),
    ("La",  "6",  "y"),
    ("Si",  "7",  "u"),
    ("Do²", "1'", "i"),
    # Row 2
    ("Do",  "1",  "z"),
    ("Re",  "2",  "x"),
    ("Mi",  "3",  "c"),
    ("Fa",  "4",  "v"),
    ("Sol", "5",  "b"),
    ("La",  "6",  "h"),
    ("Si",  "7",  "j"),
    ("Si",  "7",  "m"),
    # Row 3
    ("Do",  "1",  "l"),
    ("Re",  "2",  ";"),
    ("Mi",  "3",  "/"),
    ("Fa",  "4",  "o"),
    ("Sol", "5",  "p"),
    ("La",  "6",  "["),
    ("Si",  "7",  "]"),
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

SOLFEGE = {
    "Do": "DO", "Re": "RE", "Mi": "MI",
    "Fa": "FA", "Sol": "SOL", "La": "LA",
    "Si": "SI", "Do²": "DO²",
}


# ─────────────────────────────────────────────────────────────────
#  Qt signal bridge
# ─────────────────────────────────────────────────────────────────
class Signals(QObject):
    note_played   = pyqtSignal(str, str)
    playback_done = pyqtSignal()
    update_beat   = pyqtSignal(int)


# ─────────────────────────────────────────────────────────────────
#  Note button (piano panel)
# ─────────────────────────────────────────────────────────────────
class NoteButton(QPushButton):
    def __init__(self, note_name, degree, key, parent=None):
        super().__init__(parent)
        self.note_name = note_name
        self.degree    = degree
        self.key       = key
        color = NOTE_COLORS.get(degree, "#fff")
        self.setFixedSize(62, 62)
        self._base = f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {color}dd, stop:1 {color}77);
                border: 2px solid {color};
                border-radius: 31px;
                color: #111;
                font-size: 10px;
                font-weight: 800;
            }}
            QPushButton:hover {{ background:{color}; border:2px solid #fff; }}
            QPushButton:pressed {{ background:#fff; }}
        """
        self.setStyleSheet(self._base)
        self.setText(f"{SOLFEGE.get(note_name, note_name)}\n[{key.upper()}]")


# ─────────────────────────────────────────────────────────────────
#  Beat cell
# ─────────────────────────────────────────────────────────────────
class BeatCell(QPushButton):
    def __init__(self, row, col, degree, parent=None):
        super().__init__(parent)
        self.row     = row
        self.col     = col
        self.degree  = degree
        self._on     = False
        self._cursor = False
        self.setFixedSize(34, 34)
        self.setCheckable(True)
        self.toggled.connect(lambda c: self._set(c))
        self._refresh()

    def _set(self, checked):
        self._on = checked
        self._refresh()

    def set_cursor(self, v: bool):
        self._cursor = v
        self._refresh()

    def _refresh(self):
        c = NOTE_COLORS.get(self.degree, "#888")
        if self._cursor:
            bg, border = "#ffffff", f"3px solid {c}"
        elif self._on:
            bg, border = c, "2px solid #fff"
        else:
            bg, border = "#1a1a35", "1px solid #33336a"
        self.setStyleSheet(f"""
            QPushButton {{
                background:{bg}; border:{border}; border-radius:6px;
            }}
            QPushButton:hover {{
                background:{c}44; border:2px solid {c};
            }}
        """)


# ─────────────────────────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────────────────────────
class HeartopiaSequencer(QWidget):

    def __init__(self):
        super().__init__()
        self.signals   = Signals()
        self.running   = False
        self.beat_idx  = 0
        self.beats     = 16
        self.bpm       = 120
        self.wave_type = "sine"
        self.volume    = 0.5
        self.sounds    = build_sound_cache(self.wave_type, self.volume)

        self.row_defs  = DEFAULT_MAP
        self.cells: list[list[BeatCell]] = []

        self._init_ui()
        self._connect()

    # ── UI ───────────────────────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle("♪ Hearttopia Sequencer v3 — with Audio")
        self.resize(1380, 860)
        self.setStyleSheet("""
            QWidget { background:#0d0d20; color:#e0e0ff;
                      font-family:'Segoe UI',sans-serif; }
            QScrollArea { border:none; }
            QLabel { color:#c0c0ee; }
            QScrollBar:vertical { background:#1a1a35; width:8px; border-radius:4px; }
            QScrollBar::handle:vertical { background:#44448a; border-radius:4px; }
        """)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # ── Header ──
        hdr = QLabel("♪  HEARTTOPIA  MUSIC  SEQUENCER  v3")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.setStyleSheet("""
            font-size:20px; font-weight:900; letter-spacing:5px;
            color:#a29bfe; padding:6px;
        """)
        root.addWidget(hdr)

        # ── Transport ──
        tp = QHBoxLayout()
        tp.setSpacing(10)

        self.btn_play  = self._btn("▶  PLAY",  "#00b894")
        self.btn_stop  = self._btn("■  STOP",  "#d63031")
        self.btn_clear = self._btn("✕  CLEAR", "#636e72")

        # BPM
        self._add_label(tp, "BPM")
        self.spin_bpm = QSpinBox()
        self.spin_bpm.setRange(40, 300); self.spin_bpm.setValue(120)
        self.spin_bpm.setFixedWidth(68)
        self.spin_bpm.setStyleSheet(self._spin_style())
        tp.addWidget(self.spin_bpm)

        # Beats
        self._add_label(tp, "Beats")
        self.combo_beats = QComboBox()
        for b in ["8", "16", "32"]:
            self.combo_beats.addItem(b)
        self.combo_beats.setCurrentIndex(1)
        self.combo_beats.setFixedWidth(58)
        self.combo_beats.setStyleSheet(self._combo_style())
        tp.addWidget(self.combo_beats)

        # Waveform
        self._add_label(tp, "Wave")
        self.combo_wave = QComboBox()
        for w in ["sine", "triangle", "square"]:
            self.combo_wave.addItem(w)
        self.combo_wave.setFixedWidth(82)
        self.combo_wave.setStyleSheet(self._combo_style())
        tp.addWidget(self.combo_wave)

        # Volume
        self._add_label(tp, "Vol")
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(50)
        self.slider_vol.setFixedWidth(100)
        self.slider_vol.setStyleSheet("""
            QSlider::groove:horizontal { background:#33336a; height:6px; border-radius:3px; }
            QSlider::handle:horizontal { background:#a29bfe; width:14px; height:14px;
                                         margin:-4px 0; border-radius:7px; }
            QSlider::sub-page:horizontal { background:#a29bfe; border-radius:3px; }
        """)
        tp.addWidget(self.slider_vol)

        tp.addStretch()
        for b in [self.btn_play, self.btn_stop, self.btn_clear]:
            tp.addWidget(b)

        root.addLayout(tp)

        # ── Body ──
        body = QHBoxLayout()
        body.setSpacing(12)

        # Sequencer grid
        gf = QFrame()
        gf.setStyleSheet("QFrame{background:#10102a;border:1px solid #2a2a5a;border-radius:10px;}")
        gl = QVBoxLayout(gf)
        gl.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background:transparent;")
        self.grid_inner  = QGridLayout(self.grid_widget)
        self.grid_inner.setSpacing(3)
        self._build_grid(16)

        scroll.setWidget(self.grid_widget)
        gl.addWidget(scroll)
        body.addWidget(gf, 3)

        # Right panel
        right = QVBoxLayout()
        right.setSpacing(10)

        # Text input
        tf = self._frame()
        tl = QVBoxLayout(tf)
        tl.addWidget(self._lbl("♩  Text Note Input  (e.g.  Do Re Mi Fa Sol  or  q w e r t)"))
        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText(
            "Do Re Mi Fa Sol La Si Do²\n"
            "หรือ: q w e r t y u i"
        )
        self.note_input.setMaximumHeight(90)
        self.note_input.setStyleSheet("""
            QTextEdit { background:#0a0a1a; color:#e0e0ff;
                        border:1px solid #3a3a6a; border-radius:7px;
                        font-size:13px; padding:5px; }
        """)
        self.btn_send = self._btn("▶  Play Text", "#6c5ce7")
        tl.addWidget(self.note_input)
        tl.addWidget(self.btn_send)
        right.addWidget(tf)

        # Log
        lf = self._frame()
        ll = QVBoxLayout(lf)
        ll.addWidget(self._lbl("📋  Activity Log"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("""
            QTextEdit { background:#080817; color:#74b9ff;
                        border:1px solid #3a3a6a; border-radius:7px;
                        font-family:'Courier New'; font-size:11px; padding:5px; }
        """)
        ll.addWidget(self.log_box)
        right.addWidget(lf, 1)

        # Piano keyboard
        kf = self._frame()
        kl = QVBoxLayout(kf)
        kl.addWidget(self._lbl("🎹  Click to Play"))
        kg = QGridLayout()
        kg.setSpacing(4)
        shown, col = {}, 0
        for name, deg, key in DEFAULT_MAP:
            if key in shown:
                continue
            shown[key] = True
            nb = NoteButton(name, deg, key)
            nb.clicked.connect(lambda _, n=name, d=deg, k=key: self._manual(n, d, k))
            row_pos = 0 if col < 8 else (1 if col < 16 else 2)
            kg.addWidget(nb, row_pos, col % 8)
            col += 1
        kl.addLayout(kg)
        right.addWidget(kf)

        body.addLayout(right, 2)
        root.addLayout(body, 1)

    # ── Grid builder ─────────────────────────────────────────────
    def _build_grid(self, beats: int):
        for row in self.cells:
            for c in row:
                c.deleteLater()
        self.cells.clear()
        while self.grid_inner.count():
            item = self.grid_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.beats = beats
        for col in range(beats):
            lbl = QLabel(str(col + 1))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(34)
            lbl.setStyleSheet("color:#44448a; font-size:9px;")
            self.grid_inner.addWidget(lbl, 0, col + 1)

        for r, (name, deg, key) in enumerate(self.row_defs):
            color = NOTE_COLORS.get(deg, "#888")
            lbl = QLabel(f"{SOLFEGE.get(name, name)}\n[{key.upper()}]")
            lbl.setFixedWidth(50)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(f"color:{color}; font-size:9px; font-weight:700;")
            self.grid_inner.addWidget(lbl, r + 1, 0)
            row_cells = []
            for col in range(beats):
                cell = BeatCell(r, col, deg)
                self.grid_inner.addWidget(cell, r + 1, col + 1)
                row_cells.append(cell)
            self.cells.append(row_cells)

    # ── Helpers ──────────────────────────────────────────────────
    def _btn(self, text, color):
        b = QPushButton(text)
        b.setFixedHeight(34)
        b.setStyleSheet(f"""
            QPushButton {{
                background:{color}30; color:{color};
                border:1px solid {color}; border-radius:7px;
                font-size:12px; font-weight:700; padding:0 14px;
            }}
            QPushButton:hover {{ background:{color}80; color:#fff; }}
            QPushButton:pressed {{ background:{color}; color:#0d0d20; }}
        """)
        return b

    def _frame(self):
        f = QFrame()
        f.setStyleSheet("QFrame{background:#10102a;border:1px solid #2a2a5a;border-radius:10px;}")
        return f

    def _lbl(self, text):
        l = QLabel(text)
        l.setStyleSheet("font-size:11px; color:#a29bfe; font-weight:700;")
        return l

    def _add_label(self, layout, text):
        l = QLabel(text)
        l.setStyleSheet("color:#a29bfe; font-weight:700; font-size:12px;")
        layout.addWidget(l)

    def _spin_style(self):
        return """QSpinBox { background:#1a1a38; color:#e0e0ff;
                   border:1px solid #a29bfe; border-radius:5px;
                   padding:3px; font-size:13px; font-weight:700; }"""

    def _combo_style(self):
        return """QComboBox { background:#1a1a38; color:#e0e0ff;
                   border:1px solid #a29bfe; border-radius:5px;
                   padding:3px; font-size:12px; }
                  QComboBox QAbstractItemView { background:#1a1a38; color:#e0e0ff; }"""

    # ── Connections ──────────────────────────────────────────────
    def _connect(self):
        self.btn_play.clicked.connect(self.start_seq)
        self.btn_stop.clicked.connect(self.stop_all)
        self.btn_clear.clicked.connect(self.clear_grid)
        self.btn_send.clicked.connect(self.play_text)

        self.combo_beats.currentTextChanged.connect(
            lambda t: self._build_grid(int(t)))
        self.spin_bpm.valueChanged.connect(lambda v: setattr(self, 'bpm', v))
        self.combo_wave.currentTextChanged.connect(self._on_wave_change)
        self.slider_vol.valueChanged.connect(self._on_vol_change)

        self.signals.note_played.connect(self._on_note)
        self.signals.playback_done.connect(self._on_done)
        self.signals.update_beat.connect(self._advance)

    def _on_wave_change(self, wave):
        self.wave_type = wave
        self.sounds = build_sound_cache(self.wave_type, self.volume)

    def _on_vol_change(self, val):
        self.volume = val / 100.0
        self.sounds = build_sound_cache(self.wave_type, self.volume)

    # ── Play sound ───────────────────────────────────────────────
    def _play_sound(self, note_name: str):
        sound = self.sounds.get(note_name)
        if sound:
            sound.play()

    # ── Grid sequencer ───────────────────────────────────────────
    def start_seq(self):
        if self.running:
            return
        self.running = True
        self.beat_idx = 0
        threading.Thread(target=self._run_seq, daemon=True).start()

    def _run_seq(self):
        while self.running:
            col = self.beat_idx % self.beats
            self.signals.update_beat.emit(col)
            interval = 60.0 / self.bpm

            for r, (name, deg, key) in enumerate(self.row_defs):
                if self.cells[r][col]._on:
                    self._play_sound(name)
                    keyboard.press(key)
                    keyboard.release(key)
                    self.signals.note_played.emit(
                        f"{SOLFEGE.get(name, name)}({key.upper()})", key)

            self.beat_idx += 1
            time.sleep(interval)

    def _advance(self, col: int):
        prev = (col - 1) % self.beats
        for row in self.cells:
            row[prev].set_cursor(False)
            row[col].set_cursor(True)

    def stop_all(self):
        self.running = False
        for row in self.cells:
            for c in row:
                c.set_cursor(False)
        self.log_box.append("■ Stopped.")

    def clear_grid(self):
        for row in self.cells:
            for c in row:
                if c._on:
                    c.setChecked(False)

    # ── Text sequence ─────────────────────────────────────────────
    def play_text(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._run_text, daemon=True).start()

    def _run_text(self):
        # Build lookup:  token → (display_label, note_name, key)
        lookup: dict[str, tuple[str, str, str]] = {}
        for name, deg, key in DEFAULT_MAP:
            sol = SOLFEGE.get(name, name)
            for alias in [sol.lower(), name.lower(), key.lower()]:
                if alias not in lookup:
                    lookup[alias] = (sol, name, key)

        tokens   = self.note_input.toPlainText().split()
        interval = 60.0 / self.bpm

        for token in tokens:
            if not self.running:
                break
            entry = lookup.get(token.lower())
            if entry:
                label, note_name, key = entry
                self._play_sound(note_name)
                keyboard.press(key)
                keyboard.release(key)
                self.signals.note_played.emit(label, key)
            else:
                self.signals.note_played.emit(f"?? {token}", "–")
            time.sleep(interval)

        self.running = False
        self.signals.playback_done.emit()

    # ── Manual piano press ────────────────────────────────────────
    def _manual(self, name, deg, key):
        self._play_sound(name)
        keyboard.press(key)
        keyboard.release(key)
        self.signals.note_played.emit(
            f"{SOLFEGE.get(name, name)}({key.upper()})", key)

    # ── Log handlers ──────────────────────────────────────────────
    def _on_note(self, label, key):
        self.log_box.append(
            f'<span style="color:#74b9ff">♩ {label}</span>'
            f'<span style="color:#555577"> → [{key.upper()}]</span>'
        )
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_done(self):
        self.log_box.append('<span style="color:#00b894">✓ Done.</span>')


# ─────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,        QColor("#0d0d20"))
    pal.setColor(QPalette.ColorRole.WindowText,    QColor("#e0e0ff"))
    pal.setColor(QPalette.ColorRole.Base,          QColor("#10102a"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a1a38"))
    pal.setColor(QPalette.ColorRole.Text,          QColor("#e0e0ff"))
    pal.setColor(QPalette.ColorRole.Button,        QColor("#1a1a38"))
    pal.setColor(QPalette.ColorRole.ButtonText,    QColor("#e0e0ff"))
    app.setPalette(pal)

    win = HeartopiaSequencer()
    win.show()
    sys.exit(app.exec())