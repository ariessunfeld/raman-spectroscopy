"""This module contains a subclass of PlotWidget that allows for cropping"""

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
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
        # Add crosshair functionality
        self.crosshair_enabled = False
        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('y', width=1))
        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('y', width=1))
        
        # Add text item for coordinates
        self.label = pg.TextItem(text="", anchor=(0, 0), color='y')
        
        # Use SignalProxy for performance
        self.proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self.mouseMoved)
        
        # Set up mouse click event for adding points in empty space
        self.scene().sigMouseClicked.connect(self.on_scene_click)
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def toggle_crosshair(self):
        """Toggle the crosshair visibility"""
        self.crosshair_enabled = not self.crosshair_enabled
        
        if self.crosshair_enabled:
            self.addItem(self.vLine, ignoreBounds=True)
            self.addItem(self.hLine, ignoreBounds=True)
            self.addItem(self.label)
        else:
            self.removeItem(self.vLine)
            self.removeItem(self.hLine)
            self.removeItem(self.label)
        
        return self.crosshair_enabled

    def mouseMoved(self, evt):
        """Handle mouse movement and update crosshair position"""
        if not self.crosshair_enabled:
            return
        
        # Fix for different event types - handle both QPointF and tuple/list
        if isinstance(evt, QtCore.QPointF):
            pos = evt
        else:
            # In some configurations, SignalProxy might wrap the event in a tuple
            try:
                pos = evt[0]
            except (TypeError, IndexError):
                # If it fails, just use the event as is
                pos = evt
        
        if self.plotItem.sceneBoundingRect().contains(pos):
            mousePoint = self.plotItem.vb.mapSceneToView(pos)
            x, y = mousePoint.x(), mousePoint.y()
            
            # Update crosshair position
            self.vLine.setPos(x)
            self.hLine.setPos(y)
            
            # Update text with coordinates
            self.label.setText(f"x: {x:.2f}, y: {y:.2f}")
            
            # Position the text near but not directly under the cursor
            self.label.setPos(x, y)

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
