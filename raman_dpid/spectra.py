"""Helper classes for handling and representing Raman spectra"""

import numpy as np

class Spectrum:
    def __init__(self, x, y):
        self.x = np.array(x)
        self.y = np.array(y)
        self._history = [(x.copy(), y.copy())]
        self._current = 0

    def correct_baseline(self, baseline):
        self.y -= baseline
        self._add_to_history()

    def crop(self, start, end):
        mask = (self.x >= start) & (self.x <= end)
        self.x = self.x[mask]
        self.y = self.y[mask]
        self._add_to_history()
    
    def undo(self):
        if self._current > 0:
            self._current -= 1
            self._restore()

    def redo(self):
        if self._current < len(self._history) - 1:
            self._current += 1
            self._restore()

    def _add_to_history(self):
        # Remove any redo data beyond the current pointer
        self._history = self._history[:self._current+1]
        self._history.append((self.x.copy(), self.y.copy()))
        self._current = len(self._history) - 1

    def _restore(self):
        self.x, self.y = self._history[self._current]