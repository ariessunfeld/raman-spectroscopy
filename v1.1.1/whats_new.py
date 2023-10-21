"""This file contains new feature messages to communicate updates to the user"""

from PyQt6.QtWidgets import QDialog, QPushButton, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtGui import QFont

class WhatsNewDialog(QDialog):
    def __init__(self, messages, parent=None):
        super().__init__(parent)
        
        self.messages = messages
        self.current_index = 0

        # Configure dialog appearance
        self.setWindowTitle("What's New")
        self.setGeometry(200, 200, 600, 200)  # Change size to desired dimensions

        # Setup UI components
        self.layout = QVBoxLayout(self)
        
        self.message_label = QLabel(self)
        self.message_label.setFont(QFont("Arial", 12, QFont.Weight.Light))
        self.layout.addWidget(self.message_label)

        self.button_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("Previous", self)
        self.prev_button.clicked.connect(self.show_previous_message)
        self.button_layout.addWidget(self.prev_button)

        self.next_button = QPushButton("Next", self)
        self.next_button.clicked.connect(self.show_next_message)
        self.button_layout.addWidget(self.next_button)

        self.close_button = QPushButton("Close", self)
        self.close_button.clicked.connect(self.accept)
        self.button_layout.addWidget(self.close_button)

        self.layout.addLayout(self.button_layout)
        self.setLayout(self.layout)

        self.show_current_message()

    def show_current_message(self):
        self.message_label.setText(self.messages[self.current_index])
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.messages) - 1)

    def show_previous_message(self):
        if self.current_index > 0:
            self.current_index -= 1
        self.show_current_message()

    def show_next_message(self):
        if self.current_index < len(self.messages) - 1:
            self.current_index += 1
        self.show_current_message()

new_features = {
    'nt': [
        'Introducing Undo/Redo functionality! Press Ctrl+Z to Undo a file-load, crop, or baseline edit. Press Ctrl+Shift+Z to Redo.',
        'Press Ctrl+L to shortcut the Load Spectrum button.',
        'Press Ctrl+E to quickly estimate the baseline, then press it again to apply the baseline correction.',
        'Press Ctrl+R to activate Crop mode. Click and drag to select the region to crop out, then press Ctrl+R again to apply the crop.',
        'Press Ctrl+D to discretize the baseline, once it\'s been estimated. Then click and drag the discrete baseline points to edit the line.',
        'Once you\'re happy with your data processing, press Ctrl+S to save your spectrum.'
    ],
    'posix': [
        'Introducing Undo/Redo functionality! Press Cmd+Z to Undo a file-load, crop, or baseline edit. Press Cmd+Shift+Z to Redo.',
        'Press Cmd+L to shortcut the Load Spectrum button.',
        'Press Cmd+E to quickly estimate the baseline, then press it again to apply the baseline correction.',
        'Press Cmd+R to activate Crop mode. Click and drag to select the region to crop out, then press Cmd+R again to apply the crop.',
        'Press Cmd+D to discretize the baseline, once it\'s been estimated. Then click and drag the discrete baseline points to edit the line.',
        'Once you\'re happy with your data processing, press Cmd+S to save your spectrum.'
    ]
}