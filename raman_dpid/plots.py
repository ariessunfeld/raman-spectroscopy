"""This module contains a subclass of PlotWidget that allows for cropping"""

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal
import pyqtgraph as pg
import numpy as np

class CroppablePlotWidget(pg.PlotWidget):

    point_added = pyqtSignal(float, float)  # emits x,y of new point
    point_removed = pyqtSignal(int)  # emits idx of removed point

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cropping = False
        self.start_crop_pos = None
        self.crop_region = None
        self.points = {'x': np.array([]), 'y': np.array([])}
        self.mode = 'normal'

        # Set up mouse click event for adding points in empty space
        self.scene().sigMouseClicked.connect(self.on_scene_click)
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def get_crop_region(self):
        return self.crop_region
    
    def set_crop_region(self, start_x: float, end_x: float):
        self.start_crop_pos = start_x

        if self.crop_region is None:
            self.crop_region = pg.LinearRegionItem([self.start_crop_pos, end_x], movable=False, brush=pg.mkBrush(128, 128, 128, 100))
            self.addItem(self.crop_region)
        else:
            self.crop_region.setRegion([self.start_crop_pos, end_x])

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
                    # if self.crop_region is None:
                    #     self.crop_region = pg.LinearRegionItem([self.start_crop_pos, end_crop_pos], movable=False, brush=pg.mkBrush(128, 128, 128, 100))
                    #     self.addItem(self.crop_region)
                    # else:
                    #     self.crop_region.setRegion([self.start_crop_pos, end_crop_pos])
                    self.set_crop_region(self.start_crop_pos, end_crop_pos)
                event.accept()
            else:
                event.ignore()
        else:
            super().mouseMoveEvent(event)

    def on_scene_click(self, event):
        if not self.cropping:  # Only handle click if cropping is not active
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.scenePos()
                mousePoint = self.plotItem.vb.mapSceneToView(pos)
                x_click, y_click = mousePoint.x(), mousePoint.y()
                #print(f"Scene clicked at: x={x_click}, y={y_click}")

                x, y = self.points['x'], self.points['y']
                if len(x) and len(y):
                    distances = np.hypot(x - x_click, y - y_click)
                    closest_point_idx = np.argmin(distances)
                    threshold = 0.1  # Threshold for detecting clicks on points

                    # Check if the click is on an existing point
                    click_on_point = distances[closest_point_idx] < threshold
                else:
                    click_on_point = False

                if self.mode == 'add' and not click_on_point:
                    #("Adding a new point")
                    self.points['x'] = np.append(self.points['x'], x_click)
                    self.points['y'] = np.append(self.points['y'], y_click)
                    self.point_added.emit(x_click, y_click)
                    self.update_plot()

    def on_point_click(self, plot, points):
        if not self.cropping:  # Only handle point clicks if cropping is not active
            pos = points[0].pos()
            x_click, y_click = pos.x(), pos.y()
            #print(f"Point clicked at: x={x_click}, y={y_click}")

            x, y = self.points['x'], self.points['y']
            distances = np.hypot(x - x_click, y - y_click)
            closest_point_idx = np.argmin(distances)
            threshold = 0.1  # Threshold for detecting clicks on points

            if self.mode == 'delete' and distances[closest_point_idx] < threshold:
                #print(f"Removing point: {closest_point_idx}")
                self.points['x'] = np.delete(self.points['x'], closest_point_idx)
                self.points['y'] = np.delete(self.points['y'], closest_point_idx)
                self.point_removed.emit(closest_point_idx)
                self.update_plot()


    def update_plot(self):
        if hasattr(self, 'scatter'):
            self.removeItem(self.scatter)
        self.scatter = pg.ScatterPlotItem(self.points['x'], self.points['y'], pen='r', symbol='o', symbolSize=7, symbolBrush=(255, 0, 0))
        self.scatter.sigClicked.connect(self.on_point_click)  # Reconnect the signal to handle point clicks
        self.addItem(self.scatter)

    def set_scatter(self, x, y):
        self.points['x'] = np.array(x)
        self.points['y'] = np.array(y)
        self.update_plot()
