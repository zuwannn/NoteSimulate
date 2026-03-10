import sys
import time
import threading
from pynput.keyboard import Controller

from PyQt6.QtWidgets import (
    QApplication, QWidget, QTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

keyboard = Controller()

# Full key map based on the Hearttopia piano screenshot
KEY_MAP = {
    # ==========================
    # --- HIGH OCTAVE (Q row) ---
    # ==========================
    # White keys: q w e r t y u i
    "do+": "q", "re+": "w", "mi+": "e", "me+": "e", "fa+": "r", "sol+": "t", "la+": "y", "si+": "u", "do2+": "i",
    "1+": "q",  "2+": "w",  "3+": "e",  "4+": "r",  "5+": "t",  "6+": "y",  "7+": "u",  "8+": "i",
    # (Default mapping requested previously "do re me -> q w e")
    "do": "q", "re": "w", "mi": "e", "me": "e", "fa": "r", "sol": "t", "la": "y", "si": "u", "do2": "i",
    "1": "q", "2": "w", "3": "e", "4": "r", "5": "t", "6": "y", "7": "u", "8": "i", "1'": "i",
    # Black keys: 2 3 5 6 7
    "do#+": "2", "re#+": "3", "fa#+": "5", "sol#+": "6", "la#+": "7",
    "do#": "2",  "re#": "3",  "fa#": "5",  "sol#": "6",  "la#": "7",

    # ==========================
    # --- MIDDLE OCTAVE (Z row) ---
    # ==========================
    # White keys: z x c v b n m
    "do=": "z", "re=": "x", "mi=": "c", "me=": "c", "fa=": "v", "sol=": "b", "la=": "n", "si=": "m",
    "1=": "z",  "2=": "x",  "3=": "c",  "4=": "v",  "5=": "b",  "6=": "n",  "7=": "m",
    # Black keys: s d g h j
    "do#=": "s", "re#=": "d", "fa#=": "g", "sol#=": "h", "la#=": "j",

    # ==========================
    # --- LOW OCTAVE (, . / O P [ ]) ---
    # ==========================
    # White keys: , . / o p [ ]
    "do-": ",", "re-": ".", "mi-": "/", "me-": "/", "fa-": "o", "sol-": "p", "la-": "[", "si-": "]",
    "1-": ",",  "2-": ".",  "3-": "/",  "4-": "o",  "5-": "p",  "6-": "[",  "7-": "]",
    # Black keys: l ; 0 - =
    "do#-": "l", "re#-": ";", "fa#-": "0", "sol#-": "-", "la#-": "=",
}

# Allow direct typing of the physical English letters/symbols 
# (e.g., if user types "q w e z x c , . /", it will just press them directly)
for key in "qwertyui23567zxcvbnmsdghj,./op[]l;0-=":
    KEY_MAP[key] = key

class Signals(QObject):
    status_update = pyqtSignal(str)
    playback_done = pyqtSignal()

class AutoPlayerUI(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = Signals()
        self.running = False
        self._init_ui()
        self._connect()

    def _init_ui(self):
        self.setWindowTitle("Hearttopia Auto Player - Full Piano View")
        self.resize(540, 500)
        self.setStyleSheet("""
            QWidget { background-color: #0d0d20; color: #e0e0ff; font-family: 'Segoe UI', sans-serif; }
            QLabel { color: #c0c0ee; }
            QTextEdit { 
                background-color: #1a1a35; color: #ffffff; 
                border: 1px solid #336; border-radius: 5px; padding: 5px; font-size: 14px;
            }
            QPushButton { 
                background-color: #333366; color: #ffffff; 
                border-radius: 5px; padding: 10px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #444488; }
            QPushButton:pressed { background-color: #222244; }
            QSpinBox { 
                background-color: #1a1a35; color: #ffffff;
                border: 1px solid #336; padding: 3px; font-size: 14px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("🎹 Hearttopia Auto Player")
        title.setStyleSheet("font-size: 22px; font-weight: 900; color: #a29bfe; padding: 5px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        instruction_text = (
            "<b>1. Enter Song Notes (Space separated, '-' for rest)</b><br><br>"
            "<span style='color:#74b9ff'>• <b>High Octave</b>: do re mi (or 1 2 3) ➔ Presses: Q W E R T Y U</span><br>"
            "<span style='color:#a8e6cf'>• <b>Middle Octave</b>: do= re= mi= (or 1= 2= 3=) ➔ Presses: Z X C V B N M</span><br>"
            "<span style='color:#fab1a0'>• <b>Low Octave</b>: do- re- mi- (or 1- 2- 3-) ➔ Presses: , . / O P [ ]</span><br><br>"
            "<i>Tip: You can also just type the keyboard letters directly! (e.g. q w e z x c)</i>"
        )
        instruction = QLabel(instruction_text)
        instruction.setStyleSheet("font-size: 13px; color: #a29bfe; background:#10102a; padding:10px; border-radius:5px;")
        layout.addWidget(instruction)

        self.song_input = QTextEdit()
        # Default placeholder shows usage of different keys
        self.song_input.setPlaceholderText("do do sol sol la la sol - fa= fa= mi= mi= re= re= do=")
        self.song_input.setPlainText("do do sol sol la la sol - fa= fa= mi= mi= re= re= do=")
        layout.addWidget(self.song_input)

        controls_layout = QHBoxLayout()
        bpm_label = QLabel("BPM (Speed):")
        bpm_label.setStyleSheet("font-weight: bold;")
        controls_layout.addWidget(bpm_label)
        
        self.bpm_spin = QSpinBox()
        self.bpm_spin.setRange(40, 300)
        self.bpm_spin.setValue(120)
        self.bpm_spin.setFixedWidth(80)
        controls_layout.addWidget(self.bpm_spin)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        btn_layout = QHBoxLayout()
        self.btn_play = QPushButton("▶ PLAY (3s Delay)")
        self.btn_play.setStyleSheet("background-color: #00b894; color: #000000; font-weight: 900;")
        
        self.btn_stop = QPushButton("■ STOP")
        self.btn_stop.setStyleSheet("background-color: #d63031; color: #ffffff; font-weight: 900;")
        
        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_stop)
        layout.addLayout(btn_layout)

        self.lbl_status = QLabel("Status: Ready to play.")
        self.lbl_status.setStyleSheet("color: #74b9ff; font-family: 'Courier New'; font-size: 14px; font-weight: bold;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)

    def _connect(self):
        self.btn_play.clicked.connect(self.start_play)
        self.btn_stop.clicked.connect(self.stop_play)
        self.signals.status_update.connect(self.lbl_status.setText)
        self.signals.playback_done.connect(self._on_done)

    def start_play(self):
        if self.running:
            return
        
        song = self.song_input.toPlainText().strip()
        if not song:
            self.lbl_status.setText("Status: Please enter a song!")
            return

        self.running = True
        bpm = self.bpm_spin.value()
        self.btn_play.setEnabled(False)
        threading.Thread(target=self._run_player, args=(song, bpm), daemon=True).start()

    def _run_player(self, song, bpm):
        try:
            for i in range(3, 0, -1):
                if not self.running: return
                self.signals.status_update.emit(f"Status: Switch to game! Starting in {i}...")
                time.sleep(1)

            self.signals.status_update.emit("Status: Playing...")
            interval = 60.0 / bpm
            notes = song.split()

            for note in notes:
                if not self.running:
                    break
                
                if note == "-":
                    self.signals.status_update.emit("Status: Rest [-]")
                    time.sleep(interval)
                    continue
                
                key = KEY_MAP.get(note.lower())
                if key:
                    self.signals.status_update.emit(f"Status: Playing Note [ {note.upper()} ] --> Pressing Key [ {key.upper()} ]")
                    keyboard.press(key)
                    time.sleep(0.05)  # Simulate physical key press length
                    keyboard.release(key)
                else:
                    self.signals.status_update.emit(f"Status: Unknown note skipped: {note}")
                
                time.sleep(interval)
        finally:
            self.running = False
            self.signals.playback_done.emit()

    def stop_play(self):
        self.running = False
        self.lbl_status.setText("Status: Stopped")

    def _on_done(self):
        self.btn_play.setEnabled(True)
        if self.lbl_status.text() != "Status: Stopped":
            self.lbl_status.setText("Status: Finished playing!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = AutoPlayerUI()
    win.show()
    sys.exit(app.exec())
