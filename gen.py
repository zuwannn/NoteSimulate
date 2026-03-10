import sys
import time
import threading

from PyQt6.QtWidgets import (
    QApplication, QWidget, QTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem
)

from pynput.keyboard import Controller

keyboard = Controller()


class NotePlayer(QWidget):

    def __init__(self):
        super().__init__()

        self.running = False

        self.setWindowTitle("Note To Keyboard Player")
        self.resize(800, 500)

        main_layout = QHBoxLayout()

        # LEFT SIDE
        left_layout = QVBoxLayout()

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Insert note song")

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setPlaceholderText("Test run output")

        left_layout.addWidget(self.note_input)
        left_layout.addWidget(self.output_box)

        # RIGHT SIDE
        right_layout = QVBoxLayout()

        self.map_table = QTableWidget(3, 2)
        self.map_table.setHorizontalHeaderLabels(["note", "Map key in keyboard"])

        self.map_table.setItem(0,0,QTableWidgetItem("Do"))
        self.map_table.setItem(0,1,QTableWidgetItem("q"))

        self.map_table.setItem(1,0,QTableWidgetItem("Re"))
        self.map_table.setItem(1,1,QTableWidgetItem("w"))

        self.map_table.setItem(2,0,QTableWidgetItem("Me"))
        self.map_table.setItem(2,1,QTableWidgetItem("e"))

        self.start_btn = QPushButton("start")
        self.stop_btn = QPushButton("stop")

        right_layout.addWidget(self.map_table)
        right_layout.addWidget(self.start_btn)
        right_layout.addWidget(self.stop_btn)

        main_layout.addLayout(left_layout,3)
        main_layout.addLayout(right_layout,1)

        self.setLayout(main_layout)

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)

    def build_map(self):

        note_map = {}

        for row in range(self.map_table.rowCount()):

            note = self.map_table.item(row,0)
            key = self.map_table.item(row,1)

            if note and key:
                note_map[note.text()] = key.text()

        return note_map

    def start(self):

        if self.running:
            return

        self.running = True
        threading.Thread(target=self.play_notes).start()

    def stop(self):

        self.running = False

    def play_notes(self):

        note_map = self.build_map()

        text = self.note_input.toPlainText()
        notes = text.split()

        for n in notes:

            if not self.running:
                break

            if n in note_map:

                key = note_map[n]

                self.output_box.append(f"{n} -> {key}")

                keyboard.press(key)
                keyboard.release(key)

                time.sleep(0.4)

        self.running = False


app = QApplication(sys.argv)

window = NotePlayer()
window.show()

sys.exit(app.exec())