"""This module contains a subclass of PlotWidget that allows for cropping"""

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QTextEdit, QGridLayout
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QListWidget, QAbstractItemView, QListView
from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal
import pyqtgraph as pg

class CroppablePlotWidget(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cropping = False
        self.start_crop_pos = None
        self.crop_region = None

    def get_crop_region(self):
        return self.crop_region

    def mousePressEvent(self, event):
        if self.cropping:
            self.start_crop_pos = self.getPlotItem().vb.mapSceneToView(QtCore.QPointF(event.pos())).x()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.cropping:
            self.start_crop_pos = None  # Reset start position
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        if self.cropping:
            if event.buttons() == Qt.MouseButton.LeftButton:  # Check if left mouse button is pressed
                if self.start_crop_pos is not None:
                    end_crop_pos = self.getPlotItem().vb.mapSceneToView(QtCore.QPointF(pos)).x()
                    if self.crop_region is None:
                        self.crop_region = pg.LinearRegionItem([self.start_crop_pos, end_crop_pos], movable=False, brush=pg.mkBrush(128, 128, 128, 100))
                        self.addItem(self.crop_region)
                    else:
                        self.crop_region.setRegion([self.start_crop_pos, end_crop_pos])
                event.accept()
            else:
                event.ignore()
        else:
            super().mouseMoveEvent(event)
