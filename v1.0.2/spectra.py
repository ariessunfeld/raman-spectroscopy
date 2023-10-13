"""Helper classes for handling and representing Raman spectra"""

import numpy as np
class Spectrum:
    
    def __init__(self, x, y) -> None:
        if len(x) != len(y):
            raise ValueError('x and y must be of same length')
        self.x = np.array(x)
        self.y = np.array(y)
        self.baseline = None

    def normalize(self, inplace=False):
        if inplace:
            self.y = self.y / sum(self.y)
        else:
            return Spectrum(self.x, self.y / sum(self.y))