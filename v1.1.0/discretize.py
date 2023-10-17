"""This module implements draggable scatter points for the purpose of discretizing and editing the spectrum baseline"""

import sys
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6 import QtCore
import pyqtgraph as pg

class DraggableScatter(pg.ScatterPlotItem):
    pointDragged = QtCore.pyqtSignal()
    dragFinished = QtCore.pyqtSignal(int, float, float, float, float) 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.draggedPointIndex = None
        self.startPos = None

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = ev.pos()
            points = self.pointsAt(pos)
            if len(points):
                self.draggedPointIndex = points[0].index()
                self.startPos = (self.data['x'][self.draggedPointIndex], self.data['y'][self.draggedPointIndex])
                ev.accept()
            else:
                ev.ignore()
        super().mousePressEvent(ev)

    def mouseDragEvent(self, ev):
        if self.draggedPointIndex is not None:
            pos = ev.pos()
            self.data['x'][self.draggedPointIndex] = pos.x()
            self.data['y'][self.draggedPointIndex] = pos.y()
            self.setData(x=self.data['x'], y=self.data['y'])
            self.pointDragged.emit()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        print('mouseReleaseEvent occurred')
        if self.draggedPointIndex is not None:
            endPos = (self.data['x'][self.draggedPointIndex], self.data['y'][self.draggedPointIndex])
            self.dragFinished.emit(self.draggedPointIndex, *self.startPos, *endPos)
            print('Emitted drafFinished signal')
            self.draggedPointIndex = None
        super().mouseReleaseEvent(ev)


class DraggableGraph(pg.GraphItem):

    def __init__(self, scatter_data):
        super().__init__()
        self.scatter_data = scatter_data
        self.graph_data = {
            'adj': np.array([[i, i+1] for i in range(len(scatter_data['x'])-1)], dtype=np.int32),
            'pen': pg.mkPen('r')
        }
        self.setData(pos=np.array(list(zip(self.scatter_data['x'], self.scatter_data['y']))), adj=self.graph_data['adj'], pen=self.graph_data['pen'])


### ============================
### ============================
### ============================
### ============================
### TESTING purposes only, below

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Interactive Scatter Plot')
        self.setGeometry(100, 100, 800, 600)

        self.plotWidget = pg.PlotWidget(self)
        self.setCentralWidget(self.plotWidget)

        x = np.arange(1, 11)
        y = np.arange(1, 11)

        self.scatter = DraggableScatter(x=x, y=y)
        self.scatter.pointDragged.connect(self.updateGraph)

        self.graph = DraggableGraph(scatter_data={'x': x, 'y': y})
        
        self.plotWidget.addItem(self.scatter)
        self.plotWidget.addItem(self.graph)

        self.show()

    def updateGraph(self):
        self.graph.setData(pos=np.array(list(zip(self.scatter.data['x'], self.scatter.data['y']))))


if __name__ == '__main__':
    # TESTING
    app = QApplication(sys.argv)
    ex = MainApp()
    sys.exit(app.exec_())
